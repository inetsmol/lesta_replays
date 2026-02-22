"""
replays/services.py
Сервисы для обработки реплеев.
"""
from __future__ import annotations

import json
import logging
import datetime
import hashlib
from pathlib import Path
from typing import Any, List, Dict
from typing import Optional, Tuple
from datetime import timezone as dt_timezone

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from replays.models import (
    Replay, Tank, Player, Map, Achievement,
    SubscriptionPlan, UserSubscription, DailyUsage, ReplayVideoLink, ReplayStatBattle, ReplayStatPlayer,
)
from replays.parser.extractor import ExtractorV2
from replays.parser.parser import Parser, ParseError
from replays.parser.replay_cache import ReplayDataCache

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

    @staticmethod
    def move_to_directory(file_path: Path, subdir: str) -> Path:
        """
        Переносит файл в поддиректорию внутри MEDIA_ROOT.

        Args:
            file_path: исходный путь к файлу
            subdir: имя поддиректории внутри MEDIA_ROOT

        Returns:
            Path: новый путь к файлу
        """
        if not file_path:
            return file_path

        target_dir = Path(settings.MEDIA_ROOT) / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / file_path.name
        if target_path.exists():
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            target_path = target_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"

        file_path.rename(target_path)
        return target_path


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
            account_id: int,
            real_name: str,
            fake_name: str,
            clan_tag: str
    ) -> Player:
        """
        Получает или обновляет игрока по accountDBID.

        ВАЖНО: Игрок идентифицируется по accountDBID - уникальному ID из БД Lesta/WG.
        Если игрок найден, обновляются его имена и клан.

        Args:
            account_id: Уникальный ID игрока (accountDBID)
            real_name: Настоящее имя игрока (players.realName)
            fake_name: Имя в бою (players.name, анонимное если скрыто)
            clan_tag: Клан игрока

        Returns:
            Player: Объект игрока
        """
        player, created = Player.objects.update_or_create(
            accountDBID=account_id,
            defaults={
                "real_name": real_name,
                "fake_name": fake_name,
                "clan_tag": clan_tag or '',
            }
        )

        if created:
            logger.debug(f"Создан владелец реплея: {player}")
        else:
            logger.debug(f"Обновлён владелец реплея: {player}")

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
    UNSUPPORTED_VERSION_DIR = "unsupported_version_replays"

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
            # Шаг 1: Чтение файла в память
            uploaded_file.seek(0)  # На всякий случай сбрасываем указатель
            file_content = uploaded_file.read()

            # Шаг 2: Парсинг данных из памяти
            parser = Parser()
            data = parser.parse_bytes(file_content)

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

            # Шаг 5.1: Проверка на дубликат (ДО сохранения файла)
            battle_date = replay_fields.get('battle_date')
            if Replay.objects.filter(owner=owner, battle_date=battle_date, tank=tank).exists():
                logger.info(
                    f"Дубликат реплея отклонён: {uploaded_file.name} "
                    f"(owner={owner.real_name}, date={battle_date}, tank={tank.vehicleId})"
                )
                raise ValidationError("Такой реплей уже существует в базе данных.")

            # Шаг 6: Сохранение файла (только если НЕ дубликат)
            uploaded_file.seek(0)  # Сбрасываем указатель перед сохранением
            file_path = self.file_storage.save_file(uploaded_file)

            # ВАЖНО: Обновляем file_name в replay_fields РЕАЛЬНЫМ именем файла после сохранения
            # (файл мог быть переименован, если такое имя уже существовало)
            replay_fields['file_name'] = file_path.name

            # Шаг 7: Создание реплея
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

            # Шаг 8: Привязка игроков
            self._attach_players_to_replay(replay, payload)

            # Шаг 9: Привязка достижений
            self._attach_achievements_to_replay(replay, payload)

            logger.info(f"Реплей создан: {replay.id} - {uploaded_file.name}")
            return replay

        except ParseError as e:
            # ParseError означает, что файл не содержит статистику боя
            # Не сохраняем такие файлы, сразу отклоняем
            logger.info(f"Реплей отклонён (нет статистики боя): {uploaded_file.name}")
            raise

        except ValidationError as e:
            # ValidationError - это ожидаемые ошибки (дубликаты и т.п.)
            # Не удаляем файл, т.к. он еще не сохранён (проверка дубликатов ДО сохранения)
            # Не логируем как error - это нормальная ситуация
            logger.debug(f"Реплей отклонён (validation): {uploaded_file.name} - {e}")
            raise

        except (json.JSONDecodeError, ValueError) as e:
            if file_path:
                self.file_storage.delete_file(file_path)
            logger.error(f"Ошибка обработки реплея {uploaded_file.name}: {e}")
            raise ValidationError(f"Ошибка обработки файла реплея: {str(e)}")

        except Exception as e:
            if file_path:
                self.file_storage.delete_file(file_path)
            logger.error(f"Неожиданная ошибка при обработке {uploaded_file.name}: {e}")
            raise

    def _get_or_update_owner(self, payload) -> Player:
        """Получает или обновляет владельца реплея."""
        owner_data = ExtractorV2.get_replay_owner_from_payload(payload)
        return self.player_service.get_or_update_player(
            account_id=owner_data["accountDBID"],
            real_name=owner_data["real_name"],
            fake_name=owner_data["fake_name"],
            clan_tag=owner_data["clan_tag"]
        )

    def _attach_players_to_replay(self, replay: Replay, payload) -> None:
        """
        Создаёт/обновляет игроков и прикрепляет их к реплею (M2M).
        """
        player_objs = self._upsert_players_from_payload(payload)
        if player_objs:
            replay.participants.add(*player_objs)

    def _attach_achievements_to_replay(self, replay: Replay, payload) -> None:
        """Извлекает достижения из payload и привязывает к реплею (M2M)."""
        ach_ids = ExtractorV2.get_achievements(payload)
        if not ach_ids:
            return

        achievements = Achievement.objects.filter(achievement_id__in=ach_ids)
        if achievements:
            replay.achievements.set(achievements)
            replay.achievement_count = achievements.count()
            replay.save(update_fields=['achievement_count'])

    @transaction.atomic
    def _upsert_players_from_payload(self, payload) -> List[Player]:
        """
        Создаёт/обновляет игроков по данным из payload и возвращает список объектов Player.

        Поиск ведётся по accountDBID - уникальному ID игрока в БД Lesta/WG.
        Если игрок найден, обновляются его имена и клан.
        """
        # Парсер возвращает список словарей с полями: accountDBID, real_name, fake_name, clan_tag
        raw_players: List[Dict[str, Any]] = ExtractorV2.parse_players_payload(payload) or []
        players: List[Player] = []

        for player_data in raw_players:
            account_id = player_data.get("accountDBID")
            if not account_id:
                logger.warning(f"Игрок без accountDBID: {player_data}")
                continue

            real_name = player_data.get("real_name", "")
            fake_name = player_data.get("fake_name", "")
            clan_tag = player_data.get("clan_tag", "")

            if not real_name:
                logger.warning(f"Игрок {account_id} без real_name, пропускаем")
                continue

            # Поиск/создание/обновление по accountDBID
            obj, created = Player.objects.update_or_create(
                accountDBID=account_id,
                defaults={
                    "real_name": real_name,
                    "fake_name": fake_name,
                    "clan_tag": clan_tag,
                }
            )

            if created:
                logger.debug(f"Создан новый игрок: {obj}")
            else:
                logger.debug(f"Обновлён игрок: {obj}")

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
            is_alive=replay_fields.get('is_alive'),
            battle_duration=replay_fields.get('battle_duration'),
            is_platoon=replay_fields.get('is_platoon'),
            game_version=game_version,
            battle_type=replay_fields.get('battle_type'),
            gameplay_id=replay_fields.get('gameplay_id'),
            short_description=(description or '')[:self.MAX_DESCRIPTION_LEN],
        )


