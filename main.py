"""
Загрузка оперативных снимков БРЛК «Метеор-М» с FTP и сортировка архива по дате съёмки.

Скрипт выполняет один цикл обработки и завершается. Его запуск по расписанию
предполагается настроить в Планировщике заданий Windows.
"""

from __future__ import annotations

import calendar
import fnmatch
import ftplib
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DEST_DIR = r"Z:\ENVISAT\METEOP"
DEFAULT_FILE_GLOB = "METM24_*_BRLK_RLI_log10.tif"
ACQUISITION_DATE_RE = re.compile(
    r"^METM24_(?P<date>\d{8})t\d{6}_",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class Settings:
    """Параметры FTP, локального архива и логирования."""

    ftp_host: str
    ftp_port: int
    ftp_user: str
    ftp_password: str
    ftp_remote_dir: str
    ftp_timeout: float
    dest_dir: Path
    file_glob: str
    log_dir: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        """Читает настройки из переменных окружения и файла .env."""
        try:
            ftp_port = int(os.getenv("METEOR_FTP_PORT", "21"))
            ftp_timeout = float(os.getenv("METEOR_FTP_TIMEOUT", "60"))
        except ValueError as exc:
            raise ValueError(
                "METEOR_FTP_PORT должен быть целым числом, "
                "а METEOR_FTP_TIMEOUT — числом секунд."
            ) from exc

        dest_dir = Path(os.getenv("METEOR_DEST_DIR", DEFAULT_DEST_DIR)).expanduser()
        log_dir = Path(os.getenv("METEOR_LOG_DIR", "logs")).expanduser()
        if not log_dir.is_absolute():
            log_dir = BASE_DIR / log_dir

        return cls(
            ftp_host=os.getenv("METEOR_FTP_HOST", "ftp.ntsomz.ru").strip(),
            ftp_port=ftp_port,
            ftp_user=os.getenv("METEOR_FTP_USER", "").strip(),
            ftp_password=os.getenv("METEOR_FTP_PASSWORD", ""),
            ftp_remote_dir=os.getenv("METEOR_FTP_REMOTE_DIR", ".").strip() or ".",
            ftp_timeout=ftp_timeout,
            dest_dir=dest_dir,
            file_glob=os.getenv("METEOR_FILE_GLOB", DEFAULT_FILE_GLOB).strip()
            or DEFAULT_FILE_GLOB,
            log_dir=log_dir,
        )


def configure_logging(log_dir: Path) -> logging.Logger:
    """Настраивает консольный лог и ротацию файла журнала."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "meteor.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError as exc:
        root_logger.warning(
            "Не удалось включить запись в файл журнала (%s). "
            "Логирование продолжится в консоль.",
            exc,
        )

    return logging.getLogger("meteor")


def filename_matches(filename: str, file_glob: str) -> bool:
    """Проверяет маску без учёта регистра; поддерживает расширения .tif и .tiff."""
    normalized_name = filename.casefold()
    normalized_pattern = file_glob.casefold()
    patterns = [normalized_pattern]

    # Шаблон в .env обычно заканчивается на .tif. Разрешаем также вариант .tiff.
    if normalized_pattern.endswith(".tif"):
        patterns.append(normalized_pattern[:-4] + ".tiff")

    return any(fnmatch.fnmatchcase(normalized_name, pattern) for pattern in patterns)


def parse_acquisition_date(filename: str) -> date | None:
    """
    Извлекает дату съёмки из имени вида:
    METM24_20261005t030639_13488_1_1_BRLK_RLI_log10.tif.
    """
    match = ACQUISITION_DATE_RE.match(filename)
    if match is None:
        return None

    try:
        return datetime.strptime(match.group("date"), "%Y%m%d").date()
    except ValueError:
        return None


def destination_path_for_file(dest_root: Path, filename: str) -> Path | None:
    """
    Формирует путь архива YYYY/MM/DD-DD по семидневным интервалам внутри месяца.
    Например, 2026-10-05 попадает в каталог 2026/10/01-07.
    """
    acquisition_date = parse_acquisition_date(filename)
    if acquisition_date is None:
        return None

    period_start = ((acquisition_date.day - 1) // 7) * 7 + 1
    last_day_of_month = calendar.monthrange(
        acquisition_date.year,
        acquisition_date.month,
    )[1]
    period_end = min(period_start + 6, last_day_of_month)
    period_folder = f"{period_start:02d}-{period_end:02d}"

    return (
        dest_root
        / f"{acquisition_date.year:04d}"
        / f"{acquisition_date.month:02d}"
        / period_folder
        / filename
    )


def remove_empty_directories(
    dest_root: Path,
    logger: logging.Logger,
) -> int:
    """
    Удаляет только пустые каталоги внутри архива.
    Файлы и каталоги с содержимым не удаляются.
    """
    removed_count = 0

    try:
        directories = [
            path for path in dest_root.rglob("*") if path.is_dir()
        ]
    except OSError:
        logger.exception("Не удалось просканировать каталоги архива: %s", dest_root)
        return 0

    # Сначала проверяем самые глубокие каталоги, затем родительские.
    directories.sort(key=lambda path: len(path.parts), reverse=True)

    for directory in directories:
        try:
            next(directory.iterdir())
            continue
        except StopIteration:
            pass
        except OSError:
            logger.warning("Не удалось проверить каталог: %s", directory)
            continue

        try:
            directory.rmdir()
            removed_count += 1
            logger.info("Удалён пустой каталог: %s", directory)
        except OSError:
            logger.warning("Не удалось удалить пустой каталог: %s", directory)

    return removed_count


def sort_existing_files(
    dest_root: Path,
    file_glob: str,
    logger: logging.Logger,
) -> dict[str, int]:
    """
    Ищет снимки по всему архиву и приводит их к структуре YYYY/MM/01-07 и т. д.
    При конфликтах имён не удаляет исходный файл и не перезаписывает архивный.
    После сортировки удаляет только пустые каталоги старой структуры.
    """
    stats = {
        "moved": 0,
        "already_sorted": 0,
        "duplicates": 0,
        "unrecognized": 0,
        "errors": 0,
        "empty_dirs_removed": 0,
    }

    try:
        candidates = [
            path
            for path in dest_root.rglob("*")
            if path.is_file() and filename_matches(path.name, file_glob)
        ]
    except OSError:
        logger.exception("Не удалось просканировать архив: %s", dest_root)
        stats["errors"] += 1
        return stats

    logger.info(
        "Проверка локального архива: найдено снимков по маске — %d",
        len(candidates),
    )

    for source in candidates:
        target = destination_path_for_file(dest_root, source.name)
        if target is None:
            logger.warning(
                "Не удалось определить дату по имени; файл оставлен на месте: %s",
                source,
            )
            stats["unrecognized"] += 1
            continue

        try:
            if source.resolve() == target.resolve():
                stats["already_sorted"] += 1
                continue

            if target.exists():
                logger.warning(
                    "Конфликт имён: целевой файл уже существует. "
                    "Исходный файл оставлен без изменений: %s",
                    source,
                )
                stats["duplicates"] += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            logger.info("Отсортирован по недельному интервалу: %s -> %s", source, target)
            stats["moved"] += 1
        except OSError:
            logger.exception("Ошибка при сортировке файла: %s", source)
            stats["errors"] += 1

    stats["empty_dirs_removed"] = remove_empty_directories(dest_root, logger)

    logger.info(
        "Сортировка архива завершена: перемещено=%d, уже на месте=%d, "
        "конфликтов имён=%d, без корректной даты=%d, пустых каталогов удалено=%d, "
        "ошибок=%d",
        stats["moved"],
        stats["already_sorted"],
        stats["duplicates"],
        stats["unrecognized"],
        stats["empty_dirs_removed"],
        stats["errors"],
    )
    return stats


def audit_archive(
    dest_root: Path,
    file_glob: str,
    logger: logging.Logger,
) -> dict[str, int]:
    """
    Проверяет итоговый архив:
    - снимки находятся в правильных недельных каталогах;
    - файлы с некорректной датой помечаются;
    - посторонние файлы и временные .part регистрируются, но не удаляются.
    """
    stats = {
        "recognized": 0,
        "misplaced": 0,
        "invalid_date": 0,
        "unexpected": 0,
        "temporary": 0,
        "scan_errors": 0,
    }

    try:
        entries = list(dest_root.rglob("*"))
    except OSError:
        logger.exception("Не удалось выполнить аудит архива: %s", dest_root)
        stats["scan_errors"] += 1
        return stats

    for path in entries:
        if not path.is_file():
            continue

        if filename_matches(path.name, file_glob):
            stats["recognized"] += 1
            expected_path = destination_path_for_file(dest_root, path.name)

            if expected_path is None:
                stats["invalid_date"] += 1
                logger.warning(
                    "АУДИТ: не распознана дата снимка; файл не перемещён: %s",
                    path,
                )
                continue

            try:
                correctly_placed = path.resolve() == expected_path.resolve()
            except OSError:
                correctly_placed = False

            if not correctly_placed:
                stats["misplaced"] += 1
                logger.warning(
                    "АУДИТ: снимок находится не в целевом недельном каталоге. "
                    "Ожидалось: %s; найдено: %s",
                    expected_path,
                    path,
                )
            continue

        if path.name.casefold().endswith(".part"):
            stats["temporary"] += 1
            logger.warning(
                "АУДИТ: найден временный/незавершённый файл; автоматическое удаление "
                "не выполняется: %s",
                path,
            )
        else:
            stats["unexpected"] += 1
            logger.warning(
                "АУДИТ: посторонний файл в архиве; автоматическое удаление "
                "не выполняется: %s",
                path,
            )

    logger.info(
        "Аудит архива: распознанных снимков=%d, неверное расположение=%d, "
        "некорректная дата=%d, временных .part=%d, посторонних файлов=%d, "
        "ошибок сканирования=%d",
        stats["recognized"],
        stats["misplaced"],
        stats["invalid_date"],
        stats["temporary"],
        stats["unexpected"],
        stats["scan_errors"],
    )
    return stats


def remote_basename(remote_path: str) -> str:
    """Извлекает имя файла из пути, возвращённого FTP-сервером."""
    return PurePosixPath(remote_path.replace("\\", "/")).name


def get_remote_size(
    ftp: ftplib.FTP,
    remote_path: str,
    logger: logging.Logger,
) -> int | None:
    """Получает размер удалённого файла, если FTP-сервер поддерживает SIZE."""
    try:
        size = ftp.size(remote_path)
        return int(size) if size is not None else None
    except ftplib.all_errors as exc:
        logger.debug(
            "Размер %s не удалось получить командой SIZE: %s",
            remote_path,
            exc,
        )
        return None


def download_remote_files(
    settings: Settings,
    logger: logging.Logger,
) -> dict[str, int]:
    """
    Загружает файлы по заданной маске в недельные каталоги архива.
    Файл сначала записывается как .part и публикуется в архиве только после
    успешной передачи и, если размер известен, проверки размера.
    """
    stats = {
        "downloaded": 0,
        "already_present": 0,
        "unrecognized": 0,
        "errors": 0,
    }

    if not settings.ftp_host or not settings.ftp_user or not settings.ftp_password:
        logger.error(
            "Не заданы параметры FTP. Заполните METEOR_FTP_USER и "
            "METEOR_FTP_PASSWORD в локальном файле .env."
        )
        stats["errors"] += 1
        return stats

    logger.info(
        "Подключение к FTP %s:%d; удалённый каталог: %s",
        settings.ftp_host,
        settings.ftp_port,
        settings.ftp_remote_dir,
    )

    try:
        ftp = ftplib.FTP()
        ftp.connect(
            settings.ftp_host,
            settings.ftp_port,
            timeout=settings.ftp_timeout,
        )
        with ftp:
            ftp.login(settings.ftp_user, settings.ftp_password)
            ftp.set_pasv(True)

            if settings.ftp_remote_dir not in ("", ".", "./"):
                ftp.cwd(settings.ftp_remote_dir)

            remote_entries = ftp.nlst()
            matched_entries = [
                entry
                for entry in remote_entries
                if filename_matches(remote_basename(entry), settings.file_glob)
            ]

            logger.info(
                "На FTP найдено записей: %d; файлов по маске %s: %d",
                len(remote_entries),
                settings.file_glob,
                len(matched_entries),
            )

            for remote_path in matched_entries:
                filename = remote_basename(remote_path)
                target = destination_path_for_file(settings.dest_dir, filename)

                if target is None:
                    logger.warning(
                        "Файл соответствует маске, но дата в имени некорректна: %s",
                        filename,
                    )
                    stats["unrecognized"] += 1
                    continue

                part_path = target.with_name(target.name + ".part")

                try:
                    remote_size = get_remote_size(ftp, remote_path, logger)

                    if target.exists():
                        if not target.is_file():
                            raise IsADirectoryError(
                                f"Целевой путь существует, но не является файлом: {target}"
                            )

                        local_size = target.stat().st_size
                        if remote_size is None or local_size == remote_size:
                            logger.debug("Файл уже находится в архиве: %s", target)
                            stats["already_present"] += 1
                            continue

                        logger.warning(
                            "Размер существующего файла отличается от FTP "
                            "(локальный=%d, FTP=%d); будет выполнена повторная загрузка: %s",
                            local_size,
                            remote_size,
                            target,
                        )

                    target.parent.mkdir(parents=True, exist_ok=True)
                    part_path.unlink(missing_ok=True)

                    with part_path.open("wb") as local_file:
                        ftp.retrbinary(
                            f"RETR {remote_path}",
                            local_file.write,
                            blocksize=1024 * 1024,
                        )

                    downloaded_size = part_path.stat().st_size
                    if downloaded_size == 0:
                        raise OSError("Получен файл нулевого размера.")

                    if remote_size is not None and downloaded_size != remote_size:
                        raise OSError(
                            f"Размер загруженного файла ({downloaded_size} байт) "
                            f"не совпадает с FTP ({remote_size} байт)."
                        )

                    # Path.replace публикует завершённый файл на том же диске.
                    part_path.replace(target)
                    logger.info(
                        "Загружен: %s -> %s (%d байт)",
                        filename,
                        target,
                        downloaded_size,
                    )
                    stats["downloaded"] += 1

                except (OSError, ftplib.Error, EOFError, UnicodeError, ValueError):
                    logger.exception("Ошибка при загрузке FTP-файла: %s", remote_path)
                    stats["errors"] += 1
                    try:
                        part_path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning(
                            "Не удалось удалить временный файл: %s", part_path
                        )

    except ftplib.all_errors:
        logger.exception("Не удалось выполнить FTP-сеанс.")
        stats["errors"] += 1

    logger.info(
        "FTP-обработка завершена: загружено=%d, уже в архиве=%d, "
        "без распознанной даты=%d, ошибок=%d",
        stats["downloaded"],
        stats["already_present"],
        stats["unrecognized"],
        stats["errors"],
    )
    return stats


def main() -> int:
    """Выполняет сортировку архива, загрузку с FTP и завершает работу."""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            # TextIO в типовых объявлениях не всегда описывает reconfigure(),
            # хотя этот метод доступен у стандартных потоков Python.
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8")
                except (OSError, UnicodeError):
                    pass

    load_dotenv(BASE_DIR / ".env", override=False)

    try:
        settings = Settings.from_environment()
    except ValueError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2

    logger = configure_logging(settings.log_dir)
    logger.info("========== Запуск meteor ==========")
    logger.info("Каталог архива: %s", settings.dest_dir)
    logger.info("Маска файлов: %s", settings.file_glob)

    try:
        settings.dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception(
            "Каталог архива недоступен или не может быть создан: %s",
            settings.dest_dir,
        )
        return 2

    sort_stats = sort_existing_files(settings.dest_dir, settings.file_glob, logger)
    ftp_stats = download_remote_files(settings, logger)
    audit_stats = audit_archive(settings.dest_dir, settings.file_glob, logger)

    operational_errors = (
        sort_stats["errors"]
        + ftp_stats["errors"]
        + audit_stats["scan_errors"]
    )
    archive_issues = (
        audit_stats["misplaced"]
        + audit_stats["invalid_date"]
        + audit_stats["unexpected"]
        + audit_stats["temporary"]
    )

    logger.info(
        "========== Завершение meteor: перемещено=%d, FTP загружено=%d, "
        "ошибок операций=%d, замечаний аудита=%d ==========",
        sort_stats["moved"],
        ftp_stats["downloaded"],
        operational_errors,
        archive_issues,
    )

    # Ненулевой код сообщает о сбоях операций или о файлах, требующих проверки.
    return 1 if operational_errors or archive_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
