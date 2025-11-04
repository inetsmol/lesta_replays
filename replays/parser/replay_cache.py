"""
Кеширование данных реплея для оптимизации производительности.

Этот модуль предоставляет класс ReplayDataCache, который кеширует
часто используемые данные из payload реплея, чтобы избежать повторного
парсинга JSON и многократных обращений к структуре данных.

Использование:
    cache = ReplayDataCache(replay.payload)
    personal_data = cache.personal
    common_data = cache.common
"""

import json
import logging
from typing import Any, Dict, Optional, Mapping

logger = logging.getLogger(__name__)


class ReplayDataCache:
    """
    Кеширует часто используемые данные из payload для предотвращения
    повторного парсинга и обращений к структуре данных.

    Структура payload: [metadata, battle_results, vehicles_copy, frags]
    - payload[0] - метаданные (playerName, playerID, dateTime, ...)
    - payload[1] - результаты боя и статистика
        - payload[1][0] - словарь с 'common', 'personal', 'players', 'vehicles'
        - payload[1][1] - словарь аватаров {avatarId: {...}}

    Attributes:
        payload: Полные данные реплея
        first_block: Метаданные реплея (payload[0])
        second_block: Результаты боя (payload[1])

    Properties:
        player_id: ID текущего игрока (владельца реплея)
        common: Общие данные боя
        personal: Персональные данные текущего игрока
        players: Словарь всех игроков боя
        vehicles: Статистика техники всех игроков
        avatars: Информация об аватарах игроков
        player_team: Номер команды текущего игрока
    """

    def __init__(self, payload: Any):
        """
        Инициализирует кеш данных реплея.

        Args:
            payload: JSON-строка или уже распарсенный payload реплея

        Raises:
            ValueError: Если структура payload некорректна
        """
        # Парсим JSON только один раз
        if isinstance(payload, (str, bytes, bytearray)):
            try:
                self.payload = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON payload: {e}")
                raise ValueError(f"Некорректный JSON payload: {e}")
        else:
            self.payload = payload

        # Валидация структуры
        if not isinstance(self.payload, (list, tuple)) or len(self.payload) < 2:
            raise ValueError(
                f"Некорректная структура payload: ожидается [metadata, battle_results, ...], "
                f"получен {type(self.payload)}"
            )

        # Извлекаем основные блоки один раз
        self.first_block: Dict[str, Any] = self.payload[0]
        self.second_block: Any = self.payload[1]

        # Валидация первого блока
        if not isinstance(self.first_block, dict):
            raise ValueError(
                f"Первый блок payload должен быть словарём, получен {type(self.first_block)}"
            )

        # Валидация второго блока
        if not isinstance(self.second_block, (list, tuple)) or len(self.second_block) < 2:
            raise ValueError(
                f"Второй блок payload должен быть списком из 2+ элементов, "
                f"получен {type(self.second_block)}"
            )

        # Кеш для ленивой загрузки
        self._common: Optional[Dict[str, Any]] = None
        self._personal: Optional[Dict[str, Any]] = None
        self._players: Optional[Dict[str, Any]] = None
        self._vehicles: Optional[Dict[str, Any]] = None
        self._avatars: Optional[Dict[str, Any]] = None
        self._player_id: Optional[int] = None
        self._player_team: Optional[int] = None

        logger.debug(f"ReplayDataCache инициализирован для игрока {self.player_id}")

    @property
    def player_id(self) -> Optional[int]:
        """
        ID текущего игрока (владельца реплея).

        Returns:
            ID игрока или None, если не найден
        """
        if self._player_id is None:
            self._player_id = self.first_block.get("playerID")
        return self._player_id

    @property
    def common(self) -> Dict[str, Any]:
        """
        Общие данные боя (winnerTeam, finishReason, duration, etc).

        Returns:
            Словарь с общими данными или пустой словарь
        """
        if self._common is None:
            if isinstance(self.second_block, (list, tuple)) and len(self.second_block) > 0:
                first_result = self.second_block[0]
                if isinstance(first_result, dict):
                    self._common = first_result.get('common', {})
                else:
                    logger.warning(f"second_block[0] не является словарём: {type(first_result)}")
                    self._common = {}
            else:
                logger.warning("second_block пустой или некорректный")
                self._common = {}
        return self._common

    @property
    def personal(self) -> Dict[str, Any]:
        """
        Персональные данные текущего игрока (xp, credits, kills, damage, etc).

        Поддерживает две структуры:
        1. Плоская: {"accountDBID": 12345, "xp": 1000, ...}
        2. Вложенная: {typeCompDescr: {"accountDBID": 12345, ...}}

        Returns:
            Словарь с персональными данными или пустой словарь
        """
        if self._personal is None:
            if isinstance(self.second_block, (list, tuple)) and len(self.second_block) > 0:
                first_result = self.second_block[0]
                if isinstance(first_result, dict):
                    personal = first_result.get('personal', {})
                    if isinstance(personal, dict):
                        # Ищем данные текущего игрока
                        player_id = self.player_id
                        if player_id is not None:
                            # Проверяем плоскую структуру
                            if "accountDBID" in personal and personal.get("accountDBID") == player_id:
                                self._personal = personal
                            else:
                                # Ищем по ключам (может быть typeCompDescr или строковый ID)
                                for key, value in personal.items():
                                    if isinstance(value, dict) and value.get("accountDBID") == player_id:
                                        self._personal = value
                                        break

            if self._personal is None:
                logger.warning(f"Не удалось найти персональные данные для игрока {self.player_id}")
                self._personal = {}

        return self._personal

    @property
    def players(self) -> Dict[str, Any]:
        """
        Словарь всех игроков боя {accountDBID: player_data}.

        Структура player_data:
            {
                "name": "PlayerName",
                "realName": "DisplayName",
                "clanAbbrev": "CLAN",
                "team": 1,
                ...
            }

        Returns:
            Словарь игроков или пустой словарь
        """
        if self._players is None:
            if isinstance(self.second_block, (list, tuple)) and len(self.second_block) > 0:
                first_result = self.second_block[0]
                if isinstance(first_result, dict):
                    self._players = first_result.get('players', {})
                else:
                    logger.warning(f"second_block[0] не является словарём")
                    self._players = {}
            else:
                logger.warning("second_block пустой")
                self._players = {}
        return self._players

    @property
    def vehicles(self) -> Dict[str, Any]:
        """
        Статистика техники всех игроков боя {avatarId: [vehicle_stats]}.

        Структура vehicle_stats:
            {
                "accountDBID": 12345,
                "shots": 10,
                "damageDealt": 1500,
                "kills": 2,
                ...
            }

        Returns:
            Словарь статистики техники или пустой словарь
        """
        if self._vehicles is None:
            if isinstance(self.second_block, (list, tuple)) and len(self.second_block) > 0:
                first_result = self.second_block[0]
                if isinstance(first_result, dict):
                    self._vehicles = first_result.get('vehicles', {})
                else:
                    logger.warning(f"second_block[0] не является словарём")
                    self._vehicles = {}
            else:
                logger.warning("second_block пустой")
                self._vehicles = {}
        return self._vehicles

    @property
    def avatars(self) -> Dict[str, Any]:
        """
        Информация об аватарах игроков (второй уровень second_block).

        Структура: {avatarId: {"vehicleType": "...", "team": 1, "name": "...", ...}}

        Returns:
            Словарь аватаров или пустой словарь
        """
        if self._avatars is None:
            if isinstance(self.second_block, (list, tuple)) and len(self.second_block) > 1:
                second_level = self.second_block[1]
                if isinstance(second_level, dict):
                    self._avatars = second_level
                else:
                    logger.warning(f"second_block[1] не является словарём: {type(second_level)}")
                    self._avatars = {}
            else:
                logger.warning("second_block не содержит второго уровня")
                self._avatars = {}
        return self._avatars

    @property
    def avatar_data(self) -> Dict[str, Any]:
        """
        Данные аватара текущего игрока из блока personal['avatar'].

        Эти данные содержат итоговые значения с аккаунта игрока после боя
        (credits, xp, gold на аккаунте), в отличие от personal[player_id],
        которые содержат детали конкретного боя.

        Returns:
            Словарь с данными аватара или пустой словарь
        """
        if isinstance(self.second_block, (list, tuple)) and len(self.second_block) > 0:
            first_result = self.second_block[0]
            if isinstance(first_result, dict):
                personal_root = first_result.get('personal', {})
                if isinstance(personal_root, dict):
                    avatar = personal_root.get('avatar', {})
                    if isinstance(avatar, dict):
                        return avatar
                    else:
                        logger.warning(f"personal['avatar'] не является словарём: {type(avatar)}")

        logger.warning("Не удалось получить данные avatar")
        return {}

    @property
    def player_team(self) -> Optional[int]:
        """
        Номер команды текущего игрока (1 или 2).

        Проверяет сначала в personal, затем в players.

        Returns:
            Номер команды или None, если не найден
        """
        if self._player_team is None:
            # Пробуем из personal
            team = self.personal.get("team")
            if isinstance(team, int):
                self._player_team = team
            else:
                # Пробуем из players
                player_id = self.player_id
                if player_id is not None:
                    player_info = self.players.get(str(player_id)) or self.players.get(player_id)
                    if isinstance(player_info, dict):
                        team = player_info.get("team")
                        if isinstance(team, int):
                            self._player_team = team

            if self._player_team is None:
                logger.warning(f"Не удалось определить команду для игрока {self.player_id}")

        return self._player_team

    def get_details(self) -> Dict[str, Any]:
        """
        Детальная статистика взаимодействий текущего игрока с противниками.

        Структура: {
            "(avatarId, 0)": {
                "spotted": 1,
                "damageDealt": 500,
                "crits": 3,
                "targetKills": 1,
                ...
            },
            ...
        }

        Returns:
            Словарь детальной статистики или пустой словарь
        """
        return self.personal.get("details", {})

    def get_achievements(self) -> list:
        """
        Список ID достижений текущего игрока.

        Returns:
            Список ID достижений (может быть пустым)
        """
        return list(self.personal.get("achievements") or [])

    def __repr__(self) -> str:
        """Строковое представление объекта для отладки."""
        return (
            f"<ReplayDataCache player_id={self.player_id} team={self.player_team} "
            f"achievements={len(self.get_achievements())}>"
        )