class ReplayStatsProcessingService:
    """Сервис обработки .mtreplay только для статистики (без сохранения файла/payload)."""

    OUTCOME_MAP = {
        "victory": ReplayStatBattle.OUTCOME_WIN,
        "defeat": ReplayStatBattle.OUTCOME_LOSS,
        "draw": ReplayStatBattle.OUTCOME_DRAW,
    }

    def __init__(self):
        self.tank_service = TankService()

    @transaction.atomic
    def process_replay(self, uploaded_file, user) -> Dict[str, int]:
        """
        Обрабатывает файл реплея в памяти и сохраняет статистику по всем союзникам.

        Returns:
            Dict[str, int]:
                created_rows: количество новых строк
                duplicate_rows: количество дубликатов
                total_rows: всего обработано строк игроков
        """
        uploaded_file.seek(0)
        file_content = uploaded_file.read()

        parser = Parser()
        replay_data = parser.parse_bytes(file_content)
        replay_fields = ExtractorV2.extract_replay_fields_v2(replay_data, uploaded_file.name)

        cache = ReplayDataCache(replay_data)
        owner_data = ExtractorV2.get_replay_owner_from_payload(replay_data)

        owner_account_id = self._extract_player_account_id(replay_fields, owner_data)
        owner_player_name = self._extract_player_name(cache, owner_data)
        battle_date = replay_fields.get("battle_date")
        arena_unique_id = self._extract_arena_unique_id(cache)
        outcome = self._extract_outcome(cache)
        battle_signature = self._build_battle_signature(
            player_account_id=owner_account_id,
            battle_date=battle_date,
            tank_tag=self._extract_owner_tank_tag(cache),
            arena_unique_id=arena_unique_id,
        )

        players_rows = self._extract_allied_players_rows(
            cache=cache,
            owner_account_id=owner_account_id,
            owner_player_name=owner_player_name,
            replay_fields=replay_fields,
            outcome=outcome,
            battle_signature=battle_signature,
            battle_date=battle_date,
            arena_unique_id=arena_unique_id,
        )

        battle_obj, _ = ReplayStatBattle.objects.get_or_create(
            user=user,
            battle_signature=battle_signature,
            defaults={
                "battle_date": battle_date,
                "map_name": replay_fields.get("map_name") or "",
                "map_display_name": replay_fields.get("map_display_name") or "",
                "outcome": outcome,
                "arena_unique_id": arena_unique_id,
            },
        )

        created_rows = 0
        duplicate_rows = 0
        for row in players_rows:
            player_obj, created = ReplayStatPlayer.objects.get_or_create(
                battle=battle_obj,
                player_account_id=row["player_account_id"],
                defaults={
                    "player_name": row["player_name"],
                    "tank": row["tank"],
                    "tank_tag": row["tank_tag"],
                    "tank_name": row["tank_name"],
                    "damage": row["damage"],
                    "xp": row["xp"],
                    "kills": row["kills"],
                    "assist": row["assist"],
                    "block": row["block"],
                },
            )
            if created:
                created_rows += 1
            else:
                # Если запись уже существует, но статистика пустая (старые нули),
                # аккуратно обновляем её новыми значениями.
                existing_is_empty = (
                    int(player_obj.damage or 0) == 0
                    and int(player_obj.xp or 0) == 0
                    and int(player_obj.kills or 0) == 0
                    and int(player_obj.assist or 0) == 0
                    and int(player_obj.block or 0) == 0
                )
                incoming_has_values = (
                    int(row["damage"] or 0) > 0
                    or int(row["xp"] or 0) > 0
                    or int(row["kills"] or 0) > 0
                    or int(row["assist"] or 0) > 0
                    or int(row["block"] or 0) > 0
                )

                update_fields: List[str] = []
                if existing_is_empty and incoming_has_values:
                    player_obj.damage = int(row["damage"] or 0)
                    player_obj.xp = int(row["xp"] or 0)
                    player_obj.kills = int(row["kills"] or 0)
                    player_obj.assist = int(row["assist"] or 0)
                    player_obj.block = int(row["block"] or 0)
                    update_fields.extend(["damage", "xp", "kills", "assist", "block"])

                if not player_obj.tank_id and row["tank"] is not None:
                    player_obj.tank = row["tank"]
                    update_fields.append("tank")
                if not player_obj.tank_tag and row["tank_tag"]:
                    player_obj.tank_tag = row["tank_tag"]
                    update_fields.append("tank_tag")
                if not player_obj.tank_name and row["tank_name"]:
                    player_obj.tank_name = row["tank_name"]
                    update_fields.append("tank_name")
                if (
                    (not player_obj.player_name or player_obj.player_name.startswith("Player "))
                    and row["player_name"]
                ):
                    player_obj.player_name = row["player_name"]
                    update_fields.append("player_name")

                if update_fields:
                    player_obj.save(update_fields=update_fields)

                duplicate_rows += 1

        return {
            "created_rows": created_rows,
            "duplicate_rows": duplicate_rows,
            "total_rows": len(players_rows),
        }

    @staticmethod
    def _extract_player_account_id(replay_fields: dict, owner_data: dict) -> int:
        value = replay_fields.get("player_id") or owner_data.get("accountDBID")
        try:
            account_id = int(value)
        except (TypeError, ValueError):
            account_id = 0

        if account_id <= 0:
            raise ValidationError("Не удалось определить account_id автора реплея.")
        return account_id

    @staticmethod
    def _extract_player_name(cache: ReplayDataCache, owner_data: dict) -> str:
        return (
            owner_data.get("real_name")
            or owner_data.get("fake_name")
            or cache.first_block.get("playerName")
            or "Unknown"
        )

    @staticmethod
    def _normalize_tank_tag(raw_value: Any) -> str:
        if not isinstance(raw_value, str):
            return ""
        if ":" in raw_value:
            return raw_value.split(":", 1)[1]
        if "-" in raw_value:
            return raw_value.split("-", 1)[1]
        return raw_value.strip()

    @staticmethod
    def _normalize_team(raw_value: Any) -> Optional[int]:
        """Нормализует номер команды из int/str к int."""
        if isinstance(raw_value, int):
            return raw_value
        if isinstance(raw_value, str):
            stripped = raw_value.strip()
            if stripped.isdigit():
                return int(stripped)
        return None

    def _extract_owner_tank_tag(self, cache: ReplayDataCache) -> str:
        return self._normalize_tank_tag(cache.first_block.get("playerVehicle"))

    @staticmethod
    def _calculate_assist(personal_data: dict) -> int:
        return int(
            (personal_data.get('damageAssistedRadio') or 0)
            + (personal_data.get('damageAssistedTrack') or 0)
            + (personal_data.get('damageAssistedStun') or 0)
            + (personal_data.get('damageAssistedSmoke') or 0)
            + (personal_data.get('damageAssistedInspire') or 0)
        )

    @staticmethod
    def _extract_xp(stats_data: dict) -> int:
        """
        Извлекает XP из разных форматов статистики (personal/vehicles).
        Приоритет: originalXP -> subtotalXP -> (xp - achievementXP) -> xp.
        """
        if not isinstance(stats_data, dict):
            return 0

        if stats_data.get("originalXP") is not None:
            return int(stats_data.get("originalXP") or 0)
        if stats_data.get("subtotalXP") is not None:
            return int(stats_data.get("subtotalXP") or 0)

        xp = int(stats_data.get("xp") or 0)
        achievement_xp = int(stats_data.get("achievementXP") or 0)
        if xp > 0 and achievement_xp > 0:
            return max(0, xp - achievement_xp)
        return xp

    @staticmethod
    def _stats_quality_score(stats_data: dict) -> int:
        """
        Оценивает, насколько словарь похож на боевую статистику игрока.
        Нужен для выбора между personal/vehicles и отсечения avatar-блока.
        """
        if not isinstance(stats_data, dict):
            return 0

        score = 0
        # Ключевые поля боевой статистики.
        for key in (
            "damageDealt",
            "kills",
            "damageBlockedByArmor",
            "damageAssistedRadio",
            "damageAssistedTrack",
            "deathReason",
            "shots",
            "directHits",
            "spotted",
            "details",
        ):
            if key in stats_data:
                score += 2

        # Поля, которые есть почти везде, но полезны как дополнительный сигнал.
        for key in ("team", "xp", "originalXP", "accountDBID"):
            if key in stats_data:
                score += 1

        return score

    def _pick_best_stats(self, personal_stats: dict, vehicle_stats: dict) -> Dict[str, Any]:
        """
        Выбирает лучший источник статистики:
        - обычно personal (боевой),
        - но если personal похож на avatar-блок, берем vehicles.
        """
        personal_score = self._stats_quality_score(personal_stats)
        vehicle_score = self._stats_quality_score(vehicle_stats)

        if vehicle_score > personal_score:
            return vehicle_stats or {}
        return personal_stats or vehicle_stats or {}

    @staticmethod
    def _build_vehicle_stats_by_account(first_result: dict) -> Dict[int, Dict[str, Any]]:
        """
        Строит индекс accountDBID -> vstats из секции second_block[0]['vehicles'].
        """
        stats_by_account: Dict[int, Dict[str, Any]] = {}
        vehicles_root = first_result.get("vehicles", {}) if isinstance(first_result, dict) else {}
        if not isinstance(vehicles_root, dict):
            return stats_by_account

        for vehicle_stats in vehicles_root.values():
            if isinstance(vehicle_stats, list):
                candidates = vehicle_stats
            elif isinstance(vehicle_stats, dict):
                candidates = [vehicle_stats]
            else:
                continue

            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                account_raw = candidate.get("accountDBID")
                try:
                    account_id = int(account_raw)
                except (TypeError, ValueError):
                    continue
                if account_id <= 0:
                    continue
                # Берем запись с большим количеством полей как более полную.
                current = stats_by_account.get(account_id)
                if current is None or len(candidate) > len(current):
                    stats_by_account[account_id] = candidate

        return stats_by_account

    def _build_vehicle_tag_map(self, cache: ReplayDataCache) -> Dict[str, str]:
        vehicle_tag_map: Dict[str, str] = {}
        for raw in cache.extended_vehicle_info.values():
            if not isinstance(raw, dict):
                continue
            tank_tag = self._normalize_tank_tag(raw.get("vehicleType"))
            if not tank_tag:
                continue
            for key in ("name", "fakeName"):
                player_name = raw.get(key)
                if isinstance(player_name, str) and player_name.strip():
                    vehicle_tag_map[player_name.strip()] = tank_tag
        return vehicle_tag_map

    def _extract_allied_players_rows(
            self,
            cache: ReplayDataCache,
            owner_account_id: int,
            owner_player_name: str,
            replay_fields: dict,
            outcome: str,
            battle_signature: str,
            battle_date,
            arena_unique_id: Optional[int],
    ) -> List[Dict[str, Any]]:
        first_result = cache.second_block[0] if cache.second_block else {}
        players_data = first_result.get("players", {}) if isinstance(first_result, dict) else {}
        personal_root = first_result.get("personal", {}) if isinstance(first_result, dict) else {}

        owner_team = cache.player_team
        if owner_team is None:
            owner_player = players_data.get(str(owner_account_id)) or players_data.get(owner_account_id)
            if isinstance(owner_player, dict):
                owner_team = self._normalize_team(owner_player.get("team"))
        else:
            owner_team = self._normalize_team(owner_team)

        personal_by_account: Dict[int, Dict[str, Any]] = {}
        if isinstance(personal_root, dict):
            if "accountDBID" in personal_root:
                try:
                    personal_by_account[int(personal_root.get("accountDBID"))] = personal_root
                except (TypeError, ValueError):
                    pass
            for value in personal_root.values():
                if isinstance(value, dict) and "accountDBID" in value:
                    try:
                        account_id = int(value.get("accountDBID"))
                    except (TypeError, ValueError):
                        continue
                    if account_id <= 0:
                        continue

                    current = personal_by_account.get(account_id)
                    if current is None:
                        personal_by_account[account_id] = value
                    else:
                        # Не даем avatar-подобному блоку перезаписать боевой personal.
                        if self._stats_quality_score(value) > self._stats_quality_score(current):
                            personal_by_account[account_id] = value

        vehicle_stats_by_account = self._build_vehicle_stats_by_account(first_result)
        vehicle_tag_map = self._build_vehicle_tag_map(cache)
        owner_tank_tag = self._extract_owner_tank_tag(cache)

        rows: List[Dict[str, Any]] = []
        for account_id_raw, player_data in players_data.items():
            if not isinstance(player_data, dict):
                continue

            try:
                account_id = int(account_id_raw)
            except (TypeError, ValueError):
                continue

            player_team = self._normalize_team(player_data.get("team"))
            if owner_team is not None and player_team != owner_team:
                continue

            personal_stats = personal_by_account.get(account_id)
            vehicle_stats = vehicle_stats_by_account.get(account_id)
            stats_data = self._pick_best_stats(personal_stats, vehicle_stats)
            player_name = (
                (player_data.get("realName") or "").strip()
                or (player_data.get("name") or "").strip()
                or (owner_player_name if account_id == owner_account_id else f"Player {account_id}")
            )

            if account_id == owner_account_id:
                tank_tag = replay_fields.get("tank_tag") or owner_tank_tag
            else:
                tank_tag = (
                    vehicle_tag_map.get(player_name)
                    or vehicle_tag_map.get((player_data.get("name") or "").strip())
                    or ""
                )

            tank = self.tank_service.get_or_create_tank(tank_tag) if tank_tag else None
            tank_name = tank.name if tank else tank_tag

            rows.append({
                "player_account_id": account_id,
                "player_name": player_name,
                "battle_date": battle_date,
                "map_name": replay_fields.get("map_name") or "",
                "map_display_name": replay_fields.get("map_display_name") or "",
                "tank": tank,
                "tank_tag": tank_tag,
                "tank_name": tank_name,
                "outcome": outcome,
                "damage": int(stats_data.get("damageDealt") or 0),
                "xp": self._extract_xp(stats_data),
                "kills": int(stats_data.get("kills") or 0),
                "assist": self._calculate_assist(stats_data),
                "block": int(stats_data.get("damageBlockedByArmor") or 0),
                "arena_unique_id": arena_unique_id,
                "battle_signature": battle_signature,
            })

        if not rows:
            # fallback: хотя бы владелец реплея
            owner_tank_tag = replay_fields.get("tank_tag") or owner_tank_tag
            owner_tank = self.tank_service.get_or_create_tank(owner_tank_tag) if owner_tank_tag else None
            rows.append({
                "player_account_id": owner_account_id,
                "player_name": owner_player_name,
                "battle_date": battle_date,
                "map_name": replay_fields.get("map_name") or "",
                "map_display_name": replay_fields.get("map_display_name") or "",
                "tank": owner_tank,
                "tank_tag": owner_tank_tag,
                "tank_name": owner_tank.name if owner_tank else owner_tank_tag,
                "outcome": outcome,
                "damage": int(replay_fields.get("damage") or 0),
                "xp": int(replay_fields.get("xp") or 0),
                "kills": int(replay_fields.get("kills") or 0),
                "assist": int(replay_fields.get("assist") or 0),
                "block": int(replay_fields.get("block") or 0),
                "arena_unique_id": arena_unique_id,
                "battle_signature": battle_signature,
            })

        return rows

    def _extract_outcome(self, cache: ReplayDataCache) -> str:
        outcome_data = ExtractorV2.get_battle_outcome(cache)
        status_class = outcome_data.get("status_class", "")
        return self.OUTCOME_MAP.get(status_class, ReplayStatBattle.OUTCOME_DRAW)

    @staticmethod
    def _extract_arena_unique_id(cache: ReplayDataCache) -> Optional[int]:
        raw_value = cache.common.get("arenaUniqueID")
        if raw_value in (None, ""):
            raw_value = cache.first_block.get("arenaUniqueID")
        try:
            return int(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_battle_signature(
            player_account_id: int,
            battle_date,
            tank_tag: str,
            arena_unique_id: Optional[int],
    ) -> str:
        if arena_unique_id:
            raw_signature = f"arena:{arena_unique_id}"
        else:
            if battle_date is None:
                raise ValidationError("Не удалось определить дату боя для дедупликации.")
            if battle_date.tzinfo is None:
                battle_key = battle_date.isoformat()
            else:
                battle_key = battle_date.astimezone(dt_timezone.utc).isoformat()
            raw_signature = f"fallback:{player_account_id}:{battle_key}:{tank_tag}"

        return hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()


class SubscriptionService:
    """Сервис для работы с подписками."""

    @staticmethod
    def get_user_plan(user) -> SubscriptionPlan:
        """Получить текущий план пользователя (или бесплатный по умолчанию)."""
        if not user or not user.is_authenticated:
            return SubscriptionService._get_free_plan()

        try:
            sub = user.subscription
            if sub.is_valid:
                return sub.plan
        except UserSubscription.DoesNotExist:
            pass

        return SubscriptionService._get_free_plan()

    @staticmethod
    def is_premium(user) -> bool:
        """Проверяет, есть ли у пользователя Премиум или выше."""
        plan = SubscriptionService.get_user_plan(user)
        return plan.name in (SubscriptionPlan.PLAN_PREMIUM, SubscriptionPlan.PLAN_PRO)

    @staticmethod
    def is_pro(user) -> bool:
        """Проверяет, есть ли у пользователя план Про."""
        plan = SubscriptionService.get_user_plan(user)
        return plan.name == SubscriptionPlan.PLAN_PRO

    @staticmethod
    def activate_subscription(user, plan_name: str, days: int = 30, activated_by: str = 'admin'):
        """Активировать подписку пользователю."""
        from django.utils import timezone

        plan = SubscriptionPlan.objects.get(name=plan_name)
        expires_at = None
        if plan_name != SubscriptionPlan.PLAN_FREE:
            expires_at = timezone.now() + datetime.timedelta(days=days)

        sub, created = UserSubscription.objects.update_or_create(
            user=user,
            defaults={
                'plan': plan,
                'expires_at': expires_at,
                'is_active': True,
                'activated_by': activated_by,
            },
        )
        return sub

    @staticmethod
    def _get_free_plan() -> SubscriptionPlan:
        return SubscriptionPlan.objects.get(name=SubscriptionPlan.PLAN_FREE)


class UsageLimitService:
    """Сервис для проверки и учёта дневных лимитов."""

    @staticmethod
    def _get_or_create_today(user) -> DailyUsage:
        from django.utils import timezone
        today = timezone.now().date()
        usage, _ = DailyUsage.objects.get_or_create(user=user, date=today)
        return usage

    @staticmethod
    def can_upload(user) -> bool:
        """Может ли пользователь загрузить ещё один реплей сегодня."""
        plan = SubscriptionService.get_user_plan(user)
        if plan.daily_upload_limit == 0:
            return True
        usage = UsageLimitService._get_or_create_today(user)
        return usage.uploads < plan.daily_upload_limit

    @staticmethod
    def can_download(user) -> bool:
        """Может ли пользователь скачать ещё один реплей сегодня."""
        plan = SubscriptionService.get_user_plan(user)
        if plan.daily_download_limit == 0:
            return True
        usage = UsageLimitService._get_or_create_today(user)
        return usage.downloads < plan.daily_download_limit

    @staticmethod
    def record_upload(user):
        """Записать факт загрузки."""
        usage = UsageLimitService._get_or_create_today(user)
        usage.uploads = models.F('uploads') + 1
        usage.save(update_fields=['uploads'])

    @staticmethod
    def record_download(user):
        """Записать факт скачивания."""
        usage = UsageLimitService._get_or_create_today(user)
        usage.downloads = models.F('downloads') + 1
        usage.save(update_fields=['downloads'])

    @staticmethod
    def get_remaining(user) -> dict:
        """Получить остаток загрузок/скачиваний."""
        plan = SubscriptionService.get_user_plan(user)
        usage = UsageLimitService._get_or_create_today(user)

        upload_limit = plan.daily_upload_limit
        download_limit = plan.daily_download_limit

        return {
            'uploads_remaining': None if upload_limit == 0 else max(0, upload_limit - usage.uploads),
            'downloads_remaining': None if download_limit == 0 else max(0, download_limit - usage.downloads),
            'uploads_limit': upload_limit if upload_limit > 0 else None,
            'downloads_limit': download_limit if download_limit > 0 else None,
        }


class VideoLinkService:
    """Сервис для работы с видео-ссылками к реплеям."""

    @staticmethod
    def can_add_video(user, replay) -> bool:
        """Может ли пользователь добавить видео к этому реплею."""
        plan = SubscriptionService.get_user_plan(user)
        if plan.max_video_links == 0:
            return False
        current_count = ReplayVideoLink.objects.filter(replay=replay, added_by=user).count()
        return current_count < plan.max_video_links

    @staticmethod
    def add_video_link(user, replay, platform: str, url: str) -> ReplayVideoLink:
        """Добавить видео-ссылку к реплею."""
        return ReplayVideoLink.objects.create(
            replay=replay,
            platform=platform,
            url=url,
            added_by=user,
        )

    @staticmethod
    def get_video_links(replay):
        """Получить все видео-ссылки реплея."""
        return ReplayVideoLink.objects.filter(replay=replay).select_related('added_by')


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
