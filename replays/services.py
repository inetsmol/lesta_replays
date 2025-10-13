"""
replays/services.py
Сервисы для обработки реплеев.
"""
from __future__ import annotations

import json
import logging
import datetime
from pathlib import Path
from typing import Any, List, Iterable
from typing import Optional, Tuple

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from replays.models import Replay, Tank, Player, Map
from replays.parser.extractor import ExtractorV2
from replays.parser.parser import Parser

logger = logging.getLogger(__name__)


class FileStorageService:
    """Сервис для работы с файловой системой."""

    @staticmethod
    def save_file(uploaded_file) -> Path:
        """
        Сохраняет загруженный файл в MEDIA_ROOT.
        Если файл с таким именем уже существует, то к имени файла добавляется временная метка.

        Args:
            uploaded_file: Загруженный файл

        Returns:
            Path: Путь к сохранённому файлу
        """
        files_dir = Path(settings.MEDIA_ROOT)
        files_dir.mkdir(parents=True, exist_ok=True)

        original_name = uploaded_file.name
        file_path = files_dir / original_name

        if file_path.exists():
            stem = Path(original_name).stem
            suffix = Path(original_name).suffix
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            new_name = f"{stem}_{timestamp}{suffix}"
            file_path = files_dir / new_name
            uploaded_file.name = new_name  # Важно обновить имя файла

        with open(file_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        return file_path

    @staticmethod
    def delete_file(file_path: Path) -> None:
        """Удаляет файл из файловой системы."""
        if file_path and file_path.exists():
            file_path.unlink(missing_ok=True)


class GameVersionExtractor:
    """Извлекает версию игры из payload."""

    @staticmethod
    def extract(payload) -> str:
        """
        Извлекает версию игры из payload.

        Args:
            payload: Данные реплея в формате [{...}, [...]] или JSON-строка

        Returns:
            str: Версия игры или 'Unknown'
        """
        if not payload:
            return 'Unknown'

        # Если payload - строка JSON, парсим её
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Не удалось распарсить payload как JSON: {e}")
                return 'Unknown'

        # Проверяем структуру
        if not isinstance(payload, (list, tuple)) or len(payload) == 0:
            logger.warning(f"Некорректная структура payload: ожидается список, получен {type(payload)}")
            return 'Unknown'

        # Первый элемент должен быть словарем
        first_element = payload[0]
        if not isinstance(first_element, dict):
            logger.warning(f"Первый элемент payload не является словарем: {type(first_element)}")
            return 'Unknown'

        return first_element.get('clientVersionFromExe', 'Unknown')


class TankService:
    """Сервис для работы с танками."""

    @staticmethod
    def get_or_create_tank(tank_tag: Optional[str]) -> Optional[Tank]:
        """
        Находит существующий танк или создаёт заглушку.

        Args:
            tank_tag: Идентификатор танка

        Returns:
            Tank | None: Объект танка или None
        """
        if not tank_tag:
            logger.warning("Tank tag отсутствует")
            return None

        try:
            return Tank.objects.get(vehicleId=tank_tag)
        except Tank.DoesNotExist:
            logger.warning(f"Танк {tank_tag} не найден, создаём заглушку")
            return Tank.objects.create(
                vehicleId=tank_tag,
                name=f"Неизвестный танк ({tank_tag})",
                level=1,
                type="unknown"
            )


class PlayerService:
    """Сервис для работы с игроками."""

    @staticmethod
    def get_or_update_player(
            owner_name: str,
            owner_real_name: Optional[str],
            owner_clan: Optional[str]
    ) -> Player:
        """
        Получает или создает игрока, обновляя его данные при необходимости.

        Args:
            owner_name: Имя игрока
            owner_real_name: Реальное имя
            owner_clan: Клан

        Returns:
            Player: Объект игрока
        """
        player, created = Player.objects.get_or_create(
            name=owner_name,
            defaults={
                'real_name': owner_real_name,
                'clan_tag': owner_clan
            }
        )

        if not created:
            updated_fields = []

            if owner_real_name and player.real_name != owner_real_name:
                player.real_name = owner_real_name
                updated_fields.append('real_name')

            if owner_clan and player.clan_tag != owner_clan:
                player.clan_tag = owner_clan
                updated_fields.append('clan_tag')

            if updated_fields:
                player.save(update_fields=updated_fields)
                logger.info(f"Обновлены данные игрока {owner_name}: {', '.join(updated_fields)}")

        return player


class MapService:
    """Сервис для работы с картами."""

    @staticmethod
    def get_or_create_map(map_name: str, map_display_name: Optional[str]) -> Map:
        """
        Получает или создает карту.

        Args:
            map_name: Системное имя карты
            map_display_name: Отображаемое имя карты

        Returns:
            Map: Объект карты
        """
        map_obj, _ = Map.objects.get_or_create(
            map_name=map_name,
            defaults={'map_display_name': map_display_name}
        )
        return map_obj


class ReplayProcessingService:
    """Основной сервис обработки реплеев."""

    MAX_DESCRIPTION_LEN = 60

    def __init__(self):
        self.file_storage = FileStorageService()
        self.game_version_extractor = GameVersionExtractor()
        self.tank_service = TankService()
        self.player_service = PlayerService()
        self.map_service = MapService()

    @transaction.atomic
    def process_replay(self, uploaded_file, description: str = '', user=None) -> Replay:
        """
        Обрабатывает файл реплея и создаёт объект Replay.

        Args:
            uploaded_file: Загруженный файл
            description: Описание реплея

        Returns:
            Replay: Созданный объект реплея

        Raises:
            ValidationError: При ошибках валидации или обработки
        """
        file_path = None

        try:
            # Шаг 1: Сохранение файла
            file_path = self.file_storage.save_file(uploaded_file)

            # Шаг 2: Парсинг данных
            parser = Parser()
            data = parser.parse(file_path)

            # Шаг 3: Извлечение полей
            replay_fields = ExtractorV2.extract_replay_fields_v2(data, uploaded_file.name)

            # Шаг 4: Извлечение метаданных
            payload = replay_fields.get('payload')
            game_version = self.game_version_extractor.extract(payload)

            # Шаг 5: Получение связанных объектов
            tank = self.tank_service.get_or_create_tank(replay_fields.get('tank_tag'))
            owner = self._get_or_update_owner(payload)
            map_obj = self.map_service.get_or_create_map(
                map_name=replay_fields.get('map_name'),
                map_display_name=replay_fields.get('map_display_name')
            )

            # Шаг 6: Создание реплея
            replay = self._create_replay(
                user=user,
                replay_fields=replay_fields,
                payload=payload,
                tank=tank,
                owner=owner,
                map_obj=map_obj,
                game_version=game_version,
                description=description
            )

            # Шаг 7: Привязка игроков
            self._attach_players_to_replay(replay, payload)

            logger.info(f"Реплей создан: {replay.id} - {uploaded_file.name}")
            return replay

        except (json.JSONDecodeError, ValueError) as e:
            self.file_storage.delete_file(file_path)
            logger.error(f"Ошибка обработки реплея {uploaded_file.name}: {e}")
            raise ValidationError(f"Ошибка обработки файла реплея: {str(e)}")

        except Exception as e:
            self.file_storage.delete_file(file_path)
            logger.error(f"Неожиданная ошибка при обработке {uploaded_file.name}: {e}")
            raise

    def _get_or_update_owner(self, payload) -> Player:
        """Получает или обновляет владельца реплея."""
        owner_name, owner_real_name, owner_clan = ExtractorV2.get_replay_owner_from_payload(payload)
        return self.player_service.get_or_update_player(owner_name, owner_real_name, owner_clan)

    def _attach_players_to_replay(self, replay: Replay, payload) -> None:
        """
        Создаёт/обновляет игроков и прикрепляет их к реплею (M2M).
        """
        player_objs = self._upsert_players_from_payload(payload)
        if player_objs:
            replay.participants.add(*player_objs)

    @transaction.atomic
    def _upsert_players_from_payload(self, payload) -> List[Player]:
        """
        Создаёт/обновляет игроков по данным из payload и возвращает список объектов Player.

        Поиск ведётся по уникальному Player.name (логин).
        При нахождении записи обновляются real_name и clan_tag, если пришли непустые и отличаются.
        """
        # Ожидаем, что парсер вернёт коллекцию игроков (dicts/tuples/strings)
        raw_players: Iterable[Any] = ExtractorV2.parse_players_payload(payload) or []
        players: List[Player] = []

        for raw in raw_players:
            login, real_name, clan_tag = _extract_triplet(raw)
            if not login:
                # пропускаем мусор без логина — иначе упрёмся в UNIQUE(name)
                continue

            obj, created = Player.objects.get_or_create(
                name=login,
                defaults={"real_name": real_name, "clan_tag": clan_tag},
            )

            to_update = []
            if not created:
                # мягкие обновления (только если пришло непустое и отличается)
                if real_name and obj.real_name != real_name:
                    obj.real_name = real_name
                    to_update.append("real_name")
                if clan_tag and obj.clan_tag != clan_tag:
                    obj.clan_tag = clan_tag
                    to_update.append("clan_tag")
                if to_update:
                    obj.save(update_fields=to_update)

            players.append(obj)

        return players

    def _create_replay(
            self,
            replay_fields: dict,
            payload,
            tank: Optional[Tank],
            owner: Player,
            map_obj: Map,
            game_version: str,
            description: str,
            user=None
    ) -> Replay:
        """Создает объект Replay."""
        return Replay.objects.create(
            user=user,
            file_name=replay_fields.get('file_name'),
            payload=payload,
            tank=tank,
            owner=owner,
            battle_date=replay_fields.get('battle_date'),
            map=map_obj,
            mastery=replay_fields.get('mastery'),
            credits=replay_fields.get('credits', 0),
            xp=replay_fields.get('xp', 0),
            kills=replay_fields.get('kills', 0),
            damage=replay_fields.get('damage', 0),
            assist=replay_fields.get('assist', 0),
            block=replay_fields.get('block', 0),
            game_version=game_version,
            battle_type=replay_fields.get('battle_type'),
            gameplay_id=replay_fields.get('gameplay_id'),
            short_description=(description or '')[:self.MAX_DESCRIPTION_LEN],
        )


def _norm_str(raw: str | None) -> str:
    return (raw or "").strip()


def _norm_clan(raw: str | None) -> str:
    # В реплеях бывает "[TAG]" или "tag" — приводим к "TAG"
    return (raw or "").strip("[] ").upper()


def _extract_triplet(item: Any) -> Tuple[str, str, str]:
    """
    Унифицируем результат парсера игроков.
    Возвращает (login_name, real_name, clan_tag).
    Поддерживает:
      - dict с ключами 'name' / 'login', 'realName', 'clanAbbrev'
      - tuple длиной 3: (name, real_name, clan_tag)
      - tuple длиной 2: (name, clan_tag)  -> real_name = name
      - строку: 'name'                    -> real_name = name, clan=''
    """
    if isinstance(item, dict):
        login = _norm_str(item.get("name") or item.get("login"))
        real = _norm_str(item.get("realName"))
        clan = _norm_clan(item.get("clanAbbrev"))
        if not login and real:
            # иногда realName = отображаемый ник, используем его как логин если login пуст
            login = real
        return login, real or login, clan

    if isinstance(item, (list, tuple)):
        if len(item) == 3:
            login, real, clan = item
            return _norm_str(login), _norm_str(real) or _norm_str(login), _norm_clan(clan)
        if len(item) == 2:
            login, clan = item
            login = _norm_str(login)
            return login, login, _norm_clan(clan)

    # последний случай — строка
    login = _norm_str(str(item) if item is not None else "")
    return login, login, ""






