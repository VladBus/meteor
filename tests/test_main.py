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
        """Основная маска принимает оба распространённых расширения TIFF."""
        self.assertTrue(filename_matches(SAMPLE, DEFAULT_FILE_GLOB))
        self.assertTrue(
            filename_matches(SAMPLE.removesuffix(".tif") + ".tiff", DEFAULT_FILE_GLOB)
        )
        self.assertFalse(filename_matches("METM24_20261005.tif", DEFAULT_FILE_GLOB))

    def test_target_path_uses_week_bucket(self) -> None:
        """5 октября попадает в недельный интервал 01-07."""
        root = Path("Z:/ENVISAT/METEOP")
        self.assertEqual(
            destination_path_for_file(root, SAMPLE),
            root / "2026" / "10" / "01-07" / SAMPLE,
        )

    def test_week_bucket_boundaries(self) -> None:
        """Проверяются границы семидневных интервалов внутри месяца."""
        root = Path("archive")
        test_cases = [
            ("20261001", "01-07"),
            ("20261007", "01-07"),
            ("20261008", "08-14"),
            ("20261014", "08-14"),
            ("20261015", "15-21"),
            ("20261022", "22-28"),
            ("20261028", "22-28"),
            ("20261029", "29-31"),
            ("20261031", "29-31"),
            ("20260430", "29-30"),
        ]
        for date_text, expected_bucket in test_cases:
            with self.subTest(date=date_text):
                filename = (
                    f"METM24_{date_text}t030639_13488_1_1_BRLK_RLI_log10.tif"
                )
                target = destination_path_for_file(root, filename)
                self.assertIsNotNone(target)
                self.assertEqual(target.parent.name, expected_bucket)


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

    def test_misplaced_file_is_moved_to_week_bucket(self) -> None:
        """Снимок из старой структуры переносится в недельный каталог."""
        source = self.root / "2026" / "10" / "05" / SAMPLE
        source.parent.mkdir(parents=True)
        source.write_bytes(b"test TIFF data")
        expected = self.root / "2026" / "10" / "01-07" / SAMPLE

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(expected.is_file())
        self.assertFalse(source.exists())
        self.assertEqual(stats["moved"], 1)
        self.assertGreaterEqual(stats["empty_dirs_removed"], 1)

    def test_second_sort_is_idempotent(self) -> None:
        """Повторная сортировка не перемещает уже правильно размещённый файл."""
        target = self.root / "2026" / "10" / "01-07" / SAMPLE
        target.parent.mkdir(parents=True)
        target.write_bytes(b"test TIFF data")

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(target.is_file())
        self.assertEqual(stats["moved"], 0)
        self.assertEqual(stats["already_sorted"], 1)

    def test_name_collision_does_not_delete_source(self) -> None:
        """При конфликте имён исходный и архивный файлы сохраняются."""
        source = self.root / "unsorted" / SAMPLE
        target = self.root / "2026" / "10" / "01-07" / SAMPLE
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
        """Снимок с расширением .tiff также переносится в недельный каталог."""
        filename = SAMPLE.removesuffix(".tif") + ".tiff"
        source = self.root / filename
        source.write_bytes(b"test TIFF data")
        expected = self.root / "2026" / "10" / "01-07" / filename

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(expected.is_file())
        self.assertEqual(stats["moved"], 1)

    def test_audit_detects_misplaced_snapshot(self) -> None:
        """Аудит отмечает снимок, если он остался не в недельной папке."""
        wrong_path = self.root / "2026" / "10" / "05" / SAMPLE
        wrong_path.parent.mkdir(parents=True)
        wrong_path.write_bytes(b"test TIFF data")

        stats = audit_archive(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertEqual(stats["misplaced"], 1)


if __name__ == "__main__":
    unittest.main()
