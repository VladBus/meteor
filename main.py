"""
Загрузка оперативных снимков БРЛК «Метеор-М» с FTP и сортировка архива по дате съёмки.

Скрипт выполняет один цикл обработки и завершается. Его запуск по расписанию
предполагается настроить в Планировщике заданий Windows.
"""

from __future__ import annotations

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
    """Проверяет имя файла по маске без учёта регистра."""
    return fnmatch.fnmatchcase(filename.casefold(), file_glob.casefold())


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
    """Формирует путь архива YYYY\\MM\\DD по дате в имени файла."""
    acquisition_date = parse_acquisition_date(filename)
    if acquisition_date is None:
        return None

    return (
        dest_root
        / f"{acquisition_date.year:04d}"
        / f"{acquisition_date.month:02d}"
        / f"{acquisition_date.day:02d}"
        / filename
    )


def sort_existing_files(
    dest_root: Path,
    file_glob: str,
    logger: logging.Logger,
) -> dict[str, int]:
    """
    Ищет подходящие TIFF во всём архиве и исправляет их расположение.
    При конфликте имён не удаляет исходный файл и не перезаписывает архивный.
    """
    stats = {
        "moved": 0,
        "already_sorted": 0,
        "duplicates": 0,
        "unrecognized": 0,
        "errors": 0,
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
        "Проверка локального архива: найдено подходящих файлов — %d",
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
            logger.info("Отсортирован: %s -> %s", source, target)
            stats["moved"] += 1
        except OSError:
            logger.exception("Ошибка при сортировке файла: %s", source)
            stats["errors"] += 1

    logger.info(
        "Локальная сортировка завершена: перемещено=%d, уже на месте=%d, "
        "дубликатов=%d, без даты=%d, ошибок=%d",
        stats["moved"],
        stats["already_sorted"],
        stats["duplicates"],
        stats["unrecognized"],
        stats["errors"],
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
    Загружает файлы по заданной маске в датированные каталоги.
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
                        logger.warning("Не удалось удалить временный файл: %s", part_path)

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
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, OSError, UnicodeError):
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

    total_errors = sort_stats["errors"] + ftp_stats["errors"]
    logger.info(
        "========== Завершение meteor: локально перемещено=%d, "
        "FTP загружено=%d, ошибок=%d ==========",
        sort_stats["moved"],
        ftp_stats["downloaded"],
        total_errors,
    )

    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
