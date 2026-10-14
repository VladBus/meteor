"""Unit-тесты локальной логики meteor; FTP и сетевой диск не нужны."""

import logging
import tempfile
import unittest
from datetime import date
from pathlib import Path

from main import (
    DEFAULT_FILE_GLOB,
    audit_archive,
    destination_path_for_file,
    filename_matches,
    parse_acquisition_date,
    sort_existing_files,
)

SAMPLE = "METM24_20261005t030639_13488_1_1_BRLK_RLI_log10.tif"


class FilenameTests(unittest.TestCase):
    """Проверка разбора имён файлов и определения дат."""

    def test_parse_acquisition_date(self) -> None:
        """Дата извлекается из имени стандартного снимка."""
        self.assertEqual(parse_acquisition_date(SAMPLE), date(2026, 10, 5))

    def test_invalid_calendar_date_is_rejected(self) -> None:
        """Несуществующая календарная дата не принимается."""
        self.assertIsNone(
            parse_acquisition_date(
                "METM24_20261345t030639_13488_1_1_BRLK_RLI_log10.tif"
            )
        )

    def test_unexpected_filename_is_rejected(self) -> None:
        """Имя другого формата не даёт дату съёмки."""
        self.assertIsNone(parse_acquisition_date("unrelated_image.tif"))

    def test_file_glob_matches_tif_and_tiff(self) -> None:
        """Основная маска принимает оба расширения TIFF."""
        self.assertTrue(filename_matches(SAMPLE, DEFAULT_FILE_GLOB))
        self.assertTrue(
            filename_matches(SAMPLE.removesuffix(".tif") + ".tiff", DEFAULT_FILE_GLOB)
        )
        self.assertFalse(filename_matches("METM24_20261005.tif", DEFAULT_FILE_GLOB))

    def test_target_path_uses_iso_week_folder(self) -> None:
        """Снимок 5 октября помещается в каталог ISO-недели 41."""
        root = Path("Z:/ENVISAT/METEOP")
        self.assertEqual(
            destination_path_for_file(root, SAMPLE),
            root / "2026" / "W41_2026-10-05_2026-10-11",
        )

    def test_iso_week_boundaries_and_month_crossing(self) -> None:
        """Проверяются недели, пересекающие месяцы и календарные годы."""
        root = Path("archive")
        test_cases = [
            ("20260928", "2026", "W40_2026-09-28_2026-10-04"),
            ("20260930", "2026", "W40_2026-09-28_2026-10-04"),
            ("20261001", "2026", "W40_2026-09-28_2026-10-04"),
            ("20261004", "2026", "W40_2026-09-28_2026-10-04"),
            ("20261005", "2026", "W41_2026-10-05_2026-10-11"),
            ("20261011", "2026", "W41_2026-10-05_2026-10-11"),
            ("20261012", "2026", "W42_2026-10-12_2026-10-18"),
            ("20261231", "2026", "W53_2026-12-28_2027-01-03"),
            ("20270101", "2026", "W53_2026-12-28_2027-01-03"),
            ("20270104", "2027", "W01_2027-01-04_2027-01-10"),
        ]
        for date_text, expected_year, expected_week in test_cases:
            with self.subTest(date=date_text):
                filename = (
                    f"METM24_{date_text}t030639_13488_1_1_BRLK_RLI_log10.tif"
                )
                target = destination_path_for_file(root, filename)
                if target is None:
                    raise AssertionError(
                        f"Destination path was not created for {filename}"
                    )
                self.assertEqual(target.parent.name, expected_week)
                self.assertEqual(target.parent.parent.name, expected_year)


class LocalSortingTests(unittest.TestCase):
    """Проверка безопасной сортировки локальных файлов."""

    def setUp(self) -> None:
        """Создаёт временный каталог для независимого теста."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.logger = logging.getLogger("meteor.tests")
        self.logger.addHandler(logging.NullHandler())

    def tearDown(self) -> None:
        """Удаляет временный каталог после теста."""
        self.temp_dir.cleanup()

    def test_misplaced_file_is_moved_to_iso_week_folder(self) -> None:
        """Снимок из старой месячной структуры перемещается в ISO-неделю."""
        source = self.root / "2026" / "10" / "05" / SAMPLE
        source.parent.mkdir(parents=True)
        source.write_bytes(b"test TIFF data")
        expected = self.root / "2026" / "W41_2026-10-05_2026-10-11" / SAMPLE

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(expected.is_file())
        self.assertFalse(source.exists())
        self.assertEqual(stats["moved"], 1)
        self.assertGreaterEqual(stats["empty_dirs_removed"], 1)

    def test_second_sort_is_idempotent(self) -> None:
        """Повторная сортировка не перемещает уже правильно размещённый файл."""
        target = self.root / "2026" / "W41_2026-10-05_2026-10-11" / SAMPLE
        target.parent.mkdir(parents=True)
        target.write_bytes(b"test TIFF data")

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(target.is_file())
        self.assertEqual(stats["moved"], 0)
        self.assertEqual(stats["already_sorted"], 1)

    def test_name_collision_does_not_delete_source(self) -> None:
        """При конфликте имён исходный и архивный файлы сохраняются."""
        source = self.root / "unsorted" / SAMPLE
        target = self.root / "2026" / "W41_2026-10-05_2026-10-11" / SAMPLE
        source.parent.mkdir(parents=True)
        target.parent.mkdir(parents=True)
        source.write_bytes(b"original")
        target.write_bytes(b"archived")

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(source.exists())
        self.assertEqual(target.read_bytes(), b"archived")
        self.assertEqual(stats["duplicates"], 1)

    def test_unmatched_file_is_untouched_and_audited(self) -> None:
        """Посторонний файл отмечается аудитом, но не удаляется."""
        source = self.root / "unexpected.txt"
        source.write_text("keep this file", encoding="utf-8")

        stats = audit_archive(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(source.exists())
        self.assertEqual(stats["unexpected"], 1)

    def test_tiff_extension_is_sorted(self) -> None:
        """Снимок с расширением .tiff также переносится в ISO-неделю."""
        filename = SAMPLE.removesuffix(".tif") + ".tiff"
        source = self.root / filename
        source.write_bytes(b"test TIFF data")
        expected = self.root / "2026" / "W41_2026-10-05_2026-10-11" / filename

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(expected.is_file())
        self.assertEqual(stats["moved"], 1)

    def test_audit_detects_misplaced_snapshot(self) -> None:
        """Аудит отмечает снимок вне каталога его ISO-недели."""
        wrong_path = self.root / "2026" / "10" / "05" / SAMPLE
        wrong_path.parent.mkdir(parents=True)
        wrong_path.write_bytes(b"test TIFF data")

        stats = audit_archive(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertEqual(stats["misplaced"], 1)


if __name__ == "__main__":
    unittest.main()
