# wotreplay/helper/extractor.py
import os
import datetime
import re
from typing import Any, Dict, List, Optional, Mapping, Iterable

from django.db.models import Value, FloatField
from django.db.models.functions import Coalesce, Cast


class Extractor:

    @staticmethod
    def _calculate_total_assist(personal_data: Dict[str, Any]) -> int:
        """Вычисляет общую помощь в уроне (все виды ассиста)"""
        assist_radio = personal_data.get('damageAssistedRadio', 0)
        assist_track = personal_data.get('damageAssistedTrack', 0)
        assist_stun = personal_data.get('damageAssistedStun', 0)
        assist_smoke = personal_data.get('damageAssistedSmoke', 0)
        assist_inspire = personal_data.get('damageAssistedInspire', 0)

        return assist_radio + assist_track + assist_stun + assist_smoke + assist_inspire

    @staticmethod
    def get_file_name(file: str) -> str:
        """
        Gets the filename of the replay without the path
        """

        filename = os.path.split(file)

        return filename[-1]

    @staticmethod
    def get_replay_date(metadata: dict):
        """
        Gets the datestamp of the replay without the path
        """

        replay_date = metadata.get('dateTime')
        d = datetime.datetime.strptime(replay_date, '%d.%m.%Y%H:%M:%S')

        return d

    @staticmethod
    def get_file_data(file: str) -> list:
        """
        Creates data for the initial file.
        """

        filename = os.path.split(file)
        data = [{
            "filename": filename[-1]
        }]

        return data

    @staticmethod
    def get_account_id(metadata: dict) -> str:
        """
        Retrieves the account id from the replay metadata.
        """

        account_id = metadata.get('playerID', 'None')

        return account_id

    @staticmethod
    def get_replay_metadata(data: dict, account_id: str, replay_date: str) -> list:
        """
        The metadata of the replay is contained within the first sector of the replay data.
        """

        battle_metadata = [{
            "replay_date": replay_date,
            "player_vehicle": data.get('playerVehicle'),
            "nation": str(data.get('playerVehicle')).split('-')[0],
            "tank_tag": str(data.get('playerVehicle')).split("-", 1)[1],
            # "version": data.get('clientVersionFromExe'),
            "version": data.get('clientVersionFromXml'),
            "client_version_executable": data.get('clientVersionFromExe'),
            "region_code": data.get('regionCode'),
            "account_id": account_id,
            "server_name": data.get('serverName'),
            "map_display_name": data.get('mapDisplayName'),
            "date_time": data.get('dateTime'),
            "map_name": data.get('mapName'),
            "gameplay_id": data.get('gameplayID'),
            "battle_type": data.get('battleType'),
            "has_mods": data.get('hasMods'),
            "player_name": data.get('playerName')
        }]

        return battle_metadata

    @staticmethod
    def get_personal_by_player_id(
            payload: Mapping[str, Any],
            player_id: Optional[int] = None,
            *,
            fallback_first: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Вернуть блок personal для указанного игрока.

        :param payload: Единый словарь реплея (payload).
        :param player_id: ID игрока (accountDBID). Если None — берём payload["playerID"].
        :param fallback_first: Если True и точного совпадения нет — вернуть первую запись из personal.
        :return: dict с персональными данными игрока или None.
        """
        # --- безопасно получаем player_id ---
        if player_id is None:
            player_id = payload.get("playerID")  # в реплеях это int

        def _to_int(x: Any) -> Optional[int]:
            """Пробует привести значение к int, иначе None."""
            try:
                return int(x)
            except (TypeError, ValueError):
                return None

        pid = _to_int(player_id)
        if pid is None:
            return None

        personal = payload.get("personal")
        if not isinstance(personal, Mapping):
            return None

        # --- ищем запись, где accountDBID == player_id ---
        for entry in personal.values():
            if not isinstance(entry, Mapping):
                continue
            acc = _to_int(entry.get("accountDBID"))
            if acc is not None and acc == pid:
                # Нашли точное совпадение
                return dict(entry)  # копия на всякий случай (защита от внешних мутаций)

        # --- фолбэк: первая запись из personal (опционально) ---
        if fallback_first:
            for entry in personal.values():
                if isinstance(entry, Mapping):
                    return dict(entry)

        return None

    @staticmethod
    def get_battle_performance(data: list, account_id: str, replay_date: str) -> list:
        """
        Extracts all the parameters required to fill the model from the battle data.
        """
        raw_data = data[0]['personal']
        battle_id = list(raw_data.keys())[0]

        battle_data = raw_data[battle_id]

        battle_performance = [{
            "replay_date": replay_date,
            "account_id": account_id,
            "stunned": battle_data.get('stunned', None),
            "direct_hits": battle_data.get('directHits', None),
            "damage_assisted_radio": battle_data.get('damageAssistedRadio', None),
            "stun_duration": battle_data.get('stunDuration', None),
            "win_points": battle_data.get('winPoints', None),
            "damaged_while_moving": battle_data.get('damagedWhileMoving', None),
            "kills": battle_data.get('kills', None),
            "percent_from_total_team_damage": battle_data.get('percentFromTotalTeamDamage', None),
            "mark_of_mastery": battle_data.get('markOfMastery', None),
            "no_damage_direct_hits_received": battle_data.get('noDamageDirectHitsReceived', None),
            "equipment_damage_dealt": battle_data.get('equipmentDamageDealt', None),
            "tkills": battle_data.get('tkills', None),
            "shots": battle_data.get('shots', None),
            "team": battle_data.get('team', None),
            "death_count": battle_data.get('deathCount', None),
            "stun_number": battle_data.get('stunNum', None),
            "spotted": battle_data.get('spotted', None),
            "killer_id": battle_data.get('killerID', None),
            "solo_flag_capture": battle_data.get('soloFlagCapture', None),
            "marks_on_gun": battle_data.get('marksOnGun', None),
            "killed_and_damaged_by_all_squad_mates": battle_data.get('killedAndDamagedByAllSquadmates', None),
            "rollouts_count": battle_data.get('rolloutsCount', None),
            "health": battle_data.get('health', None),
            "stop_respawn": battle_data.get('stopRespawn', None),
            "t_damage_dealt": battle_data.get('tdamageDealt', None),
            "resource_absorbed": battle_data.get('resourceAbsorbed', None),
            "damaged_while_enemy_moving": battle_data.get('damagedWhileEnemyMoving', None),
            "damage_received": battle_data.get('damageReceived', None),
            "percent_from_second_best_damage": battle_data.get('percentFromSecondBestDamage', None),
            "committed_suicide": battle_data.get('committedSuicide', None),
            "life_time": battle_data.get('lifeTime', None),
            "damage_assisted_track": battle_data.get('damageAssistedTrack', None),
            "sniper_damage_dealt": battle_data.get('sniperDamageDealt', None),
            "fairplay_factor": battle_data.get('fairplayFactor10', None),
            "damage_blocked_by_armour": battle_data.get('damageBlockedByArmor', None),
            "dropped_capture_points": battle_data.get('droppedCapturePoints', None),
            "damage_received_from_invisibles": battle_data.get('damageReceivedFromInvisibles', None),
            "max_health": battle_data.get('maxHealth', None),
            "moving_avg_damage": battle_data.get('movingAvgDamage', None),
            "flag_capture": battle_data.get('flagCapture', None),
            "kills_before_team_was_damaged": battle_data.get('killsBeforeTeamWasDamaged', None),
            "potential_damage_received": battle_data.get('potentialDamageReceived', None),
            "direct_team_hits": battle_data.get('directTeamHits', None),
            "damage_dealt": battle_data.get('damageDealt', None),
            "piercings_received": battle_data.get('piercingsReceived', None),
            "piercings": battle_data.get('piercings', None),
            "prev_mark_of_mastery": battle_data.get('prevMarkOfMastery', None),
            "damaged": battle_data.get('damaged', None),
            "death_reason": battle_data.get('deathReason', None),
            "capture_points": battle_data.get('capturePoints', None),
            "damage_before_team_was_damaged": battle_data.get('damageBeforeTeamWasDamaged', None),
            "explosion_hits_received": battle_data.get('explosionHitsReceived', None),
            "damage_rating": battle_data.get('damageRating', None),
            "mileage": battle_data.get('mileage', None),
            "explosion_hits": battle_data.get('explosionHits', None),
            "direct_hits_received": battle_data.get('directHitsReceived', None),
            "is_team_killer": battle_data.get('isTeamKiller', None),
            "capturing_base": battle_data.get('capturingBase', None),
            "damage_assisted_stun": battle_data.get('damageAssistedStun', None),
            "damage_assisted_smoke": battle_data.get('damageAssistedSmoke', None),
            "t_destroyed_modules": battle_data.get('tdestroyedModules', None),
            "damage_assisted_inspire": battle_data.get('damageAssistedInspire', None)
        }]

        return battle_performance

    @staticmethod
    def get_common(data: dict):
        """
        Extracts the common data from the battle replay.
        """

        raw_data = data.get('common')
        response = {
            "division": raw_data.get('division', None),
            "gui_type": raw_data.get('guiType', None),
            "arena_create_time": raw_data.get('arenaCreateTime', None),
            "duration": raw_data.get('duration', None),
            "arena_type_id": raw_data.get('arenaTypeID', None),
            "gas_attack_winner_team": raw_data.get('gasAttackWinnerTeam', None),
            "winner_team": raw_data.get('winnerTeam', None),
            "veh_lock_mode": raw_data.get('vehLockMode', None),
            "bonus_type": raw_data.get('bonusType', None),
        }

        return response

    @staticmethod
    def get_battle_frags(data: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """
        Извлекает список игроков/техники с фрагами из единого payload.

        Где берём данные:
          • Основной источник: верхнеуровневые блоки с ключами-числами (avatarId),
            в них есть поля: vehicleType, team, isAlive, name, frags и т.д.
          • Фолбэк по фрагам: payload["vehicles"][avatarId][0]["kills"].

        :param data: Единый словарь payload из реплея.
        :return: Список словарей с полями игрока и количеством фрагов.
        """
        if not isinstance(data, Mapping):
            return []

        vehicles_stats = data.get("vehicles")
        result: List[Dict[str, Any]] = []

        for key, raw in data.items():
            # Ищем верхнеуровневые записи игроков: ключ — строка из цифр, значение — dict с 'vehicleType'
            if not (isinstance(key, str) and key.isdigit() and isinstance(raw, Mapping)):
                continue
            if "vehicleType" not in raw:
                continue  # отсекаем посторонние числовые ключи, если вдруг

            avatar_id = key  # строковый ID из реплея (например "46118423")

            # --- фраги ---
            frags = raw.get("frags")
            if frags is None and isinstance(vehicles_stats, Mapping):
                # Фолбэк: kills из блока vehicles[avatar_id][0]
                vlist = vehicles_stats.get(avatar_id)
                if isinstance(vlist, list) and vlist and isinstance(vlist[0], Mapping):
                    frags = vlist[0].get("kills")

            # Нормализуем к int
            try:
                frags_int = int(frags) if frags is not None else 0
            except (TypeError, ValueError):
                frags_int = 0

            vehicle_type = str(raw.get("vehicleType", ""))
            # vehicle_tag: часть после двоеточия, nation: до двоеточия
            if ":" in vehicle_type:
                vehicle_nation, vehicle_tag = vehicle_type.split(":", 1)
            else:
                vehicle_nation, vehicle_tag = "", vehicle_type

            # Собираем запись
            player_entry = {
                "player_id": avatar_id,  # это avatarId из реплея, не accountDBID
                "fake_name": raw.get("fakeName", "None"),
                "team": raw.get("team"),
                "vehicle_type": vehicle_type,
                "vehicle_tag": vehicle_tag,
                "vehicle_nation": vehicle_nation,
                "is_alive": bool(raw.get("isAlive")),
                "forbid_in_battle_invitations": bool(raw.get("forbidInBattleInvitations")),
                "igr_type": raw.get("igrType", 0),
                "is_team_killer": bool(raw.get("isTeamKiller")),
                "name": raw.get("name"),
                "frags": frags_int,
            }
            result.append(player_entry)

        # Фолбэк: если по какой-то причине не нашли верхнеуровневые блоки,
        # можно собрать минимум из 'vehicles' (используя kills). Обычно не требуется.
        if not result and isinstance(vehicles_stats, Mapping):
            for avatar_id, vlist in vehicles_stats.items():
                if not (isinstance(avatar_id, str) and isinstance(vlist, list) and vlist):
                    continue
                v0 = vlist[0] if isinstance(vlist[0], Mapping) else {}
                frags_int = int(v0.get("kills") or 0)
                top = data.get(avatar_id, {}) if isinstance(data.get(avatar_id), Mapping) else {}
                vehicle_type = str(top.get("vehicleType", ""))
                if ":" in vehicle_type:
                    vehicle_nation, vehicle_tag = vehicle_type.split(":", 1)
                else:
                    vehicle_nation, vehicle_tag = "", vehicle_type

                result.append({
                    "player_id": avatar_id,
                    "fake_name": top.get("fakeName", "None"),
                    "team": top.get("team") or v0.get("team"),
                    "vehicle_type": vehicle_type,
                    "vehicle_tag": vehicle_tag,
                    "vehicle_nation": vehicle_nation,
                    "is_alive": bool(top.get("isAlive") or v0.get("health", 0) > 0),
                    "forbid_in_battle_invitations": bool(top.get("forbidInBattleInvitations", False)),
                    "igr_type": top.get("igrType", 0),
                    "is_team_killer": bool(top.get("isTeamKiller", False)),
                    "name": top.get("name"),
                    "frags": frags_int,
                })

        return result

    @staticmethod
    def get_battle_economy(data: list, account_id: str, replay_date: str) -> list:
        """
        Extracts the economy data from the battle replay
        """

        raw_data = data[0]['personal']
        battle_id = list(raw_data.keys())[0]

        battle_data = raw_data[battle_id]

        battle_economy = [{
            "replay_date": replay_date,
            "account_id": account_id,
            "credits_to_draw": battle_data.get('creditsToDraw', None),
            "original_prem_squad_credits": battle_data.get('originalPremSquadCredits', None),
            "credits_contribution_in": battle_data.get('creditsContributionIn', None),
            "event_credits": battle_data.get('eventCredits', None),
            "piggy_bank": battle_data.get('originalPremSquadCredits', None),
            "premium_credits_factor_100": battle_data.get('premiumCreditsFactor100', None),
            "original_credits_contribution_in": battle_data.get('originalCreditsContributionIn', None),
            "original_credits_penalty": battle_data.get('originalPremSquadCredits', None),
            "original_gold": battle_data.get('originalGold', None),
            "booster_credits": battle_data.get('boosterCredits', None),
            "referral_20_credits": battle_data.get('referral20Credits', None),
            "subtotal_event_coin": battle_data.get('subtotalEventCoin', None),
            "booster_credits_factor_100": battle_data.get('boosterCreditsFactor100', None),
            "credits_contribution_out": battle_data.get('creditsContributionOut', None),
            "premium_plus_credits_factor_100": battle_data.get('premiumPlusCreditsFactor100', None),
            "credits": battle_data.get('originalPremSquadCredits', None),
            "gold_replay": battle_data.get('goldReplay', None),
            "credits_penalty": battle_data.get('creditsPenalty', None),
            "repair": battle_data.get('repair', None),
            "original_credits": battle_data.get('originalCredits', None),
            "order_credits": battle_data.get('orderCredits', None),
            "order_credits_factor_100": battle_data.get('orderCreditsFactor100', None),
            "original_crystal": battle_data.get('originalCrystal', None),
            "applied_premium_credits_factor_100": battle_data.get('appliedPremiumCreditsFactor100', None),
            "prem_squad_credits": battle_data.get('premSquadCredits', None),
            "event_gold": battle_data.get('eventGold', None),
            "gold": battle_data.get('gold', None),
            "original_credits_contribution_in_squad": battle_data.get('originalCreditsContributionInSquad', None),
            "original_event_coin": battle_data.get('originalEventCoin', None),
            "factual_credits": battle_data.get('factualCredits', None),
            "event_coin": battle_data.get('eventCoin', None),
            "crystal": battle_data.get('crystal', None),
            "crystal_replay": battle_data.get('crystalReplay', None),
            "original_credits_to_draw_squad": battle_data.get('originalCreditsToDrawSquad', None),
            "subtotal_credits": battle_data.get('subtotalCredits', None),
            "credits_replay": battle_data.get('creditsReplay', None),
            "event_event_coin": battle_data.get('eventEventCoin', None),
            "subtotal_crystal": battle_data.get('subtotalCrystal', None),
            "achievement_credits": battle_data.get('achievementCredits', None),
            "subtotal_gold": battle_data.get('subtotalGold', None),
            "event_crystal": battle_data.get('eventCrystal', None),
            "event_coin_replay": battle_data.get('eventCoinReplay', None),
            "auto_repair_cost": battle_data.get('autoRepairCost', None),
            "original_credits_penalty_squad": battle_data.get('originalCreditsPenaltySquad', None)
        }]

        return battle_economy

    @staticmethod
    def get_battle_xp(data: list, account_id: str, replay_date: str) -> list:
        """
        Extracts the xp data from the battle replay
        """

        raw_data = data[0]['personal']
        battle_id = list(raw_data.keys())[0]

        battle_data = raw_data[battle_id]

        battle_xp = [{
            "replay_date": replay_date,
            "account_id": account_id,
            "order_free_xp_factor_100": battle_data.get('orderFreeXPFactor100', None),
            "order_xp_factor_100": battle_data.get('orderXPFactor100', None),
            "free_xp_replay": battle_data.get('freeXPReplay', None),
            "xp_other": battle_data.get('xp/other', None),
            "premium_t_men_xp_factor_100": battle_data.get('premiumTmenXPFactor100', None),
            "achievement_xp": battle_data.get('achievementXP', None),
            "igr_xp_factor_10": battle_data.get('igrXPFactor10', None),
            "event_t_men_xp": battle_data.get('eventTMenXP', None),
            "premium_plus_xp_factor_100": battle_data.get('premiumPlusXPFactor100', None),
            "premium_plus_t_men_xp_factor_100": battle_data.get('premiumPlusTmenXPFactor100', None),
            "original_t_men_xp": battle_data.get('originalTMenXP', None),
            "referal_20_xp": battle_data.get('referral20XP', None),
            "subtotal_t_men_xp": battle_data.get('subtotalTMenXP', None),
            "premium_vehicle_xp_factor_100": battle_data.get('premiumVehicleXPFactor100', None),
            "additional_xp_factor_100": battle_data.get('additionalXPFactor10', None),
            "factual_xp": battle_data.get('factualXP', None),
            "order_free_xp": battle_data.get('orderFreeXP', None),
            "booster_t_men_xp_factor_100": battle_data.get('boosterTMenXPFactor100', None),
            "original_xp": battle_data.get('originalXP', None),
            "applied_premium_xp_factor_100": battle_data.get('appliedPremiumXPFactor100', None),
            "booster_xp": battle_data.get('boosterXP', None),
            "factual_free_xp": battle_data.get('factualFreeXP', None),
            "daily_xp_factor_10": battle_data.get('dailyXPFactor10', None),
            "event_free_xp": battle_data.get('eventFreeXP', None),
            "player_rank_xp_factor_100": battle_data.get('playerRankXPFactor100', None),
            "xp_penalty": battle_data.get('xpPenalty', None),
            "xp": battle_data.get('xp', None),
            "booster_xp_factor_100": battle_data.get('boosterXPFactor100', None),
            "order_t_men_xp": battle_data.get('orderTMenXP', None),
            "original_xp_penalty": battle_data.get('originalXPPenalty', None),
            "order_t_men_xp_factor_100": battle_data.get('orderTMenXPFactor100', None),
            "subtotal_xp": battle_data.get('subtotalXP', None),
            "squad_xp": battle_data.get('squadXP', None),
            "original_free_xp": battle_data.get('originalFreeXP', None),
            "xp_assist": battle_data.get('xp/assist', None),
            "free_xp": battle_data.get('freeXP', None),
            "premium_vehicle_xp": battle_data.get('premiumVehicleXP', None),
            "referral_20_xp_factor_100": battle_data.get('referral20XPFactor100', None),
            "event_xp": battle_data.get('eventXP', None),
            "subtotal_free_xp": battle_data.get('subtotalFreeXP', None),
            "achievement_free_xp": battle_data.get('achievementFreeXP', None),
            "player_rank_xp": battle_data.get('playerRankXP', None),
            "squad_xp_factor_100": battle_data.get('squadXPFactor100', None),
            "applied_premium_t_men_xp_factor_100": battle_data.get('appliedPremiumTmenXPFactor100', None),
            "booster_t_men_xp": battle_data.get('boosterTMenXP', None),
            "xp_attack": battle_data.get('xp/attack', None),
            "ref_system_xp_factor_10": battle_data.get('refSystemXPFactor10', None),
            "t_men_xp_replay": battle_data.get('tmenXPReplay', None),
            "premium_xp_factor_100": battle_data.get('premiumXPFactor100', None),
            "t_men_xp": battle_data.get('tmenXP', None),
            "booster_free_xp_factor_100": battle_data.get('boosterFreeXPFactor100', None),
            "booster_free_xp": battle_data.get('boosterFreeXP', None),
            "battle_num": battle_data.get('battleNum', None)

        }]

        return battle_xp

    @staticmethod
    def extract_replay_fields(replay_data, file_name: str) -> Dict[str, Any]:
        """
        Извлекает поля для модели Replay из ЕДИНОГО словаря replay_data.

        Args:
            replay_data: Единый dict, полученный после глубокого слияния всех JSON-объектов.
            file_name  : Имя файла реплея.

        Returns:
            Dict[str, Any]: Словарь с полями для создания объекта Replay.

        Raises:
            ValueError: Если структура данных некорректна или не найдены персональные данные игрока.
        """
        # Находим данные текущего игрока
        player_name = replay_data.get("playerName")
        player_id = replay_data.get("playerID")

        # Персональные данные находятся в top-level ключе 'personal' (dict: typeCompDescr -> data)
        personal = replay_data.get("personal") or {}
        if not isinstance(personal, dict):
            raise ValueError("Некорректная структура replay_data: 'personal' должен быть dict")

        # Ищем персональные данные игрока
        personal_data = None
        if personal:
            # Персональные данные хранятся по typeCompDescr танка
            for tank_type, data in personal.items():
                if data.get('accountDBID') == player_id:
                    personal_data = data
                    break

        if not personal_data:
            raise ValueError(f"Не найдены персональные данные для игрока {player_name}")

        replay_date = replay_data.get('dateTime')
        battle_date = datetime.datetime.strptime(replay_date, '%d.%m.%Y%H:%M:%S')

        # Извлекаем поля для модели
        fields = {
            'file_name': file_name,
            'payload': replay_data,
            "tank_tag": str(replay_data.get('playerVehicle')).split("-", 1)[1],
            'mastery': personal_data.get('markOfMastery'),
            'battle_date': battle_date,
            'map_name': replay_data.get('mapName'),
            'map_display_name': replay_data.get('mapDisplayName'),
            'credits': personal_data.get('credits', 0),
            'xp': personal_data.get('xp', 0),
            'kills': personal_data.get('kills', 0),
            'damage': personal_data.get('damageDealt', 0),
            'assist': Extractor._calculate_total_assist(personal_data),
            'block': personal_data.get('damageBlockedByArmor', 0),
        }

        return fields

    @staticmethod
    def get_achievements(payload: Dict[str, Any]) -> List[int]:
        """
        Вернёт список ID достижений текущего игрока.
        Берём прямо из payload['personal'][...]['achievements'].

        Логика:
        - Находим запись в 'personal', где accountDBID == payload['playerID'].
        - Возвращаем поле 'achievements' (если нет — пустой список).
        """
        player_id = payload.get("playerID")

        p = Extractor.get_personal_by_player_id(payload, player_id, fallback_first=False)
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
    def get_details_data(payload: Dict[str, Any]) -> Dict[str, Any]:

        player_id = payload.get("playerID")

        personal = Extractor.get_personal_by_player_id(payload, player_id, fallback_first=False)

        details_data = {
            'xp': personal.get('xp'),
            'originalCredits': personal.get('originalCredits'),
            'repair': personal.get('repair'),

            'serverName': payload.get('serverName'),
            'battleType': payload.get('battleType'),
            'clientVersion': payload.get('clientVersionFromExe'),
            'playerName': payload.get('playerName'),
        }
        return details_data

    @staticmethod
    def _parse_target_avatar_id(key: str) -> Optional[str]:
        """
        Разбирает ключ details вида "(46118422,0)" -> "46118422".
        Возвращает None, если формат не совпал.
        """
        _TARGET_KEY_RE = re.compile(r"^\((\d+),\d+\)$")  # формат ключа в details: "(46118422,0)"
        m = _TARGET_KEY_RE.match(key)
        return m.group(1) if m else None

    @staticmethod
    def _avatar_info(payload: Mapping[str, Any], avatar_id: str) -> Dict[str, Any]:
        top = payload.get(avatar_id) or {}
        vtype = str(top.get("vehicleType", ""))
        nation, tag = ("", vtype)
        if ":" in vtype:
            nation, tag = vtype.split(":", 1)
        return {
            "avatar_id": avatar_id,
            "name": top.get("name") or avatar_id,
            "vehicle_type": vtype,
            "vehicle_tag": tag,
            "vehicle_img": f"style/images/wot/shop/vehicles/180x135/{tag}.png" if tag else "tanks/tank_placeholder.png",
            "team": top.get("team"),
        }

    # --- ОСНОВНАЯ ЛОГИКА ---------------------------------------------------------
    @staticmethod
    def get_player_interactions(payload: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Собирает списки техники (по аватару противника), над которой игрок:
          - обнаружил (spotted > 0)
          - помог в уничтожении (assist > 0: track/radio/stun/smoke/inspire)
          - заблокировал урон (есть заблок/рикошеты/нодамаг-хиты от цели)
          - нанёс критические попадания (crits > 0)
          - нанёс урон (damageDealt > 0)
          - уничтожил (targetKills > 0)

        Возвращает dict с ключами: 'spotted', 'assist', 'blocked', 'crits', 'damaged', 'destroyed'.
        Значение каждого ключа — список словарей с полями техники (avatar_id, vehicle_tag, ...).
        """
        # 1) Берём details текущего игрока
        personal = Extractor.get_personal_by_player_id(payload) or {}
        details = personal.get("details")
        if not isinstance(details, Mapping) or not details:
            # Нет покиловой детализации — вернём пустые списки
            return {k: [] for k in ("spotted", "assist", "blocked", "crits", "damaged", "destroyed")}

        out = {
            "spotted": [],   # обнаружил
            "assist": [],    # помог в уничтожении
            "blocked": [],   # заблокировал урон
            "crits": [],     # нанёс крит. попадания
            "damaged": [],   # нанёс урон
            "destroyed": [], # уничтожил
        }

        # 2) Обходим цели в details: ключ "(avatarId,0)" -> значение с метриками по этой цели
        for key, d in details.items():
            if not isinstance(d, Mapping):
                continue
            avatar_id = Extractor._parse_target_avatar_id(str(key))
            if not avatar_id:
                continue

            # Значения по умолчанию = 0
            spotted = int(d.get("spotted") or 0)

            assist = (
                int(d.get("damageAssistedTrack") or 0) +
                int(d.get("damageAssistedRadio") or 0) +
                int(d.get("damageAssistedStun") or 0) +
                int(d.get("damageAssistedSmoke") or 0) +
                int(d.get("damageAssistedInspire") or 0)
            )

            # Блок: любые индикаторы «вы заблокировали выстрелы/урон от этой цели»
            blocked = (
                int(d.get("damageBlockedByArmor") or 0) +
                int(d.get("rickochetsReceived") or 0) +
                int(d.get("noDamageDirectHitsReceived") or 0)
            )

            # Криты: в WoT это часто битовая маска, потому проверяем просто > 0
            crits = int(d.get("crits") or 0)

            # Урон и уничтожения по конкретной цели
            damage_dealt = int(d.get("damageDealt") or 0)
            target_kills = int(d.get("targetKills") or 0)

            # Если по этой цели есть хотя бы одна из активностей — добавим карточку техники
            info = Extractor._avatar_info(payload, avatar_id)

            if spotted > 0:
                out["spotted"].append(info)
            if assist > 0:
                out["assist"].append(info)
            if blocked > 0:
                out["blocked"].append(info)
            if crits > 0:
                out["crits"].append(info)
            if damage_dealt > 0:
                out["damaged"].append(info)
            if target_kills > 0:
                out["destroyed"].append(info)

        # 3) Убираем дубликаты на случай повторов (сохраняем порядок)
        for k in out:
            seen = set()
            uniq = []
            for item in out[k]:
                aid = item["avatar_id"]
                if aid not in seen:
                    uniq.append(item)
                    seen.add(aid)
            out[k] = uniq

        return out

    @staticmethod
    def build_interaction_rows(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """
        Готовит строки для шаблона по деталям текущего игрока.
        Для каждой цели считает количества: засветы, ассист (сумма урона),
        блок (события), криты (popcount), урон (пробития), уничтожения.
        """
        personal = Extractor.get_personal_by_player_id(payload) or {}
        details = personal.get("details")
        if not isinstance(details, Mapping):
            return []

        rows: Dict[str, Dict[str, Any]] = {}

        for k, d in details.items():
            if not isinstance(d, Mapping):
                continue
            aid = Extractor._parse_target_avatar_id(str(k))
            if not aid:
                continue

            info = rows.setdefault(aid, {
                **Extractor._avatar_info(payload, aid),
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
    def _death_reason_to_text(code: int) -> str:
        """
        Преобразует код причины смерти в понятный текст.
        По данным реплеев:  -1 = жив, 0 = выстрел (типовая смерть).
        Остальные коды при необходимости дополни.
        """
        mapping = {
            0: "выстрелом",
            1: "тараном",
            2: "пожаром",
            3: "переворотом/утоплением",
        }
        return mapping.get(int(code), "уничтожен")

    @staticmethod
    def get_killer_name(payload: Mapping[str, Any], default: str = "") -> str:
        """
        Возвращает ник убийцы по killerID из personal текущего игрока.
        Если игрок выжил или данных нет — вернёт default.
        """
        p = Extractor.get_personal_by_player_id(payload) or {}
        killer_id = p.get("killerID")
        try:
            killer_id_int = int(killer_id)
        except (TypeError, ValueError):
            killer_id_int = 0

        if killer_id_int <= 0:
            return default

        killer = payload.get(str(killer_id_int)) or {}
        # В верхнеуровневом блоке по avatarId есть 'name' (а для ботов ещё и fakeName)
        return killer.get("name") or killer.get("fakeName") or str(killer_id_int)

    @staticmethod
    def get_death_text(payload: Mapping[str, Any]) -> str:
        """
        Строит строку для шаблона:
          - "Выжил", если deathReason == -1
          - "Уничтожен <причина> (<ник>)", если погиб
        """
        p = Extractor.get_personal_by_player_id(payload) or {}
        death_reason = p.get("deathReason", -1)
        try:
            dr = int(death_reason)
        except (TypeError, ValueError):
            dr = -1

        if dr == -1:
            return "Выжил"

        reason = Extractor._death_reason_to_text(dr)
        killer = Extractor.get_killer_name(payload)
        return f"Уничтожен {reason}" + (f" ({killer})" if killer else "")

    @staticmethod
    def build_income_summary(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Сводка для блока income:
        - кредиты для базового и прем-аккаунта,
        - опыт (обычный и с "первой победой"),
        - меткость (попадания/выстрелы и %),
        - суммарный ассист и нанесённый урон.
        """
        # персональные данные текущего игрока
        p = Extractor.get_personal_by_player_id(payload) or {}
        common = payload.get('common') or {}

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

        # --- меткость ---
        shots = int(p.get('shots') or 0)
        hits = int(p.get('directHits') or p.get('directEnemyHits') or 0)
        hit_percent = (hits / shots * 100.0) if shots > 0 else 0.0

        # --- ассист и урон ---
        assist_total = Extractor._calculate_total_assist(p)  # суммарный ассист-урон
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
    def get_battle_type_label(payload: Mapping[str, Any]) -> str:
        """
        Вернёт человекочитаемое название типа боя.
        Приоритет: gameplayID (строка) → fallback по battleType/bonusType (число) → 'Неизвестный режим'.
        """
        # основные режимы WoT
        gp_map = {
            "ctf": "Стандартный бой",
            "domination": "Встречный бой",
            "assault": "Штурм",
            "assault2": "Штурм",
            "epic_battle": "Линия фронта",
            "epic": "Линия фронта",
            "nations": "Нации",
            "battle_royale": "Стальной охотник",
            "ranked": "Ранговый бой",
            "clan": "Укрепрайон",
            "sandbox": "Тренировочный бой",
            "tutorial": "Тренировка",
            "ctf30x30": "Большие бои",
            # при необходимости дополняй
        }

        gameplay_id = str(payload.get("gameplayID") or "").strip()
        if gameplay_id:
            return gp_map.get(gameplay_id, "Неизвестный режим")

        # На случай отсутствия gameplayID попробуем числовые коды
        # ВНИМАНИЕ: это не тип режима, а тип "бонус-боя", оставим общее имя.
        bt = payload.get("battleType")
        bonus = (payload.get("common") or {}).get("bonusType")
        for code in (bt, bonus):
            try:
                if int(code) == 1:
                    return "Случайный бой"
                if int(code) == 2:
                    return "Ротный/Командный бой"
                if int(code) == 10:
                    return "Ранговый бой"
                # и т.п., по мере необходимости
            except (TypeError, ValueError):
                pass

        return "Неизвестный режим"

    @staticmethod
    def _get_player_team(payload: Mapping[str, Any]) -> int | None:
        """
        Возвращает номер команды игрока (1 или 2).
        Сначала из personal, затем из players по accountID.
        """
        p = Extractor.get_personal_by_player_id(payload) or {}
        team = p.get("team")
        if isinstance(team, int):
            return team

        acc_id = payload.get("playerID")
        players = payload.get("players") or {}
        rec = players.get(str(acc_id)) or players.get(acc_id) or {}
        team = rec.get("team")
        return int(team) if isinstance(team, int) else None

    @staticmethod
    def get_battle_outcome(payload: Mapping[str, Any]) -> dict[str, str]:
        """
        Формирует текст статуса ('Победа! / Поражение / Ничья'),
        CSS-класс и человекочитаемую причину завершения боя.
        """
        common = payload.get("common") or {}
        winner_team = common.get("winnerTeam")       # 0 = ничья
        finish_reason = common.get("finishReason")   # 1 — уничтожены, 2 — база, 3 — время и т.д.
        player_team = Extractor._get_player_team(payload)

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
    def split_achievements_by_type(achievements_ids: Iterable[int]):
        """
        Делит достижения на небoевые и боевые по полю `achievement_type`,
        сортирует по весу (`order` DESC) и названию. Возвращает (nonbattle_qs, battle_qs).
        """
        from replays.models import Achievement  # чтобы избежать циклического импорта

        ids = list({int(x) for x in (achievements_ids or [])})
        if not ids:
            empty = Achievement.objects.none()
            return empty, empty

        # ВАЖНО: кастим order к Float, чтобы не было смешения типов в Coalesce
        qs = (
            Achievement.objects
            .filter(achievement_id__in=ids, is_active=True)
            .annotate(
                weight=Coalesce(
                    Cast('order', FloatField()),
                    Value(0.0),
                    output_field=FloatField(),
                )
            )
        )

        battle_types = ('battle', 'epic')  # добавь 'mastery', если надо относить к боевым
        ach_battle_qs = qs.filter(achievement_type__in=battle_types).order_by('-weight', 'name')
        ach_nonbattle_qs = qs.exclude(achievement_type__in=battle_types).order_by('-weight', 'name')

        return ach_nonbattle_qs, ach_battle_qs