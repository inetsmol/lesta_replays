"""
Обработчики ошибок для загрузки реплеев.
"""
import json
import logging
from typing import Dict, Any

from django.core.exceptions import ValidationError

from replays.models import Tank

logger = logging.getLogger(__name__)

SUPPORT_EMAIL = "inetsmol@gmail.com"
SUPPORT_TELEGRAM = "@inetsmol"


class ErrorMessageFormatter:
    """Форматирует сообщения об ошибках для пользователя."""

    # Список ошибок, которые безопасно показывать пользователю
    USER_FRIENDLY_ERRORS = [
        "Реплей с таким именем уже существует в базе",
        "Такой реплей уже существует в базе данных.",
        "Файл с таким именем уже загружен",
        "не содержит статистику боя",
        "Неподдерживаемый формат",
        "Файл слишком большой",
        "Файл слишком мал",
    ]

    @classmethod
    def get_user_message(cls, error: Exception, error_type: str = "general") -> str:
        """
        Возвращает понятное пользователю сообщение об ошибке.

        Args:
            error: Исключение
            error_type: Тип ошибки

        Returns:
            str: Сообщение для пользователя
        """
        error_message = str(error)

        # Проверяем ValidationError
        if isinstance(error, ValidationError):
            error_message = cls._extract_validation_error(error)

        # Проверяем, безопасно ли показывать ошибку
        if cls._is_user_friendly_error(error_message):
            return error_message

        # Для остальных ошибок возвращаем заглушку
        return cls._get_technical_error_message()

    @classmethod
    def _is_user_friendly_error(cls, error_message: str) -> bool:
        """Проверяет, является ли ошибка безопасной для показа пользователю."""
        error_lower = error_message.lower()
        return any(safe_error.lower() in error_lower for safe_error in cls.USER_FRIENDLY_ERRORS)

    @classmethod
    def _extract_validation_error(cls, validation_error: ValidationError) -> str:
        """Извлекает читаемое сообщение из ValidationError."""
        if hasattr(validation_error, 'message_dict'):
            messages = []
            for field, errors in validation_error.message_dict.items():
                field_name = field if field != '__all__' else 'Общая ошибка'
                if isinstance(errors, list):
                    for err in errors:
                        messages.append(f"{field_name}: {err}")
                else:
                    messages.append(f"{field_name}: {str(errors)}")
            return '; '.join(messages)

        if hasattr(validation_error, 'messages'):
            if isinstance(validation_error.messages, list):
                return '; '.join(str(m) for m in validation_error.messages)
            return str(validation_error.messages)

        return str(validation_error)

    @staticmethod
    def _get_technical_error_message() -> str:
        """Возвращает заглушку для технических ошибок."""
        return (
            f"Произошла техническая ошибка при обработке файла. "
            f"Мы работаем над исправлением. Пожалуйста, сообщите нам: "
            f"{SUPPORT_EMAIL} или {SUPPORT_TELEGRAM}"
        )


class ReplayErrorHandler:
    """Обработчик ошибок при загрузке реплеев."""

    def __init__(self):
        self.formatter = ErrorMessageFormatter()

    def handle_error(self, error: Exception, file_name: str) -> Dict[str, Any]:
        """
        Обрабатывает ошибку и возвращает структурированный результат.

        Args:
            error: Исключение
            file_name: Имя файла

        Returns:
            dict: Результат с информацией об ошибке
        """
        error_type = self._get_error_type(error)

        # Логируем ошибку
        self._log_error(error, file_name, error_type)

        # Формируем сообщение для пользователя
        user_message = self.formatter.get_user_message(error, error_type)

        return {
            "ok": False,
            "error": user_message,
            "file": file_name
        }

    @staticmethod
    def _get_error_type(error: Exception) -> str:
        """Определяет тип ошибки."""
        if isinstance(error, ValidationError):
            return "validation"
        if isinstance(error, json.JSONDecodeError):
            return "json_parse"
        if isinstance(error, KeyError):
            return "missing_field"
        if isinstance(error, Tank.DoesNotExist):
            return "tank_not_found"
        return "unknown"

    @staticmethod
    def _log_error(error: Exception, file_name: str, error_type: str) -> None:
        """Логирует ошибку с соответствующим уровнем."""
        log_message = f"[BATCH] Ошибка ({error_type}) при обработке '{file_name}': {error}"

        if error_type in ("validation", "json_parse"):
            logger.warning(log_message)
        else:
            logger.error(log_message, exc_info=True)