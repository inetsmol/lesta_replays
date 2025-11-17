from __future__ import annotations

import ast
import datetime as _dt
import json
import logging
import math
import re
from collections import defaultdict
from functools import lru_cache
from logging import critical

from typing import Any, Dict, List, Sequence, Tuple, Mapping, Optional, Iterable

from django.db.models.functions import Coalesce, Cast
from django.db.models import Value, FloatField
from django.utils import timezone

from replays.models import Tank
from replays.utils import summarize_credits, summarize_xp, summarize_gold

logger = logging.getLogger(__name__)


class ParserUtils:
    @staticmethod
    def _parse_battle_datetime(dt_str: str) -> _dt.datetime:
        """
        Парсит дату боя формата 'DD.MM.YYYYHH:MM:SS' в объект datetime с timezone.
        Пример: '25.08.2025 15:57:56' и '25.08.202515:57:56' (без пробела) — поддерживаем оба.
        """
        # ⚠ В некоторых реплеях между датой и временем нет пробела.
        if " " not in dt_str and len(dt_str) == 19:
            dt_str = f"{dt_str[:10]} {dt_str[10:]}"
        naive_dt = _dt.datetime.strptime(dt_str, "%d.%m.%Y %H:%M:%S")
        # Делаем datetime aware (используем текущий timezone из Django настроек)
        return timezone.make_aware(naive_dt)

    @staticmethod
    def _extract_tank_tag(player_vehicle: Any) -> str | None:
        """
        Возвращает 'tag' танка из строки вида 'uk-GB134_FV242B_Condor' -> 'GB134_FV242B_Condor'.
        Если формат неожиданный — вернёт None.
        """
        if not isinstance(player_vehicle, str):
            return None
        parts = player_vehicle.split("-", 1)
        return parts[1] if len(parts) == 2 else None

    @staticmethod
    def _iter_personal_blocks(second_block: Any):
        """
        Итератор по персональным блокам новой структуры.
        Новая структура: [{...}, {...}, ...], где каждый элемент может содержать ключ 'personal'.
        При этом 'personal' может быть:
          1) уже "плоским" словарём одного игрока (с ключом 'accountDBID'),
          2) или словарём вида { typeCompDescr: {...}, ... } — тогда надо пройтись по значениям.
        """
        if not isinstance(second_block, Sequence):
            return
        for item in second_block:
            if not isinstance(item, dict):
                continue
            p = item.get("personal")
            if isinstance(p, dict):
                # Случай 1: плоский объект одного игрока
                if "accountDBID" in p:
                    yield p
                else:
                    # Случай 2: dict по typeCompDescr -> { ... }
                    for v in p.values():
                        if isinstance(v, dict) and "accountDBID" in v:
                            yield v


class ExtractorContext:
    """
    Контекст для хранения промежуточных вычислений при работе экстрактора.

    Позволяет избежать повторных вычислений одних и тех же значений,
    например, суммарного ассиста, который используется в нескольких методах.
    """

    def __init__(self, cache: 'ReplayDataCache'):
        """
        Args:
            cache: ReplayDataCache с данными реплея
        """
        from replays.parser.replay_cache import ReplayDataCache

        self.cache = cache
        self._total_assist: Optional[int] = None

    def get_total_assist(self) -> int:
        """
        Получает суммарный ассист (с кешированием).
        Вычисляется только один раз, последующие вызовы возвращают закешированное значение.

        Returns:
            Суммарный ассист-урон
        """
        if self._total_assist is None:
            p = self.cache.personal
            assist_radio = p.get('damageAssistedRadio', 0)
            assist_track = p.get('damageAssistedTrack', 0)
            assist_stun = p.get('damageAssistedStun', 0)
            assist_smoke = p.get('damageAssistedSmoke', 0)
            assist_inspire = p.get('damageAssistedInspire', 0)

            self._total_assist = assist_radio + assist_track + assist_stun + assist_smoke + assist_inspire

        return self._total_assist


