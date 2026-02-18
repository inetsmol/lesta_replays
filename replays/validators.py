"""
Валидаторы для загрузки реплеев.
"""
from typing import Optional

from replays.models import Replay


class ReplayFileValidator:
    """Валидатор файлов реплеев."""

    ALLOWED_EXTENSION = '.mtreplay'
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MIN_FILE_SIZE = 100  # байт

    @classmethod
    def validate(cls, uploaded_file) -> Optional[str]:
        """
        Валидирует файл реплея.

        Args:
            uploaded_file: Загруженный файл

        Returns:
            str | None: Сообщение об ошибке или None если валидация прошла успешно
        """
        if error := cls._validate_extension(uploaded_file.name):
            return error

        if error := cls._validate_size(uploaded_file.size):
            return error

        return None

    @classmethod
    def _validate_extension(cls, filename: str) -> Optional[str]:
        """Проверяет расширение файла."""
        if not filename.lower().endswith(cls.ALLOWED_EXTENSION):
            return f"Неподдерживаемый формат. Допустимы только файлы {cls.ALLOWED_EXTENSION}"
        return None

    @classmethod
    def _validate_size(cls, file_size: int) -> Optional[str]:
        """Проверяет размер файла."""
        if file_size > cls.MAX_FILE_SIZE:
            size_mb = file_size // (1024 * 1024)
            max_mb = cls.MAX_FILE_SIZE // (1024 * 1024)
            return f"Файл слишком большой ({size_mb}MB). Максимальный размер: {max_mb}MB"

        if file_size < cls.MIN_FILE_SIZE:
            return "Файл слишком мал или повреждён"

        return None

    @classmethod
    def _validate_uniqueness(cls, filename: str) -> Optional[str]:
        """Проверяет уникальность имени файла."""
        if Replay.objects.filter(file_name=filename).exists():
            return "Реплей с таким именем уже существует в базе"
        return None


class BatchUploadValidator:
    """Валидатор пакетной загрузки."""

    MAX_FILES_FREE = 1
    MAX_FILES_PREMIUM = 5
    MAX_TOTAL_SIZE = 30 * 1024 * 1024  # 30MB

    @classmethod
    def validate_batch(cls, files: list, is_premium: bool = False) -> Optional[str]:
        """
        Валидирует пакет файлов.

        Args:
            files: Список загруженных файлов
            is_premium: Премиум/Про пользователь (множественная загрузка)

        Returns:
            str | None: Сообщение об ошибке или None
        """
        if not files:
            return "Файлы не выбраны"

        max_files = cls.MAX_FILES_PREMIUM if is_premium else cls.MAX_FILES_FREE
        if len(files) > max_files:
            if not is_premium:
                return "Загрузка нескольких файлов одновременно доступна только с Премиум-подпиской. Загружайте по одному файлу."
            return f"Слишком много файлов. Максимум: {max_files}"

        total_size = sum(f.size for f in files)
        if total_size > cls.MAX_TOTAL_SIZE:
            max_mb = cls.MAX_TOTAL_SIZE // (1024 * 1024)
            return f"Суммарный размер слишком большой. Лимит: {max_mb}MB"

        return None