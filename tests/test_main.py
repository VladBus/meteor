"""Unit-тесты локальной логики meteor; FTP и сетевой диск не нужны."""

import logging
import tempfile
import unittest
from datetime import date
from pathlib import Path

from main import (
    DEFAULT_FILE_GLOB,
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

    def test_file_glob_matches_sample(self) -> None:
        """Маска выбирает снимки BRLK требуемого формата."""
        self.assertTrue(filename_matches(SAMPLE, DEFAULT_FILE_GLOB))
        self.assertFalse(filename_matches("METM24_20261005.tif", DEFAULT_FILE_GLOB))

    def test_target_path_uses_year_month_day(self) -> None:
        """Целевой путь содержит отдельные каталоги года, месяца и дня."""
        root = Path("Z:/ENVISAT/METEOP")
        self.assertEqual(
            destination_path_for_file(root, SAMPLE),
            root / "2026" / "10" / "05" / SAMPLE,
        )


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

    def test_misplaced_file_is_moved_and_then_is_idempotent(self) -> None:
        """Перемещённый файл при следующей проверке не переносится снова."""
        source = self.root / "unsorted" / SAMPLE
        source.parent.mkdir(parents=True)
        source.write_bytes(b"test TIFF data")
        expected = self.root / "2026" / "10" / "05" / SAMPLE

        first = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)
        self.assertTrue(expected.is_file())
        self.assertFalse(source.exists())
        self.assertEqual(first["moved"], 1)

        second = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)
        self.assertTrue(expected.is_file())
        self.assertEqual(second["moved"], 0)
        self.assertEqual(second["already_sorted"], 1)

    def test_name_collision_does_not_delete_source(self) -> None:
        """При конфликте имён исходный и архивный файлы сохраняются."""
        source = self.root / "unsorted" / SAMPLE
        target = self.root / "2026" / "10" / "05" / SAMPLE
        source.parent.mkdir(parents=True)
        target.parent.mkdir(parents=True)
        source.write_bytes(b"original")
        target.write_bytes(b"archived")

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(source.exists())
        self.assertEqual(target.read_bytes(), b"archived")
        self.assertEqual(stats["duplicates"], 1)

    def test_unmatched_file_is_untouched(self) -> None:
        """Файлы вне маски не перемещаются."""
        source = self.root / "image.tif"
        source.write_bytes(b"not a BRLK image")

        stats = sort_existing_files(self.root, DEFAULT_FILE_GLOB, self.logger)

        self.assertTrue(source.exists())
        self.assertEqual(stats["moved"], 0)
        self.assertEqual(stats["errors"], 0)


if __name__ == "__main__":
    unittest.main()