class ExtractorV2:
    @staticmethod
    def _calculate_total_assist(personal: Dict[str, Any]) -> int:
        """
        Вычисляет общую помощь в уроне (все виды ассиста).

        DEPRECATED: Используйте ExtractorContext.get_total_assist() для избежания повторных вычислений.
        """
        assist_radio = personal.get('damageAssistedRadio', 0)
        assist_track = personal.get('damageAssistedTrack', 0)
        assist_stun = personal.get('damageAssistedStun', 0)
        assist_smoke = personal.get('damageAssistedSmoke', 0)
        assist_inspire = personal.get('damageAssistedInspire', 0)

        return assist_radio + assist_track + assist_stun + assist_smoke + assist_inspire

    @staticmethod
    def _iter_personal_blocks(second_block: Any):
        """
        Итератор персональных данных во втором элементе новой структуры.

        Новая структура: [{...}, [...]]
          - второй элемент — это массив dict-ов;
          - внутри элемента ключ 'personal' может быть:
              a) сразу одним объектом игрока с 'accountDBID'
              b) словарём {typeCompDescr: {...}}, тогда берём значения().
        """
        if not isinstance(second_block, Sequence):
            return
        for item in second_block:
            if not isinstance(item, dict):
                continue
            p = item.get("personal")
            if isinstance(p, dict):
                # Случай a): один игрок
                if "accountDBID" in p:
                    yield p
                else:
                    # Случай b): map typeCompDescr -> { ... }
                    for v in p.values():
                        if isinstance(v, dict) and "accountDBID" in v:
                            yield v

    @staticmethod
    def _normalize_to_pair(replay_data: Any) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Приводит вход к паре (root_object, personal_array).

        Поддерживаем входные типы:
          - str/bytes: JSON-текст -> json.loads
          - list/tuple: ожидаем [ {...}, [...] ]
          - dict: это старая структура; падаем с понятной ошибкой

        Возвращает:
          (root: dict, personal_array: list[dict])
        """
        # --- Если пришёл сырой JSON-текст ---
        if isinstance(replay_data, (str, bytes, bytearray)):
            try:
                replay_data = json.loads(replay_data)
            except Exception as e:
                raise ValueError(f"Некорректный JSON-текст: {e}")

        # --- Ожидаем новую структуру: список из двух элементов ---
        if isinstance(replay_data, Sequence) and not isinstance(replay_data, (dict,)):
            if len(replay_data) != 2:
                raise ValueError("Ожидается новая структура вида: [{...}, [...]] (ровно 2 элемента).")
            root, second = replay_data[0], replay_data[1]
            if not isinstance(root, dict):
                raise ValueError("Первый элемент новой структуры должен быть объектом JSON (dict).")
            if not isinstance(second, Sequence):
                raise ValueError("Второй элемент новой структуры должен быть массивом JSON (list).")
            return root, list(second)

        # --- Если передали dict (старая схема) ---
        if isinstance(replay_data, dict):
            raise ValueError(
                "Передан единый dict (старая структура). Для новой версии ожидается массив из двух элементов: [{...}, [...]]."
            )

        # --- Иначе формат входа неизвестен ---
        raise ValueError("Некорректный тип данных: ожидаются JSON-строка или структура [{...}, [...]].")

    @staticmethod
    def _parse_target_avatar_id(key: str) -> Optional[str]:
        """
        Парсит строку с кортежом '(46118422, 0)' в tuple[int, int] и возвращает первый элемент как str.
        Возвращает None, если формат не соответствует ожидаемому кортежу из двух целых.
        """
        try:
            value = ast.literal_eval(key)  # безопасно парсит литералы Python
            if (isinstance(value, tuple) and len(value) == 2
                    and all(isinstance(x, int) for x in value)):
                return str(value[0])
        except (ValueError, SyntaxError):
            pass
        return None

    @staticmethod
    def get_first_block(payload):
        # Парсим JSON если нужно
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)

        # Проверяем базовую структуру
        if not isinstance(payload, (list, tuple)) or len(payload) < 2:
            logger.warning(
                f"Некорректная структура payload: ожидается список из 4 элементов, получен {type(payload)}")

        return payload[0]

    @staticmethod
    def get_second_block(payload):
        # Парсим JSON если нужно
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)

        # Проверяем базовую структуру
        if not isinstance(payload, (list, tuple)) or len(payload) < 2:
            logger.warning(
                f"Некорректная структура payload: ожидается список из 4 элементов, получен {type(payload)}")

        return payload[1]

    @staticmethod
    def get_common(payload) -> Optional[Dict[str, Any]]:

        # Извлекаем детальные данные из второго элемента
        battle_results = ExtractorV2.get_second_block(payload)

        if not isinstance(battle_results, (list, tuple)) or len(battle_results) == 0:
            logger.warning("Второй элемент payload пустой или некорректный")

        # Получаем словарь игроков
        first_result = battle_results[0]
        if not isinstance(first_result, dict):
            logger.warning("Первый элемент battle_results не является словарем")

        return first_result.get('common')

    @staticmethod
    def get_personal_by_player_id(payload) -> Optional[Dict[str, Any]]:
        """
        Вернуть блок personal для указанного игрока.
        - payload[1][0]['personal'] - данные игрока

        :param payload: Единый словарь реплея (payload).
        :return: dict с персональными данными игрока или None.
        """
        battle_results = ExtractorV2.get_second_block(payload)

        if not isinstance(battle_results, (list, tuple)) or len(battle_results) == 0:
            logger.warning("Второй элемент payload пустой или некорректный")

        # Получаем словарь игроков
        first_result = battle_results[0]
        if not isinstance(first_result, dict):
            logger.warning("Первый элемент battle_results не является словарем")

        personal = first_result.get('personal')
        if not isinstance(personal, dict) or not personal:
            logger.warning("Ключ 'personal' отсутствует или не является словарем")
            return None

            # Ищем первый числовой ключ в порядке следования
        first_numeric_key = None
        for k in personal.keys():
            if isinstance(k, int):
                first_numeric_key = k
                break
            if isinstance(k, str) and k.isdigit():
                first_numeric_key = k
                break

        if first_numeric_key is None:
            logger.warning("В 'personal' нет числовых ключей")
            return None

        return personal[first_numeric_key]

    @staticmethod
    def extract_replay_fields_v2(replay_data: Any, file_name: str) -> Dict[str, Any]:
        """
        Извлекает поля для модели Replay согласно НОВОЙ структуре: [{...}, [...]].

        Args:
            replay_data : JSON-строка или уже распарсенный объект.
                          Должен соответствовать структуре: [{...}, [...]].
            file_name   : Имя файла реплея.

        Returns:
            Dict[str, Any]: Поля для создания объекта Replay.

        Raises:
            ValueError: Если структура некорректна или не найдены персональные данные игрока.
        """
        # 1) Нормализуем вход: получаем (root, personal_array)
        root, personal_array = ExtractorV2._normalize_to_pair(replay_data)

        # 2) Базовые поля
        player_name = root.get("playerName")
        player_id = root.get("playerID")
        if player_id is None:
            raise ValueError("В метаданных отсутствует 'playerID' (первый объект новой структуры).")

        tank_tag = ParserUtils._extract_tank_tag(root.get("playerVehicle"))

        dt_raw = root.get("dateTime")
        if not isinstance(dt_raw, str):
            raise ValueError("В метаданных отсутствует строковое поле 'dateTime'.")
        battle_date = ParserUtils._parse_battle_datetime(dt_raw)

        map_name = root.get("mapName")
        map_display_name = root.get("mapDisplayName")

        # 3) Ищем персональные данные текущего игрока во втором элементе
        personal_data = None
        for p in ExtractorV2._iter_personal_blocks(personal_array):
            if p.get("accountDBID") == player_id:
                personal_data = p
                break

        if not personal_data:
            raise ValueError(f"Не найдены персональные данные для игрока {player_name} (id={player_id}).")

        # 4) Сформировать результат
        fields: Dict[str, Any] = {
            "file_name": file_name,
            "payload": replay_data,
            "tank_tag": tank_tag,
            "mastery": personal_data.get("markOfMastery"),
            "battle_date": battle_date,
            "map_name": map_name,
            "map_display_name": map_display_name,
            "gameplay_id": root.get("gameplayID"),
            "battle_type": root.get("battleType"),
            "credits": personal_data.get("originalCredits", 0),
            "xp": personal_data.get("originalXP", 0),
            "kills": personal_data.get("kills", 0),
            "damage": personal_data.get("damageDealt", 0),
            "assist": ExtractorV2._calculate_total_assist(personal_data),
            "block": personal_data.get("damageBlockedByArmor", 0),
        }
        return fields

    @staticmethod
    def parse_players_payload(payload) -> List[Tuple[str, str]]:
        """
        Достаёт из payload кортежи (nickname, clan_tag).
        Структура payload: [metadata, [battle_results], vehicles_copy, frags]
        - payload[0] - метаданные с playerName и playerID
        - payload[1][0]['players'] - словарь игроков {accountDBID: {name, realName, clanAbbrev, ...}}

        Возвращает список без пустых/битых записей, без дублей.
        """

        try:
            # Парсим JSON если нужно
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)

            # Проверяем базовую структуру
            if not isinstance(payload, (list, tuple)) or len(payload) < 2:
                logger.warning(
                    f"Некорректная структура payload: ожидается список из 4 элементов, получен {type(payload)}")

            # Извлекаем детальные данные из второго элемента
            battle_results = payload[1]
            if not isinstance(battle_results, (list, tuple)) or len(battle_results) == 0:
                logger.warning("Второй элемент payload пустой или некорректный")

            # Получаем словарь игроков
            first_result = battle_results[0]
            if not isinstance(first_result, dict):
                logger.warning("Первый элемент battle_results не является словарем")

            players = first_result.get('players')

            seen: set[Tuple[str, str]] = set()
            result: List[Tuple[str, str]] = []

            # Внутри словаря ключи — любые ID; берём только значения
            for p in players.values():
                # в примерах бывают поля "name" и "realName" — берём приоритетно "name"
                nickname = (p.get("realName") or p.get("name")).strip() or ""
                if not nickname:
                    continue
                clan_tag = p.get("clanAbbrev").strip("[] ").upper() or ""

                key = (nickname, clan_tag)
                if key in seen:
                    continue
                seen.add(key)
                result.append(key)

            return result

        except Exception as e:
            logger.error(f"Неожиданная ошибка при извлечении игроков: {e}", exc_info=True)

    @staticmethod
    def get_replay_owner_from_payload(payload):
        """
        Извлекает данные владельца реплея из новой структуры.

        Структура payload: [metadata, [battle_results], vehicles_copy, frags]
        - payload[0] - метаданные с playerName и playerID
        - payload[1][0]['players'] - словарь игроков {accountDBID: {name, realName, clanAbbrev, ...}}

        Args:
            payload: Данные реплея

        Returns:
            tuple: (owner_name, owner_real_name, clan_tag) - всегда 3 значения
        """
        try:
            # Парсим JSON если нужно
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)

            # Проверяем базовую структуру
            if not isinstance(payload, (list, tuple)) or len(payload) < 2:
                logger.warning(
                    f"Некорректная структура payload: ожидается список из 4 элементов, получен {type(payload)}")
                return '', '', ''

            # Извлекаем метаданные из первого элемента
            metadata = payload[0]
            if not isinstance(metadata, dict):
                logger.warning(f"Первый элемент payload не является словарем: {type(metadata)}")
                return '', '', ''

            # Получаем базовые данные владельца
            owner_real_name = (metadata.get('playerName') or '').strip()
            player_id = metadata.get('playerID')

            if not owner_real_name:
                logger.warning("В metadata отсутствует playerName")
                return '', '', ''

            if not player_id:
                logger.warning("В metadata отсутствует playerID")
                return owner_real_name, owner_real_name, ''

            # Извлекаем детальные данные из второго элемента
            battle_results = payload[1]
            if not isinstance(battle_results, (list, tuple)) or len(battle_results) == 0:
                logger.warning("Второй элемент payload пустой или некорректный")
                return owner_real_name, owner_real_name, ''

            # Получаем словарь игроков
            first_result = battle_results[0]
            if not isinstance(first_result, dict):
                logger.warning("Первый элемент battle_results не является словарем")
                return owner_real_name, owner_real_name, ''

            players = first_result.get('players')
            if not isinstance(players, dict):
                logger.warning("Секция 'players' отсутствует или некорректна")
                return owner_real_name, owner_real_name, ''

            # Ищем данные владельца по player_id
            player_id_str = str(player_id)
            if player_id_str in players:
                player_data = players[player_id_str]
                if isinstance(player_data, dict):
                    # name - отображаемое имя (может быть fake, совпадать у разных игроков)
                    owner_name = (player_data.get('name') or owner_real_name).strip()
                    # realName - настоящее имя игрока (уникальное)
                    # Если realName пусто, значит игрок скрыл имя, используем playerName из metadata
                    owner_real_name_from_players = (player_data.get('realName') or owner_real_name).strip()
                    clan_tag = (player_data.get('clanAbbrev') or '').strip()
                    return owner_name, owner_real_name_from_players, clan_tag

            # Если не нашли по строковому ID, пробуем числовой
            if player_id in players:
                player_data = players[player_id]
                if isinstance(player_data, dict):
                    owner_name = (player_data.get('name') or owner_real_name).strip()
                    owner_real_name_from_players = (player_data.get('realName') or owner_real_name).strip()
                    clan_tag = (player_data.get('clanAbbrev') or '').strip()
                    return owner_name, owner_real_name_from_players, clan_tag

            # Не нашли в словаре игроков
            logger.info(f"Игрок {owner_real_name} (ID: {player_id}) не найден в словаре players")
            return owner_real_name, owner_real_name, ''

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON payload: {e}")
            return '', '', ''
        except Exception as e:
            logger.error(f"Неожиданная ошибка при извлечении владельца реплея: {e}", exc_info=True)
            return '', '', ''

    @staticmethod
    def get_personal_data_minimal(cache: 'ReplayDataCache') -> dict:
        """
        Возвращает ТОЛЬКО те поля из personal, которые реально используются в шаблоне detail.html.

        Вместо 60+ полей возвращаем только 3 нужных поля.
        Это существенно снижает потребление памяти и ускоряет обработку.

        Args:
            cache: ReplayDataCache с данными реплея

        Returns:
            Словарь с минимальным набором полей: credits, xp, crystal
        """
        from replays.parser.replay_cache import ReplayDataCache

        p = cache.personal

        return {
            # Только поля, которые используются в шаблоне detail.html
            'credits': int(p.get('credits', 0)),
            'xp': int(p.get('xp', 0)),
            'crystal': int(p.get('crystal', 0)),
        }

    @staticmethod
    def get_personal_data(replay_data: dict) -> dict:
        p = ExtractorV2.get_personal_by_player_id(replay_data) or {}

        # ---- помощники
        def as_dict_of_pairs(pairs):
            """[['k', v], [k2, v2]] -> {k: v}"""
            try:
                return {k: v for k, v in (pairs or [])}
            except Exception:
                return {}

        def as_tuple_or_list(val):
            return tuple(val) if isinstance(val, (list, tuple)) else val

        # ---- агрегаты по details
        details = p.get("details") or {}
        agg = defaultdict(int)
        for v in details.values():
            if not isinstance(v, dict):
                continue
            agg["details_fire"] += v.get("fire", 0)
            agg["details_crits"] += v.get("crits", 0)
            agg["details_spotted"] += v.get("spotted", 0)
            agg["details_stun_num"] += v.get("stunNum", 0)
            agg["details_direct_hits"] += v.get("directHits", 0)
            agg["details_explosion_hits"] += v.get("explosionHits", 0)
            agg["details_piercings"] += v.get("piercings", 0)
            agg["details_damage_dealt"] += v.get("damageDealt", 0)
            agg["details_damage_received"] += v.get("damageReceived", 0)
            agg["details_direct_enemy_hits"] += v.get("directEnemyHits", 0)
            agg["details_piercing_enemy_hits"] += v.get("piercingEnemyHits", 0)
            agg["details_damage_assisted_stun"] += v.get("damageAssistedStun", 0)
            agg["details_damage_assisted_radio"] += v.get("damageAssistedRadio", 0)
            agg["details_damage_assisted_smoke"] += v.get("damageAssistedSmoke", 0)
            agg["details_damage_assisted_track"] += v.get("damageAssistedTrack", 0)
            agg["details_damage_blocked_by_armor"] += v.get("damageBlockedByArmor", 0)
            agg["details_no_damage_direct_hits_received"] += v.get("noDamageDirectHitsReceived", 0)
            agg["details_rickochets_received"] += v.get("rickochetsReceived", 0)  # да, тут так пишется в сыром json
            agg["details_target_kills"] += v.get("targetKills", 0)
            # stunDuration может быть float
            try:
                agg["details_stun_duration"] += float(v.get("stunDuration", 0.0))
            except Exception:
                pass

        # ---- основная раскладка (плоские поля + удобные алиасы)
        data = {
            # командные / счётчики
            "team": p.get("team"),
            "index": p.get("index"),
            "kills": p.get("kills"),
            "tkills": p.get("tkills"),
            "shots": p.get("shots"),
            "spotted": p.get("spotted"),
            "stun_num": p.get("stunNum"),
            "life_time": p.get("lifeTime"),
            "killer_id": p.get("killerID"),
            "death_reason": p.get("deathReason"),
            "death_count": p.get("deathCount"),

            # боевые действия (итоги по верхнему уровню)
            "damage_dealt": p.get("damageDealt"),
            "damage_received": p.get("damageReceived"),
            "damage_blocked": p.get("damageBlockedByArmor"),
            "damage_assisted_radio": p.get("damageAssistedRadio"),
            "damage_assisted_track": p.get("damageAssistedTrack"),
            "damage_assisted_stun": p.get("damageAssistedStun"),
            "damage_assisted_smoke": p.get("damageAssistedSmoke"),
            "damage_assisted_inspire": p.get("damageAssistedInspire"),
            "piercings": p.get("piercings"),
            "direct_hits": p.get("directHits"),
            "explosion_hits": p.get("explosionHits"),
            "direct_enemy_hits": p.get("directEnemyHits"),
            "piercing_enemy_hits": p.get("piercingEnemyHits"),
            "direct_hits_received": p.get("directHitsReceived"),
            "no_damage_direct_hits_received": p.get("noDamageDirectHitsReceived"),
            "piercings_received": p.get("piercingsReceived"),
            "ricochets_received": p.get("rickochetsReceived"),
            "sniper_damage_dealt": p.get("sniperDamageDealt"),
            "potential_damage_received": p.get("potentialDamageReceived"),
            "destructibles_hits": p.get("destructiblesHits"),
            "destructibles_damage_dealt": p.get("destructiblesDamageDealt"),
            "destructibles_num_destroyed": p.get("destructiblesNumDestroyed"),
            "damage_assisted_inspire_total": p.get("damageAssistedInspire"),

            # экономика / валюты
            "credits": p.get("credits"),
            "original_credits": p.get("originalCredits"),
            "subtotal_credits": p.get("subtotalCredits"),
            "factual_credits": p.get("factualCredits"),
            "credits_penalty": p.get("creditsPenalty"),
            "credits_to_draw": p.get("creditsToDraw"),
            "prem_squad_credits": p.get("premSquadCredits"),
            "premium_credits_factor100": p.get("premiumCreditsFactor100"),
            "premium_plus_credits_factor100": p.get("premiumPlusCreditsFactor100"),
            "booster_credits": p.get("boosterCredits"),
            "booster_credits_factor100": p.get("boosterCreditsFactor100"),
            "gold": p.get("gold"),
            "subtotal_gold": p.get("subtotalGold"),
            "original_gold": p.get("originalGold"),
            "crystal": p.get("crystal"),
            "subtotal_crystal": p.get("subtotalCrystal"),
            "original_crystal": p.get("originalCrystal"),
            "bpcoin": p.get("bpcoin"),
            "piggy_bank": p.get("piggyBank"),

            # опыт
            "xp": p.get("xp"),
            "original_xp": p.get("originalXP"),
            "subtotal_xp": p.get("subtotalXP"),
            "factual_xp": p.get("factualXP"),
            "xp_penalty": p.get("xpPenalty"),
            "xp_by_tmen": as_dict_of_pairs(p.get("xpByTmen")),
            "tmen_xp": p.get("tmenXP"),
            "original_tmen_xp": p.get("originalTMenXP"),
            "subtotal_tmen_xp": p.get("subtotalTMenXP"),
            "free_xp": p.get("freeXP"),
            "original_free_xp": p.get("originalFreeXP"),
            "subtotal_free_xp": p.get("subtotalFreeXP"),
            "factual_free_xp": p.get("factualFreeXP"),

            # множители опыта
            "premium_xp_factor100": p.get("premiumXPFactor100"),
            "premium_plus_xp_factor100": p.get("premiumPlusXPFactor100"),
            "daily_xp_factor10": p.get("dailyXPFactor10"),
            "additional_xp_factor10": p.get("additionalXPFactor10"),
            "applied_premium_xp_factor100": p.get("appliedPremiumXPFactor100"),
            "applied_premium_tmen_xp_factor100": p.get("appliedPremiumTmenXPFactor100"),
            "igr_xp_factor10": p.get("igrXPFactor10"),
            "ref_system_xp_factor10": p.get("refSystemXPFactor10"),

            # сервис/ремонт/расходы
            "repair": p.get("repair"),
            "auto_repair_cost": as_tuple_or_list(p.get("autoRepairCost")),
            "auto_equip_cost": as_tuple_or_list(p.get("autoEquipCost")),
            "auto_load_cost": as_tuple_or_list(p.get("autoLoadCost")),

            # прочее состояние
            "health": p.get("health"),
            "max_health": p.get("maxHealth"),
            "mileage": p.get("mileage"),
            "marks_on_gun": p.get("marksOnGun"),
            "mark_of_mastery": p.get("markOfMastery"),
            "is_premium": p.get("isPremium"),
            "is_first_blood": p.get("isFirstBlood"),
            "is_team_killer": p.get("isTeamKiller"),
            "account_dbid": p.get("accountDBID"),
            "type_comp_descr": p.get("typeCompDescr"),

            # цели/очки базы
            "capture_points": p.get("capturePoints"),
            "dropped_capture_points": p.get("droppedCapturePoints"),
            "num_defended": p.get("numDefended"),
            "flag_capture": p.get("flagCapture"),
            "solo_flag_capture": p.get("soloFlagCapture"),
            "win_points": p.get("winPoints"),

            # проценты вклада
            "kills_before_team_was_damaged": p.get("killsBeforeTeamWasDamaged"),
            "damage_before_team_was_damaged": p.get("damageBeforeTeamWasDamaged"),
            "percent_from_total_team_damage": p.get("percentFromTotalTeamDamage"),
            "percent_from_second_best_damage": p.get("percentFromSecondBestDamage"),

            # достижения/квесты/служебное
            "achievements": list(p.get("achievements") or []),
            "dossier_log_records": list(p.get("dossierLogRecords") or []),
            "quests_progress": p.get("questsProgress") or {},
            "c11n_progress": p.get("c11nProgress") or {},

            # сводка по details (агрегаты сверху)
            **agg,
        }

        # удобно вернуть и исходные details, чтобы при необходимости рисовать «по целям»
        data["details"] = details

        return data

    @staticmethod
    def get_achievements(payload) -> List[int]:
        """
        Вернёт список ID достижений текущего игрока.
        Берём прямо из payload['personal'][...]['achievements'].

        Логика:
        - Находим запись в 'personal', где accountDBID == payload['playerID'].
        - Возвращаем поле 'achievements' (если нет — пустой список).
        """
        p = ExtractorV2.get_personal_by_player_id(payload)
        if not p:
            return []
        ach = p.get("achievements") or []
        # Нормализуем к int (на всякий случай)
        out: List[int] = []
        for x in ach:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    def get_details_data(cache: 'ReplayDataCache') -> Dict[str, Any]:
        """
        Извлекает детальные данные боя для отображения.

        Args:
            cache: Кеш данных реплея

        Returns:
            Словарь с детальными данными
        """
        personal = cache.personal
        first_block = cache.first_block

        player_id = cache.player_id
        player = cache.players.get(str(player_id), {})
        clan_abbrev = player.get("clanAbbrev", "")

        details_data = {
            'xp': personal.get('xp'),
            'credits': personal.get('credits'),
            'repair': personal.get('repair'),

            'serverName': first_block.get('serverName'),
            'battleType': first_block.get('battleType'),
            'battleModeLabel': ExtractorV2.get_battle_mode_label(cache),
            'clientVersion': first_block.get('clientVersionFromExe'),
            'playerName': first_block.get('playerName'),
            'clanAbbrev': clan_abbrev
        }
        return details_data

    @staticmethod
    def build_interactions_data(cache: 'ReplayDataCache', tanks_cache: Dict[str, 'Tank']) -> tuple:
        """
        Строит данные взаимодействий И суммарную статистику за ОДИН проход.

        Это оптимизированная версия, которая объединяет build_interaction_rows и
        build_interactions_summary в один метод, избегая двойного прохода по данным.

        Args:
            cache: ReplayDataCache с данными реплея
            tanks_cache: Предзагруженные танки {vehicleId: Tank}

        Returns:
            Кортеж (interaction_rows: list, interactions_summary: dict)
        """
        from replays.models import Tank
        from replays.parser.replay_cache import ReplayDataCache

        details = cache.get_details()

        if not isinstance(details, Mapping):
            empty_summary = {
                "spotted_tanks": 0,
                "assist_tanks": 0,
                "blocked_tanks": 0,
                "crits_total": 0,
                "piercings_total": 0,
                "destroyed_tanks": 0,
            }
            return [], empty_summary

        rows = []

        # Счётчики для summary (считаем сразу в цикле!)
        spotted_count = 0
        assist_count = 0
        blocked_count = 0
        crits_total = 0
        piercings_total = 0
        destroyed_count = 0

        for k, d in details.items():
            if not isinstance(d, Mapping):
                continue

            aid = ExtractorV2._parse_target_avatar_id(str(k))
            if not aid:
                continue

            # Получаем информацию об аватаре из metadata_vehicles
            avatar_data = cache.metadata_vehicles.get(aid, {})
            vehicle_type = str(avatar_data.get("vehicleType", ""))

            if ":" in vehicle_type:
                _, vehicle_tag = vehicle_type.split(":", 1)
            else:
                vehicle_tag = vehicle_type

            # Используем предзагруженный кеш танков!
            tank = tanks_cache.get(vehicle_tag)
            if not tank:
                # Создаём неизвестный танк (но это должно быть редким случаем)
                tank, _ = Tank.objects.get_or_create(
                    vehicleId=vehicle_tag,
                    defaults={
                        'name': f'Неизвестный танк ({vehicle_tag})',
                        'level': 1,
                        'type': 'unknown'
                    }
                )
                # Добавляем в кеш для последующих использований
                tanks_cache[vehicle_tag] = tank

            # Вычисляем метрики
            spotted = int(d.get("spotted") or 0)
            assist_value = (
                int(d.get("damageAssistedTrack") or 0) +
                int(d.get("damageAssistedRadio") or 0) +
                int(d.get("damageAssistedStun") or 0) +
                int(d.get("damageAssistedSmoke") or 0) +
                int(d.get("damageAssistedInspire") or 0)
            )
            blocked_events = (
                int(d.get("rickochetsReceived") or 0) +
                int(d.get("noDamageDirectHitsReceived") or 0)
            )
            crits_mask = int(d.get("crits") or 0)
            crits_count = crits_mask.bit_count() if hasattr(int, "bit_count") else bin(crits_mask).count("1")
            damage_piercings = int(d.get("piercings") or 0)
            target_kills = int(d.get("targetKills") or 0)

            # Обновляем суммарные счётчики (ЗА ОДИН ПРОХОД!)
            if spotted > 0:
                spotted_count += 1
            if assist_value > 0:
                assist_count += 1
            if blocked_events > 0:
                blocked_count += 1
            crits_total += crits_count
            piercings_total += damage_piercings
            if target_kills > 0:
                destroyed_count += 1

            # Получаем имя игрока (приоритет: realName > name)
            player_info = cache.players.get(str(aid), {})
            player_real_name = player_info.get("realName") if isinstance(player_info, dict) else None
            player_name = player_real_name or avatar_data.get("name") or aid

            # Формируем строку
            rows.append({
                "avatar_id": aid,
                "name": player_name,
                "vehicle_tag": vehicle_tag,
                "vehicle_name": tank.name,
                "vehicle_img": f"style/images/wot/shop/vehicles/180x135/{vehicle_tag}.png" if vehicle_tag else "tanks/tank_placeholder.png",
                "team": avatar_data.get("team"),

                # Флаги для иконок (opacity)
                "spotted": spotted > 0,
                "assist": assist_value > 0,
                "blocked": blocked_events > 0,
                "crits": crits_count > 0,
                "damaged": damage_piercings > 0,
                "destroyed": target_kills > 0,

                # Числовые значения для отображения
                "spotted_count": spotted,
                "assist_value": assist_value,
                "blocked_events": blocked_events,
                "crits_count": crits_count,
                "damage_piercings": damage_piercings,
                "destroyed_count": target_kills,
            })

        # Формируем summary
        summary = {
            "spotted_tanks": spotted_count,
            "assist_tanks": assist_count,
            "blocked_tanks": blocked_count,
            "crits_total": crits_total,
            "piercings_total": piercings_total,
            "destroyed_tanks": destroyed_count,
        }

        return rows, summary

    @staticmethod
    def build_interaction_rows(payload) -> List[Dict[str, Any]]:
        """
        Готовит строки для шаблона по деталям текущего игрока.
        Для каждой цели считает количества: засветы, ассист (сумма урона),
        блок (события), криты (popcount), урон (пробития), уничтожения.
        """
        personal = ExtractorV2.get_personal_by_player_id(payload) or {}
        details = personal.get("details")
        if not isinstance(details, Mapping):
            return []

        rows: Dict[str, Dict[str, Any]] = {}

        for k, d in details.items():
            if not isinstance(d, Mapping):
                continue
            aid = ExtractorV2._parse_target_avatar_id(str(k))
            if not aid:
                continue

            info = rows.setdefault(aid, {
                **ExtractorV2._avatar_info(payload, aid),
                # флаги для затенения и числа для <div class="info">
                "spotted": False, "spotted_count": 0,
                "assist": False, "assist_value": 0,  # суммарный ассист-урон
                "blocked": False, "blocked_events": 0,  # рикошеты + непробития
                # "blocked_damage" можно тоже добавить при желании
                "crits": False, "crits_count": 0,  # popcount по битовой маске
                "damaged": False, "damage_piercings": 0,  # кол-во пробитий по цели
                "destroyed": False, "destroyed_count": 0,
            })

            # --- считаем количества ---
            spotted = int(d.get("spotted") or 0)

            assist_value = (
                    int(d.get("damageAssistedTrack") or 0) +
                    int(d.get("damageAssistedRadio") or 0) +
                    int(d.get("damageAssistedStun") or 0) +
                    int(d.get("damageAssistedSmoke") or 0) +
                    int(d.get("damageAssistedInspire") or 0)
            )

            blocked_events = (
                    int(d.get("rickochetsReceived") or 0) +
                    int(d.get("noDamageDirectHitsReceived") or 0)
            )
            # при желании: blocked_damage = int(d.get("damageBlockedByArmor") or 0)

            crits_mask = int(d.get("crits") or 0)
            # popcount (сколько бит установлено) — грубая оценка количества критов
            crits_count = crits_mask.bit_count() if hasattr(int, "bit_count") else bin(crits_mask).count("1")

            damage_piercings = int(d.get("piercings") or 0)  # «всего пробитий»
            target_kills = int(d.get("targetKills") or 0)

            # --- заполняем флаги + числа (накопительным образом на случай дублей ключей) ---
            if spotted > 0:
                info["spotted"] = True
                info["spotted_count"] += spotted

            if assist_value > 0:
                info["assist"] = True
                info["assist_value"] += assist_value

            if blocked_events > 0:
                info["blocked"] = True
                info["blocked_events"] += blocked_events

            if crits_count > 0:
                info["crits"] = True
                info["crits_count"] += crits_count

            if damage_piercings > 0:
                info["damaged"] = True
                info["damage_piercings"] += damage_piercings

            if target_kills > 0:
                info["destroyed"] = True
                info["destroyed_count"] += target_kills

        return list(rows.values())

    @staticmethod
    def build_interactions_summary(rows: list[dict]) -> dict[str, int]:
        """
        Считает суммарные показатели по списку целей:
        - spotted_tanks: сколько танков ты обнаружил
        - assist_tanks: по скольким помог в уничтожении (ассист-урон > 0)
        - blocked_tanks: от скольких заблокировал урон (рик+непробития > 0)
        - crits_total: суммарное число критов (по popcount маски на целях)
        - piercings_total: суммарное число пробитий (нанёс урон)
        - destroyed_tanks: сколько танков уничтожил
        """
        return {
            "spotted_tanks": sum(1 for r in rows if r.get("spotted")),
            "assist_tanks": sum(1 for r in rows if r.get("assist")),
            "blocked_tanks": sum(1 for r in rows if r.get("blocked")),
            "crits_total": sum(int(r.get("crits_count") or 0) for r in rows),
            "piercings_total": sum(int(r.get("damage_piercings") or 0) for r in rows),
            "destroyed_tanks": sum(int(r.get("destroyed_count") or 0) for r in rows),
        }

    @staticmethod
    def split_achievements_by_section(achievement_ids: Iterable[int]):
        """
        Возвращает (ach_nonbattle_qs, ach_battle_qs):
        - battle:  section == 'battle'
        - nonbattle: section != 'battle'
        Сортировка: по weight (order) DESC, затем по name ASC.
        """
        from replays.models import Achievement  # локальный импорт во избежание циклических

        ids = [int(x) for x in (achievement_ids or []) if x is not None]
        if not ids:
            empty = Achievement.objects.none()
            return empty, empty

        qs = (
            Achievement.objects
            .filter(achievement_id__in=ids, is_active=True)
            .annotate(
                weight=Coalesce(
                    Cast('order', FloatField()),  # order может быть INT/NULL -> приводим к float
                    Value(0.0),
                    output_field=FloatField(),
                )
            )
        )

        battle_sections = ('battle', 'epic')
        ach_battle_qs = qs.filter(section__in=battle_sections).order_by('-weight', 'name')
        ach_nonbattle_qs = qs.exclude(section__in=battle_sections).order_by('-weight', 'name')

        return ach_nonbattle_qs, ach_battle_qs

    @staticmethod
    @lru_cache(maxsize=8)
    def _death_reason_to_text(code: int) -> str:
        """
        Преобразует код причины смерти в понятный текст.
        По данным реплеев:  -1 = жив, 0 = выстрел (типовая смерть).
        Остальные коды при необходимости дополни.

        Кешируется с помощью lru_cache, т.к. значений мало (0-3),
        а вызовов может быть много при обработке команд.
        """
        mapping = {
            0: "выстрелом",
            1: "тараном",
            2: "пожаром",
            3: "переворотом/утоплением",
        }
        return mapping.get(int(code), "уничтожен")

    @staticmethod
    def get_killer_name(cache: 'ReplayDataCache', default: str = "") -> str:
        """
        Возвращает ник убийцы по killerID из personal текущего игрока.
        Если игрок выжил или данных нет — вернёт default.

        Args:
            cache: Кеш данных реплея
            default: Значение по умолчанию

        Returns:
            Ник убийцы или default
        """
        p = cache.personal
        killer_id = p.get("killerID")
        try:
            killer_id_int = int(killer_id)
        except (TypeError, ValueError):
            killer_id_int = 0

        if killer_id_int <= 0:
            return default

        # killer_id_int - это avatarSessionID, берём данные из metadata_vehicles
        killer = cache.metadata_vehicles.get(str(killer_id_int), {})

        # Получаем accountDBID убийцы из vehicles
        killer_vehicle_list = cache.vehicles.get(str(killer_id_int), [])
        killer_account_id = None
        if isinstance(killer_vehicle_list, list) and killer_vehicle_list:
            killer_vstats = killer_vehicle_list[0] if isinstance(killer_vehicle_list[0], dict) else {}
            killer_account_id = killer_vstats.get("accountDBID")

        # Получаем realName из players
        real_name = None
        if killer_account_id:
            killer_player_info = cache.players.get(str(killer_account_id), {})
            if isinstance(killer_player_info, dict):
                real_name = killer_player_info.get("realName")

        # Приоритет: realName из players > name из metadata_vehicles > fakeName
        return real_name or killer.get("name") or killer.get("fakeName") or str(killer_id_int)

    @staticmethod
    def get_death_text(cache: 'ReplayDataCache') -> str:
        """
        Строит строку для шаблона:
          - "Выжил", если deathReason == -1
          - "Уничтожен <причина> (<ник>)", если погиб

        Args:
            cache: Кеш данных реплея

        Returns:
            Текст статуса жизни
        """
        p = cache.personal
        death_reason = p.get("deathReason", -1)
        try:
            dr = int(death_reason)
        except (TypeError, ValueError):
            dr = -1

        if dr == -1:
            return "Выжил"

        reason = ExtractorV2._death_reason_to_text(dr)
        killer = ExtractorV2.get_killer_name(cache)
        return f"Уничтожен {reason}" + (f" ({killer})" if killer else "")

    @staticmethod
    def build_income_summary_cached(cache: 'ReplayDataCache', context: 'ExtractorContext') -> Dict[str, Any]:
        """
        Оптимизированная версия build_income_summary с использованием кеша.

        Args:
            cache: ReplayDataCache с данными реплея
            context: ExtractorContext для кеширования вычислений

        Returns:
            Словарь со сводкой по доходам
        """
        from replays.parser.replay_cache import ReplayDataCache

        # персональные данные текущего игрока
        p = cache.personal
        common = cache.common

        # --- первая победа (x2) ---
        team = int(p.get('team') or 0)
        winner_team = int(common.get('winnerTeam') or -1)
        is_victory = (team == winner_team)
        daily_factor10 = int(p.get('dailyXPFactor10') or 10)
        is_first_win = is_victory and daily_factor10 >= 20

        # --- кредиты (база и прем) ---
        base_credits = int(p.get('originalCredits') or p.get('subtotalCredits') or p.get('credits') or 0)
        prem_cred_factor = (int(p.get('premiumCreditsFactor100') or 100)) / 100.0
        prem_credits = int(round(base_credits * prem_cred_factor))

        # --- опыт (база и прем) ---
        base_xp = int(p.get('originalXP') or p.get('subtotalXP') or p.get('xp') or 0)
        prem_xp_factor = (int(p.get('premiumXPFactor100') or 100)) / 100.0
        prem_xp = int(round(base_xp * prem_xp_factor))

        # x2 за первую победу
        victory_mult = 2 if is_first_win else 1
        xp_with_first_base = base_xp * victory_mult
        xp_with_first_prem = int(round(prem_xp * victory_mult))

        # --- меткость ---
        shots = int(p.get('shots') or 0)
        hits = int(p.get('directHits') or p.get('directEnemyHits') or 0)
        hit_percent = (hits / shots * 100.0) if shots > 0 else 0.0

        # --- ассист и урон (используем кешированное значение!) ---
        assist_total = context.get_total_assist()
        damage_total = int(p.get('damageDealt') or 0)

        return {
            'credits_base': base_credits,
            'credits_premium': prem_credits,
            'xp_base': base_xp,
            'xp_premium': prem_xp,
            'xp_with_first_base': xp_with_first_base,
            'xp_with_first_premium': xp_with_first_prem,
            'is_first_win': is_first_win,
            'shots': shots,
            'hits': hits,
            'hit_percent': hit_percent,
            'assist_total': assist_total,
            'damage_total': damage_total,
        }

    @staticmethod
    def build_income_summary(payload) -> Dict[str, Any]:
        """
        Сводка для блока income:
        - кредиты для базового и прем-аккаунта,
        - опыт (обычный и с "первой победой"),
        - меткость (попадания/выстрелы и %),
        - суммарный ассист и нанесённый урон.
        """
        # персональные данные текущего игрока
        p = ExtractorV2.get_personal_by_player_id(payload) or {}

        common = ExtractorV2.get_common(payload)

        # --- первая победа (x2) ---
        # dailyXPFactor10: 10 = x1.0, 20 = x2.0
        team = int(p.get('team') or 0)
        winner_team = int(common.get('winnerTeam') or -1)
        is_victory = (team == winner_team)
        daily_factor10 = int(p.get('dailyXPFactor10') or 10)
        is_first_win = is_victory and daily_factor10 >= 20

        # --- кредиты (база и прем) ---
        # Базу берём как "originalCredits" (или fallback-и)
        base_credits = int(p.get('originalCredits') or p.get('subtotalCredits') or p.get('credits') or 0)
        prem_cred_factor = (int(p.get('premiumCreditsFactor100') or 100)) / 100.0  # обычно 1.5 для премиума
        prem_credits = int(round(base_credits * prem_cred_factor))

        # --- опыт (база и прем) ---
        base_xp = int(p.get('originalXP') or p.get('subtotalXP') or p.get('xp') or 0)
        prem_xp_factor = (int(p.get('premiumXPFactor100') or 100)) / 100.0  # обычно 1.5 для премиума
        prem_xp = int(round(base_xp * prem_xp_factor))

        # x2 за первую победу
        victory_mult = 2 if is_first_win else 1
        xp_with_first_base = base_xp * victory_mult
        xp_with_first_prem = int(round(prem_xp * victory_mult))

        # === Итого ===


        # --- меткость ---
        shots = int(p.get('shots') or 0)
        hits = int(p.get('directHits') or p.get('directEnemyHits') or 0)
        hit_percent = (hits / shots * 100.0) if shots > 0 else 0.0

        # --- ассист и урон ---
        assist_total = ExtractorV2._calculate_total_assist(p)  # суммарный ассист-урон
        damage_total = int(p.get('damageDealt') or 0)

        return {
            'credits_base': base_credits,
            'credits_premium': prem_credits,
            'xp_base': base_xp,
            'xp_premium': prem_xp,
            'xp_with_first_base': xp_with_first_base,
            'xp_with_first_premium': xp_with_first_prem,
            'is_first_win': is_first_win,
            'shots': shots,
            'hits': hits,
            'hit_percent': hit_percent,
            'assist_total': assist_total,
            'damage_total': damage_total,
        }

    @staticmethod
    @lru_cache(maxsize=32)
    def _get_battle_type_by_gameplay_id(gameplay_id: str) -> Optional[str]:
        """
        Кешируемая функция для определения типа боя по gameplay ID.

        Args:
            gameplay_id: Строковый идентификатор режима игры

        Returns:
            Название режима или None, если не найдено
        """
        gp_map = {
                "ctf": "Стандартный бой",
                "ctf2": "Завоевание",
                "ctf30x30": "Генеральное сражение",
                "comp7": "Натиск",
                "comp7_1": "Натиск (Защита баз)",
                "comp7_2": "Натиск (Атака)",
                "domination": "Встречный бой",
                "domination3": "Столкновение",
                "domination30x30": "Генеральное сражение",
                "epic": "Линия фронта",
                "escort": "Эскорт",
                "fallout": "«Стальная охота»",
                "fallout1": "«Стальная охота»",
                "fallout2": "«Стальная охота»",
                "fallout3": "«Стальная охота»",
                "fallout4": "«Превосходство»",
                "fallout5": "«Превосходство»",
                "fallout6": "«Превосходство»",
                "maps_training": "Топография",
                "nations": "Противостояние",
                "rts": "Искусство стратегии",
                "rts_bootcamp": "Искусство стратегии",
                "winback": "Разминка"
            }
        return gp_map.get(gameplay_id)

    @staticmethod
    @lru_cache(maxsize=16)
    def _get_battle_type_by_code(code: int) -> Optional[str]:
        """
        Кешируемая функция для определения типа боя по числовому коду.

        Args:
            code: Числовой код типа боя (battleType или bonusType)

        Returns:
            Название режима или None, если не найдено
        """
        code_map = {
            0: "Специальный бой",
            1: "Случайный бой",
            2: "Тренировочный бой",
            4: "Боевое обучение",
            5: "Командный бой",
            6: "Исторический бой",
            7: "Специальный игровой режим",
            8: "Вылазки",
            9: "Бой с кланом",
            10: "Командный бой: игра в Ладдере",
            11: "Учебный бой",
            12: "Учебный бой",
            13: "«Превосходство»",
            14: "«Стальная охота»",
            15: "Вылазка",
            16: "Наступление",
            17: "Ранговый бой",
            18: "«Превосходство»",
            19: "Случайный бой",
            20: "Тренировочный бой",
            21: "Линия фронта",
            22: "Линия фронта",
            23: "Стальной охотник",
            24: "Разведка боем",
            25: "Обучение на картах",
            26: "Искусство стратегии",
            27: "Линия фронта",
            28: "Основы стратегии",
            29: "«Стальной охотник»",
            30: "Натиск",
            31: "Разминка",
            32: "«Битва блогеров»",
            33: "Натиск",
            37: "«Разведка боем»",
            38: "«Топография»",
            42: "Полевые испытания",
            43: "Натиск",
            44: "Разминка",
            50: "Полигон",
            61: "Разлом",
            31000: "Полигон",
        }
        return code_map.get(code)

    @staticmethod
    def get_battle_type_label(cache: 'ReplayDataCache') -> str:
        """
        Вернёт человекочитаемое название типа игры по gameplayID.
        Например: "Стандартный бой", "Встречный бой", "Господство".

        Args:
            cache: Кеш данных реплея

        Returns:
            Человекочитаемое название типа игры
        """
        gameplay_id = str(cache.first_block.get("gameplayID") or "").strip()
        if gameplay_id:
            label = ExtractorV2._get_battle_type_by_gameplay_id(gameplay_id)
            if label:
                return label
        return "Неизвестный режим"

    @staticmethod
    def get_battle_mode_label(cache: 'ReplayDataCache') -> str:
        """
        Вернёт человекочитаемое название режима боя по battleType/bonusType.
        Например: "Случайный бой", "Ранговый бой", "Тренировочный бой".

        Args:
            cache: Кеш данных реплея

        Returns:
            Человекочитаемое название режима боя
        """
        # Проверяем battleType и bonusType
        bt = cache.first_block.get("battleType")
        bonus = cache.common.get("bonusType")

        for code in (bt, bonus):
            try:
                code_int = int(code)
                label = ExtractorV2._get_battle_type_by_code(code_int)
                if label:
                    return label
            except (TypeError, ValueError):
                pass

        return "Неизвестный режим"

    @staticmethod
    def get_battle_outcome(cache: 'ReplayDataCache') -> dict[str, str]:
        """
        Формирует текст статуса ('Победа! / Поражение / Ничья'),
        CSS-класс и человекочитаемую причину завершения боя.

        Args:
            cache: Кеш данных реплея

        Returns:
            Словарь с ключами: status_text, status_class, reason_text
        """
        winner_team = cache.common.get("winnerTeam")       # 0 = ничья
        finish_reason = cache.common.get("finishReason")   # 1 — уничтожены, 2 — база, 3 — время и т.д.
        player_team = cache.player_team

        # Статус
        if winner_team in (0, None):
            status_text, status_class = "Ничья", "draw"
        elif player_team is not None and int(winner_team) == int(player_team):
            status_text, status_class = "Победа!", "victory"
        else:
            status_text, status_class = "Поражение", "defeat"

        # Причины (минимально достаточная карта)
        reasons_victory = {
            1: "Вся техника противника уничтожена",
            2: "Наша команда захватила базу",
            3: "Время истекло",
        }
        reasons_defeat = {
            1: "Вся наша техника уничтожена",
            2: "Вражеская команда захватила базу",
            3: "Время истекло",
        }
        reasons_draw = {
            3: "Время истекло",
        }

        fr = int(finish_reason) if isinstance(finish_reason, int) else None
        if status_class == "victory":
            reason = reasons_victory.get(fr, "Бой завершён")
        elif status_class == "defeat":
            reason = reasons_defeat.get(fr, "Бой завершён")
        else:
            reason = reasons_draw.get(fr, "Бой завершён")

        return {
            "status_text": status_text,
            "status_class": status_class,
            "reason_text": reason,
        }

    @staticmethod
    def _preload_all_player_medals(cache: 'ReplayDataCache') -> Dict[str, Dict[str, Any]]:
        """
        Предзагружает медали для ВСЕХ игроков боя одним запросом.

        Args:
            cache: Кеш данных реплея

        Returns:
            Словарь {avatar_id: {"count": N, "title": "...", "has_medals": bool}}
        """
        from replays.models import Achievement

        # Собираем все достижения всех игроков
        all_achievement_ids = set()
        player_achievements = {}  # {avatar_id: [achievement_ids]}

        for avatar_id, vstats_list in cache.vehicles.items():
            if isinstance(vstats_list, list) and vstats_list:
                vstats = vstats_list[0] if isinstance(vstats_list[0], dict) else {}
                achievements = vstats.get("achievements", [])
                if achievements:
                    player_achievements[avatar_id] = achievements
                    for aid in achievements:
                        try:
                            all_achievement_ids.add(int(aid))
                        except (TypeError, ValueError):
                            pass

        if not all_achievement_ids:
            return {}

        # ОДИН запрос для ВСЕХ достижений ВСЕХ игроков!
        achievements = Achievement.objects.filter(
            achievement_id__in=all_achievement_ids,
            is_active=True,
            achievement_type__in=['battle', 'epic']
        ).values('achievement_id', 'name').order_by('name')

        # Создаём lookup таблицу
        ach_lookup = {ach['achievement_id']: ach['name'] for ach in achievements}

        # Формируем результат для каждого игрока
        result = {}
        for avatar_id, ach_ids in player_achievements.items():
            valid_names = []
            for aid in ach_ids:
                try:
                    aid_int = int(aid)
                    if aid_int in ach_lookup:
                        valid_names.append(ach_lookup[aid_int])
                except (TypeError, ValueError):
                    pass

            if valid_names:
                result[avatar_id] = {
                    "count": len(valid_names),
                    "title": "&lt;br&gt;".join(f"«{name}»" for name in valid_names),
                    "has_medals": True
                }
            else:
                result[avatar_id] = {
                    "count": 0,
                    "title": "",
                    "has_medals": False
                }

        logger.debug(f"Предзагружено медалей для {len(result)} игроков из {len(player_achievements)} с достижениями")

        return result

    @staticmethod
    def _get_player_medals(achievement_ids: list) -> Dict[str, Any]:
        """
        Получает информацию о медалях игрока из базы данных.
        Возвращает только боевые и эпические достижения.

        DEPRECATED: Используйте _preload_all_player_medals() для batch-загрузки всех медалей.
        """
        if not achievement_ids:
            return {
                "count": 0,
                "title": "",
                "has_medals": False
            }

        try:
            # Импортируем модель здесь, чтобы избежать циклических импортов
            from replays.models import Achievement

            # Нормализуем ID к int
            ids = []
            for aid in achievement_ids:
                try:
                    ids.append(int(aid))
                except (TypeError, ValueError):
                    continue

            if not ids:
                return {
                    "count": 0,
                    "title": "",
                    "has_medals": False
                }

            # Получаем только боевые и эпические достижения
            achievements = Achievement.objects.filter(
                achievement_id__in=ids,
                is_active=True,
                achievement_type__in=['battle', 'epic']
            ).values('name').order_by('name')

            count = len(achievements)

            if count == 0:
                return {
                    "count": 0,
                    "title": "",
                    "has_medals": False
                }

            # Формируем title для tooltip
            medal_names = [f"«{ach['name']}»" for ach in achievements]
            title = "&lt;br&gt;".join(medal_names)

            return {
                "count": count,
                "title": title,
                "has_medals": True
            }

        except Exception as e:
            # В случае ошибки возвращаем пустые данные
            return {
                "count": 0,
                "title": "",
                "has_medals": False
            }

    @staticmethod
    def _build_player_data(
        avatar_id: str,
        raw: Mapping[str, Any],
        vehicles_stats: Mapping[str, Any],
        players_info: Mapping[str, Any],
        cache: 'ReplayDataCache',
        tanks_cache: Dict[str, 'Tank'],
        medals_cache: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Формирует данные игрока для командного результата.

        Args:
            avatar_id: ID аватара игрока
            raw: Сырые данные аватара
            vehicles_stats: Статистика техники
            players_info: Информация об игроках
            cache: Кеш данных реплея
            tanks_cache: Предзагруженные танки
            medals_cache: Предзагруженные медали
        """
        # Базовая информация
        vehicle_type = str(raw.get("vehicleType", ""))
        if ":" in vehicle_type:
            vehicle_nation, vehicle_tag = vehicle_type.split(":", 1)
        else:
            vehicle_nation, vehicle_tag = "", vehicle_type

        # Статистика из vehicles (ключ - avatarSessionID)
        vstats = {}
        vehicle_list = vehicles_stats.get(avatar_id, [])
        if isinstance(vehicle_list, list) and vehicle_list:
            vstats = vehicle_list[0] if isinstance(vehicle_list[0], dict) else {}

        # Информация об игроке из players (ключ - accountDBID)
        # Нужно найти accountDBID из vstats, чтобы получить данные из players
        account_id = vstats.get("accountDBID")
        player_info = {}

        if account_id:
            # Преобразуем к строке для поиска
            player_info = players_info.get(str(account_id), {})
            if not isinstance(player_info, dict):
                player_info = players_info.get(int(account_id), {})
            if not isinstance(player_info, dict):
                player_info = {}                
        # Определяем статус жизни
        death_reason = vstats.get("deathReason", -1)
        is_alive = death_reason == -1
        killer_id = vstats.get("killerID", 0)

        # Текст причины смерти
        death_text = ""
        if not is_alive and killer_id > 0:
            # killer_id - это avatarSessionID, берём данные из metadata_vehicles
            killer_data = cache.metadata_vehicles.get(str(killer_id), {})

            # Получаем accountDBID убийцы из vehicles
            killer_vehicle_list = vehicles_stats.get(str(killer_id), [])
            killer_account_id = None
            if isinstance(killer_vehicle_list, list) and killer_vehicle_list:
                killer_vstats = killer_vehicle_list[0] if isinstance(killer_vehicle_list[0], dict) else {}
                killer_account_id = killer_vstats.get("accountDBID")

            # Получаем realName из players
            killer_real_name = None
            if killer_account_id:
                killer_player_info = players_info.get(str(killer_account_id), {})
                if isinstance(killer_player_info, dict):
                    killer_real_name = killer_player_info.get("realName")

            # Приоритет: realName из players > name из metadata_vehicles > fakeName
            killer_name = killer_real_name or killer_data.get("name") or killer_data.get("fakeName", "")

            if death_reason == 0:
                death_text = f"Уничтожен выстрелом ({killer_name})"
            elif death_reason == 2:
                death_text = f"Уничтожен пожаром ({killer_name})"
            elif death_reason == 3:
                death_text = "Затоплен"
            else:
                death_text = f"Уничтожен ({killer_name})" if killer_name else "Уничтожен"
        elif not is_alive:
            death_text = "Уничтожен"
        else:
            death_text = "Выжил"

        # Получаем танк из предзагруженного кеша
        tank = tanks_cache.get(vehicle_tag)
        if not tank:
            # Редкий случай - танка нет в кеше (создаём на месте)
            logger.warning(f"Танк {vehicle_tag} отсутствует в предзагруженном кеше, создаём новый")
            from replays.models import Tank
            tank, _ = Tank.objects.get_or_create(
                vehicleId=vehicle_tag,
                defaults={
                    'name': f'Неизвестный танк ({vehicle_tag})',
                    'level': 1,
                    'type': 'unknown'
                }
            )
        tank_level = tank.level
        tank_type = tank.type

        # Имя и клан игрока
        # Приоритет: realName из players > name из metadata_vehicles > fakeName
        if player_info:
            clan_tag = player_info.get("clanAbbrev", "")
            player_name = player_info.get("realName") or raw.get("name") or raw.get("fakeName", avatar_id)
        else:
            # Если нет данных в players (бот), используем metadata_vehicles
            clan_tag = ""
            player_name = raw.get("name") or raw.get("fakeName", avatar_id)

        display_name = f"{player_name} [{clan_tag}]" if clan_tag else player_name

        # Ассисты
        total_assist = (
                int(vstats.get("damageAssistedRadio", 0)) +
                int(vstats.get("damageAssistedTrack", 0)) +
                int(vstats.get("damageAssistedStun", 0)) +
                int(vstats.get("damageAssistedSmoke", 0)) +
                int(vstats.get("damageAssistedInspire", 0))
        )

        # Получаем медали из предзагруженного кеша
        medals_data = medals_cache.get(avatar_id, {
            "count": 0,
            "title": "",
            "has_medals": False
        })

        # Определяем, является ли это текущим игроком (владельцем реплея)
        current_player_id = cache.player_id  # ID текущего игрока
        player_account_id = vstats.get("accountDBID")  # ID этого игрока

        is_current_player = (
                current_player_id is not None and
                player_account_id is not None and
                int(current_player_id) == int(player_account_id)
        )

        return {
            "avatar_id": avatar_id,
            "player_name": player_name,
            "display_name": display_name,
            "clan_tag": clan_tag,
            "team": raw.get("team"),
            # "vehicle_type": vehicle_type,
            "vehicle_tag": vehicle_tag,
            # "vehicle_nation": vehicle_nation,
            "vehicle_display_name": tank.name,
            "tank_level": tank_level,
            "tank_type": tank_type,
            "is_alive": is_alive,
            "death_text": death_text,
            "medals": medals_data,
            "is_current_player": is_current_player,

            # Основная статистика
            "shots": int(vstats.get("shots", 0)),
            "direct_hits": int(vstats.get("directHits", 0)),
            "piercings": int(vstats.get("piercings", 0)),
            "explosion_hits": int(vstats.get("explosionHits", 0)),
            "damage_dealt": int(vstats.get("damageDealt", 0)),
            "sniper_damage": int(vstats.get("sniperDamageDealt", 0)),
            "hits_received": int(vstats.get("directHitsReceived", 0)),
            "piercings_received": int(vstats.get("piercingsReceived", 0)),
            "no_damage_hits_received": int(vstats.get("noDamageDirectHitsReceived", 0)),
            "explosion_hits_received": int(vstats.get("explosionHitsReceived", 0)),
            "damage_blocked": int(vstats.get("damageBlockedByArmor", 0)),
            "team_damage": int(vstats.get("tdamageDealt", 0)),
            "team_kills": int(vstats.get("tkills", 0)),
            "spotted": int(vstats.get("spotted", 0)),
            "damaged_count": int(vstats.get("damaged", 0)),
            "kills": int(vstats.get("kills", 0)),
            "assist_damage": total_assist,
            "capture_points": int(vstats.get("capturePoints", 0)),
            "defense_points": int(vstats.get("droppedCapturePoints", 0)),
            "distance": round(int(vstats.get("mileage", 0)) / 1000, 2),  # в км
            "xp": int(vstats.get("xp", 0)),

            # Специальные поля для арты
            "stun_damage": int(vstats.get("damageAssistedStun", 0)),
            "stun_count": int(vstats.get("stunNum", 0)),

            # Достижения
            "achievements": vstats.get("achievements", []),

            # Взвод
            "platoon_id": ExtractorV2._get_platoon_id(avatar_id, cache),
        }

    @staticmethod
    def _get_platoon_id(avatar_id: str, cache: 'ReplayDataCache') -> Optional[int]:
        """Определяет ID взвода игрока."""
        # В реплеях информация о взводах может быть в разных местах
        # Это примерная логика - нужно изучить конкретную структуру

        # Поиск в common.bots или других местах
        bots = cache.common.get("bots") or {}
        if avatar_id in bots:
            bot_data = bots[avatar_id]
            if isinstance(bot_data, list) and len(bot_data) > 0:
                # Возможно здесь есть информация о группировке
                pass

        # Пока возвращаем None - нужна дополнительная логика
        return None

    @staticmethod
    def get_team_results(cache: 'ReplayDataCache', tanks_cache: Dict[str, 'Tank']) -> Dict[str, Any]:
        """
        Извлекает командные результаты для отображения в шаблоне.
        Союзники игрока всегда в allies_players, противники в enemies_players.

        Args:
            cache: Кеш данных реплея
            tanks_cache: Предзагруженные танки {vehicleId: Tank}

        Returns:
            Dict с ключами:
            - 'allies_players': список игроков команды союзников (команда игрока)
            - 'enemies_players': список игроков команды противников
            - 'allies_name': "Союзники"
            - 'enemies_name': "Противник"
        """
        vehicles_stats = cache.vehicles
        players_info = cache.players

        # Определяем команду текущего игрока
        player_team = cache.player_team
        if player_team is None:
            # Фолбэк: если не можем определить команду игрока
            player_team = 1
            logger.warning("Не удалось определить команду игрока, используем team=1")

        # Предзагружаем медали для всех игроков одним запросом
        medals_cache = ExtractorV2._preload_all_player_medals(cache)

        allies_players = []
        enemies_players = []

        # Обходим всех участников (игроков + ботов) из metadata.vehicles
        metadata_vehicles = cache.metadata_vehicles

        for avatar_id, raw in metadata_vehicles.items():
            if not (isinstance(avatar_id, str) and avatar_id.isdigit() and isinstance(raw, Mapping)):
                continue
            if "vehicleType" not in raw:
                continue

            player_data = ExtractorV2._build_player_data(
                avatar_id, raw, vehicles_stats, players_info, cache, tanks_cache, medals_cache
            )
            if not player_data:
                continue

            team = player_data.get("team")
            if team == player_team:
                # Команда игрока = союзники
                allies_players.append(player_data)
            else:
                # Другая команда = противники
                enemies_players.append(player_data)

        # Сортируем по урону (убыванию)
        allies_players.sort(key=lambda x: x.get("damage_dealt", 0), reverse=True)
        enemies_players.sort(key=lambda x: x.get("damage_dealt", 0), reverse=True)

        logger.debug(f"Обработано игроков: {len(allies_players)} союзников, {len(enemies_players)} противников")

        return {
            'allies_players': allies_players,
            'enemies_players': enemies_players,
            'allies_name': "Союзники",
            'enemies_name': "Противник",
        }

    @staticmethod
    def get_detailed_report(cache: 'ReplayDataCache') -> Dict[str, Any]:
        """
        Извлекает детализированные данные для подробного отчета.

        Args:
            cache: Кеш данных реплея

        Returns:
            Словарь с детальными данными отчёта
        """
        first_block = cache.first_block
        personal = cache.personal
        common = cache.common

        # === БОЕВАЯ СТАТИСТИКА === (оставляем как есть)
        battle_stats = {
            "shots": int(personal.get('shots', 0)),
            "direct_hits": int(personal.get('directHits', 0)),
            "piercings": int(personal.get('piercings', 0)),
            "explosion_hits": int(personal.get('explosionHits', 0)),
            "damage_dealt": int(personal.get('damageDealt', 0)),
            "sniper_damage": int(personal.get('sniperDamageDealt', 0)),
            "hits_received": int(personal.get('directHitsReceived', 0)),
            "piercings_received": int(personal.get('piercingsReceived', 0)),
            "no_damage_hits_received": int(personal.get('noDamageDirectHitsReceived', 0)),
            "explosion_hits_received": int(personal.get('explosionHitsReceived', 0)),
            "damage_blocked": int(personal.get('damageBlockedByArmor', 0)),
            "team_damage": int(personal.get('tdamageDealt', 0)),
            "team_kills": int(personal.get('tkills', 0)),
            "spotted": int(personal.get('spotted', 0)),
            "damaged_count": int(personal.get('damaged', 0)),
            "kills": int(personal.get('kills', 0)),
            "assist_total": ExtractorV2._calculate_total_assist(personal),
            "capture_points": int(personal.get('capturePoints', 0)),
            "defense_points": int(personal.get('droppedCapturePoints', 0)),
            "distance": round(int(personal.get('mileage', 0)) / 1000, 2),
            "stun_damage": int(personal.get('damageAssistedStun', 0)),
            "stun_count": int(personal.get('stunNum', 0)),
        }

        # === РАСШИРЕННАЯ ЭКОНОМИКА ===
        # Получаем данные аватара для экономических расчётов
        avatar_data = cache.avatar_data

        # Создаём комбинированный словарь данных для экономических функций:
        # - Основные значения (credits, xp, gold) берём из avatar_data
        # - Множители и факторы берём из personal
        economy_data = dict(personal)  # Копируем все данные из personal
        if avatar_data:
            # Переопределяем только те поля, которые есть в avatar_data
            for key in ['credits', 'xp', 'gold', 'freeXP', 'eventCredits', 'eventXP',
                       'eventGold', 'eventFreeXP', 'eventCreditsList', 'eventXPList',
                       'eventGoldList', 'eventFreeXPList', 'crystal', 'eventCrystal',
                       'eventCrystalList']:
                if key in avatar_data:
                    economy_data[key] = avatar_data[key]

        # == Credits ==
        credits = summarize_credits(economy_data)
        xp = summarize_xp(economy_data)
        gold = summarize_gold(economy_data)



        # Базовые доходы
        original_credits = int(personal.get('originalCredits', 0))
        achievement_credits = int(personal.get('achievementCredits', 0))
        premium_booster_credits = int(personal.get("boosterCredits", 0)) # в файле цифра уже ждя према. базоу надо считать по boosterCreditsFactor100

        booster_credits_factor100 = int(personal.get("boosterCreditsFactor100", 0))
        base_booster_credits = premium_booster_credits * 100 // (100 + booster_credits_factor100)
        team_subs_bonus_credits = int(personal.get("teamSubsBonusCredits", 0))

        # Штрафы и компенсации
        credits_penalty = int(personal.get('creditsPenalty', 0))
        team_damage_penalty = int(personal.get('originalCreditsPenalty', 0))
        team_damage_xp_penalty = int(personal.get('originalXPPenalty', 0))

        # Расходы
        repair_cost = int(personal.get('repair', 0))
        auto_repair_cost = int(personal.get('autoRepairCost', 0))

        # Боекомплект (может быть список [ammo, equipment])
        auto_load_cost = personal.get('autoLoadCost', [0, 0])
        if isinstance(auto_load_cost, list) and len(auto_load_cost) >= 2:
            ammo_cost = int(auto_load_cost[0])
            equipment_cost = int(auto_load_cost[1])
        else:
            ammo_cost = int(auto_load_cost) if auto_load_cost else 0
            equipment_cost = 0

        # Расходы на снаряжение
        auto_equip_cost = personal.get('autoEquipCost', [0, 0, 0])
        if isinstance(auto_equip_cost, list):
            equipment_credits_cost = sum(int(x) for x in auto_equip_cost)
        else:
            equipment_credits_cost = int(auto_equip_cost) if auto_equip_cost else 0

        # Золото за снаряжение
        gold_spent = int(personal.get('gold', 0)) - int(personal.get('originalGold', 0))
        if gold_spent < 0:
            gold_spent = abs(gold_spent)  # Потрачено золота
        else:
            gold_spent = 0

        # Итоги
        total_expenses = auto_repair_cost + ammo_cost + equipment_credits_cost
        battle_earnings = original_credits + achievement_credits + base_booster_credits + team_subs_bonus_credits - team_damage_penalty
        net_result = battle_earnings - total_expenses

        # Премиум факторы
        premium_credit_factor = (int(personal.get('premiumCreditsFactor100', 100))) / 100.0
        is_premium = premium_credit_factor > 1.0

        # Премиум расчеты
        premium_original_credits = int(original_credits * premium_credit_factor)
        premium_achievement_credits = int(achievement_credits * premium_credit_factor) if achievement_credits > 0 else achievement_credits
        premium_battle_earnings = premium_original_credits + premium_achievement_credits + premium_booster_credits + team_subs_bonus_credits - team_damage_penalty
        premium_net_result = premium_battle_earnings - total_expenses

        # === ОПЫТ ===
        # первая победа
        daily_xp_factor10 =  int(int(personal.get('dailyXPFactor10')) / 10)
        original_xp = int(personal.get('originalXP', 0))
        original_free_xp = int(personal.get('originalFreeXP', 0))
        event_xp = int(personal.get('eventXP', 0))
        event_free_xp = int(personal.get('eventFreeXP', 0))

        total_original_xp = original_xp + event_xp - team_damage_xp_penalty
        if personal.get('isFirstBlood'):
            total_original_xp = total_original_xp * 2

        total_free_xp = original_free_xp + event_free_xp - team_damage_xp_penalty
        if personal.get('isFirstBlood'):
            total_free_xp = total_free_xp * 2

        premium_xp_factor = (int(personal.get('premiumXPFactor100', 100))) / 100.0

        premium_xp = int(math.ceil(original_xp * premium_xp_factor))
        premium_free_xp = int(math.ceil(original_free_xp * premium_xp_factor))
        premium_event_xp = int(math.ceil(event_xp * premium_xp_factor))
        premium_event_free_xp = int(math.ceil(event_free_xp * premium_xp_factor))

        total_premium_xp = premium_xp + premium_event_xp - team_damage_xp_penalty
        if personal.get('isFirstBlood'):
            total_premium_xp = total_premium_xp * 2

        total_premium_free_xp = premium_free_xp + premium_event_xp - team_damage_xp_penalty
        if personal.get('isFirstBlood'):
            total_premium_free_xp = total_premium_free_xp * 2

        # === БОНЫ/КРИСТАЛЛЫ ===
        crystal = int(personal.get('crystal', 0))
        event_crystal = int(personal.get("eventCrystal", 0))
        original_crystal = int(personal.get('originalCrystal', 0))
        achievement_crystal = crystal - original_crystal if crystal > original_crystal else 0
        special_vehicle_crystal = max(0, original_crystal)  # "За особые свойства машины"

        economics = {
            # Базовые доходы
            "original_credits": original_credits,
            "achievement_credits": achievement_credits,
            "base_booster_credits": base_booster_credits,
            "team_subs_bonus_credits": team_subs_bonus_credits,

            "battle_earnings": battle_earnings,

            # Премиум доходы
            "premium_original_credits": premium_original_credits,
            "premium_achievement_credits": premium_achievement_credits,
            "premium_booster_credits": premium_booster_credits,
            "premium_team_subs_bonus_credits": team_subs_bonus_credits,

            "premium_battle_earnings": premium_battle_earnings,

            # Расходы
            "auto_repair_cost": auto_repair_cost,
            "ammo_cost": ammo_cost,
            "equipment_credits_cost": equipment_credits_cost,
            "gold_spent": gold_spent,
            "total_expenses": total_expenses,

            # Итоги
            "net_result": net_result,
            "premium_net_result": premium_net_result,

            # Штрафы
            "credits_penalty": credits_penalty,
            "team_damage_penalty": team_damage_penalty,

            # Опыт
            "daily_xp_factor10": daily_xp_factor10,
            "original_xp": original_xp,
            "original_free_xp": original_free_xp,
            "event_xp": event_xp,
            "event_free_xp": event_free_xp,
            "total_original_xp": total_original_xp,
            "total_free_xp": total_free_xp,

            "premium_xp": premium_xp,
            "premium_free_xp": premium_free_xp,
            "premium_event_xp": premium_event_xp,
            "premium_event_free_xp": premium_event_free_xp,
            "total_premium_xp": total_premium_xp,
            "total_premium_free_xp": total_premium_free_xp,

            # Кристаллы
            "achievement_crystal": achievement_crystal,
            "special_vehicle_crystal": special_vehicle_crystal,
            "event_crystal": event_crystal,
            "total_crystal": crystal,

            "is_premium": is_premium,
        }

        # === ВРЕМЯ ===

        death_reason = int(personal.get('deathReason', -1))

        battle_duration = int(common.get('duration', 0))

        lifetime = int(personal.get('lifeTime', 0))

        if death_reason >= 0:
            lifetime_formatted = f"{lifetime // 60}:{lifetime % 60:02d}"
        else:
            lifetime_formatted = "-"

            # Время создания арены (timestamp)
        arena_create_time = common.get('arenaCreateTime', 0)
        battle_start_datetime = None
        battle_start_formatted = ""

        if arena_create_time:
            try:
                from datetime import datetime
                battle_start_datetime = datetime.fromtimestamp(arena_create_time)
                battle_start_formatted = battle_start_datetime.strftime("%d.%m.%Y %H:%M:%S")
            except (ValueError, OSError):
                battle_start_formatted = ""

        # Также можно получить из dateTime если arenaCreateTime недоступно
        if not battle_start_formatted:
            date_time_str = first_block.get('dateTime', '')
            if date_time_str:
                try:
                    # Формат: "25.08.2025 15:57:56"
                    battle_start_datetime = datetime.strptime(date_time_str, '%d.%m.%Y %H:%M:%S')
                    battle_start_formatted = date_time_str
                except ValueError:
                    battle_start_formatted = date_time_str

        time_stats = {
            "battle_duration": battle_duration,
            "battle_duration_formatted": f"{battle_duration // 60}:{battle_duration % 60:02d}",
            "lifetime": lifetime,
            "lifetime_formatted": lifetime_formatted,
            "survival_time_percent": round((lifetime / battle_duration * 100), 1) if battle_duration > 0 else 0,
            "battle_start_time": arena_create_time,
            "battle_start_formatted": battle_start_formatted,
            "battle_start_datetime": battle_start_datetime,
        }

        # === ИНФОРМАЦИЯ О ТЕХНИКЕ === (оставляем как есть)
        vehicle_type = first_block.get('playerVehicle', '')
        if ':' in vehicle_type:
            nation, tank_tag = vehicle_type.split(':', 1)
        else:
            nation, tank_tag = '', vehicle_type

        vehicle_info = {
            "tank_tag": tank_tag,
            "nation": nation,
            "max_health": int(personal.get('maxHealth', 0)),
            "health_remaining": int(personal.get('health', 0)),
            "health_percent": round((int(personal.get('health', 0)) / max(int(personal.get('maxHealth', 1)), 1) * 100), 1),
        }

        return {
            "battle_stats": battle_stats,
            "economics": economics,
            "credits": credits,
            "xp": xp,
            "gold": gold,
            "time_stats": time_stats,
            "vehicle_info": vehicle_info,
        }
