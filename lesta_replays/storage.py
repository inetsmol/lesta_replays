"""
Кастомное хранилище статики для обработки динамических путей
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Whitenoise хранилище, которое не падает при динамических путях к статике.
    Для несуществующих файлов возвращает оригинальный путь без хеширования.
    """

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        """
        Переопределяем метод, чтобы не падать при динамической конкатенации.
        Если файл не найден - возвращаем оригинальное имя.
        """
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            # Файл не найден в манифесте или не существует
            # Возвращаем оригинальный путь
            return name