# wotreplay/helper/extractor.py
import os
import datetime
import re
from typing import Any, Dict, List, Optional, Mapping, Iterable, Sequence, Tuple

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
    def get_personal_by_player_id(payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Вернуть блок personal для указанного игрока.

        :param payload: Единый словарь реплея (payload).
        :return: dict с персональными данными игрока или None.
        """

        personal = payload.get("personal")
        if not isinstance(personal, Mapping):
            return None

        # --- Ищем числовые ключи ---
        # Ключи приходят строками из JSON. Берём только те, что целиком состоят из цифр.
        numeric_keys: Sequence[str] = [k for k in personal.keys() if isinstance(k, str) and k.isdigit()]

        # --- Обработка числа найденных ключей ---
        if len(numeric_keys) == 1:
            return personal[numeric_keys[0]]

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

        p = Extractor.get_personal_by_player_id(payload)
        print(f"personal: {p}")
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

        personal = Extractor.get_personal_by_player_id(payload)
        # print(f"personal: {personal}")

        details_data = {
            'xp': personal.get('xp'),
            'credits': personal.get('credits'),
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
        vehicle_name = Extractor._get_vehicle_display_name(tag)
        return {
            "avatar_id": avatar_id,
            "name": top.get("name") or avatar_id,
            "vehicle_type": vtype,
            "vehicle_tag": tag,
            "vehicle_name": vehicle_name,
            "vehicle_img": f"style/images/wot/shop/vehicles/180x135/{tag}.png" if tag else "tanks/tank_placeholder.png",
            "team": top.get("team"),
        }

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
    def get_team_results(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Извлекает командные результаты для отображения в шаблоне.
        Союзники игрока всегда в allies_players, противники в enemies_players.

        Returns:
            Dict с ключами:
            - 'allies_players': список игроков команды союзников (команда игрока)
            - 'enemies_players': список игроков команды противников
            - 'allies_name': "Союзники"
            - 'enemies_name': "Противник"
        """
        vehicles_stats = payload.get("vehicles") or {}
        players_info = payload.get("players") or {}

        # Определяем команду текущего игрока
        player_team = Extractor._get_player_team(payload)
        if player_team is None:
            # Фолбэк: если не можем определить команду игрока
            player_team = 1

        allies_players = []
        enemies_players = []

        # Обходим всех игроков
        for avatar_id, raw in payload.items():
            if not (isinstance(avatar_id, str) and avatar_id.isdigit() and isinstance(raw, Mapping)):
                continue
            if "vehicleType" not in raw:
                continue

            player_data = Extractor._build_player_data(avatar_id, raw, vehicles_stats, players_info, payload)
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

        return {
            'allies_players': allies_players,
            'enemies_players': enemies_players,
            'allies_name': "Союзники",
            'enemies_name': "Противник",
        }

    @staticmethod
    def _build_player_data(avatar_id: str, raw: Mapping[str, Any], vehicles_stats: Mapping[str, Any],
                           players_info: Mapping[str, Any], payload: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Формирует данные игрока для командного результата.
        """
        # Базовая информация
        vehicle_type = str(raw.get("vehicleType", ""))
        if ":" in vehicle_type:
            vehicle_nation, vehicle_tag = vehicle_type.split(":", 1)
        else:
            vehicle_nation, vehicle_tag = "", vehicle_type

        # Статистика из vehicles
        vstats = {}
        vehicle_list = vehicles_stats.get(avatar_id, [])
        if isinstance(vehicle_list, list) and vehicle_list:
            vstats = vehicle_list[0] if isinstance(vehicle_list[0], dict) else {}

        # Информация об игроке
        player_info = players_info.get(avatar_id, {})
        if not isinstance(player_info, dict):
            # Ищем по accountDBID в players
            account_id = vstats.get("accountDBID")
            if account_id:
                for pid, pinfo in players_info.items():
                    if isinstance(pinfo, dict) and pinfo.get("accountDBID") == account_id:
                        player_info = pinfo
                        break

        # Определяем статус жизни
        death_reason = vstats.get("deathReason", -1)
        is_alive = death_reason == -1
        killer_id = vstats.get("killerID", 0)

        # Текст причины смерти
        death_text = ""
        if not is_alive and killer_id > 0:
            killer_data = payload.get(str(killer_id), {})
            killer_name = killer_data.get("name") or killer_data.get("fakeName", "")
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

        # Получаем уровень танка и тип
        tank_level = Extractor._extract_tank_level(vehicle_tag)
        tank_type_icon = Extractor._get_tank_type_icon(vehicle_tag)

        # Клан
        clan_tag = player_info.get("clanAbbrev", "")
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

        medals_data = Extractor._get_player_medals(vstats.get("achievements", []))

        # Определяем, является ли это текущим игроком (владельцем реплея)
        current_player_id = payload.get("playerID")  # ID текущего игрока
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
            "vehicle_type": vehicle_type,
            "vehicle_tag": vehicle_tag,
            "vehicle_nation": vehicle_nation,
            "vehicle_display_name": Extractor._get_vehicle_display_name(vehicle_tag),
            "tank_level": tank_level,
            "tank_type_icon": tank_type_icon,
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
            "platoon_id": Extractor._get_platoon_id(avatar_id, payload),
        }

    @staticmethod
    def _get_player_medals(achievement_ids: list) -> Dict[str, Any]:
        """
        Получает информацию о медалях игрока из базы данных.
        Возвращает только боевые и эпические достижения.
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
    def _extract_tank_level(vehicle_tag: str) -> int:
        """Извлекает уровень танка из тега (примерная логика)."""
        # Простая логика - в реальности нужна база данных танков
        level_patterns = {
            '_T1_': 1, '_T2_': 2, '_T3_': 3, '_T4_': 4, '_T5_': 5,
            '_T6_': 6, '_T7_': 7, '_T8_': 8, '_T9_': 9, '_T10_': 10
        }
        for pattern, level in level_patterns.items():
            if pattern in vehicle_tag:
                return level
        return 6  # по умолчанию

    @staticmethod
    def _get_tank_type_icon(vehicle_tag: str) -> str:
        """Возвращает иконку типа танка."""
        if 'SPG' in vehicle_tag.upper() or 'arty' in vehicle_tag.lower():
            return 'style/images/wot/vehicleTypes/SPG.png'
        elif 'AT' in vehicle_tag.upper() or 'TD' in vehicle_tag.upper():
            return 'style/images/wot/vehicleTypes/AT-SPG.png'
        elif 'heavy' in vehicle_tag.lower() or 'HT' in vehicle_tag.upper():
            return 'style/images/wot/vehicleTypes/heavyTank.png'
        elif 'light' in vehicle_tag.lower() or 'LT' in vehicle_tag.upper():
            return 'style/images/wot/vehicleTypes/lightTank.png'
        else:
            return 'style/images/wot/vehicleTypes/mediumTank.png'

    @staticmethod
    def _get_vehicle_display_name(vehicle_tag: str) -> str:
        """Преобразует тег танка в отображаемое имя."""
        # Убираем префиксы стран и технические суффиксы
        name = vehicle_tag
        if name.startswith(("Un", "GB", "Ch", "Cz", "Pl", "It", "S", "J", "F", "G", "R", "A")):
            parts = name.split('_')
            if len(parts) > 1:
                name = '_'.join(parts[1:])

        # Заменяем подчеркивания на пробелы и убираем технические суффиксы
        name = name.replace('_', ' ').strip()
        for suffix in [' SH', ' Berlin', ' test', ' premium']:
            if name.endswith(suffix):
                name = name[:-len(suffix)]

        return name.title()

    @staticmethod
    def _get_platoon_id(avatar_id: str, payload: Mapping[str, Any]) -> Optional[int]:
        """Определяет ID взвода игрока."""
        # В реплеях информация о взводах может быть в разных местах
        # Это примерная логика - нужно изучить конкретную структуру

        # Поиск в common.bots или других местах
        bots = (payload.get("common") or {}).get("bots") or {}
        if avatar_id in bots:
            bot_data = bots[avatar_id]
            if isinstance(bot_data, list) and len(bot_data) > 0:
                # Возможно здесь есть информация о группировке
                pass

        # Пока возвращаем None - нужна дополнительная логика
        return None

    # В replays/utils.py в класс Extractor добавляем:


    @staticmethod
    def get_detailed_report(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Извлекает детализированные данные для подробного отчета.
        """
        personal = Extractor.get_personal_by_player_id(payload) or {}
        common = payload.get('common') or {}

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
            "assist_total": Extractor._calculate_total_assist(personal),
            "capture_points": int(personal.get('capturePoints', 0)),
            "defense_points": int(personal.get('droppedCapturePoints', 0)),
            "distance": round(int(personal.get('mileage', 0)) / 1000, 2),
            "stun_damage": int(personal.get('damageAssistedStun', 0)),
            "stun_count": int(personal.get('stunNum', 0)),
        }

        # === РАСШИРЕННАЯ ЭКОНОМИКА ===
        # Базовые доходы
        original_credits = int(personal.get('originalCredits', 0))
        achievement_credits = int(personal.get('achievementCredits', 0))

        # Штрафы и компенсации
        credits_penalty = int(personal.get('creditsPenalty', 0))
        team_damage_penalty = int(personal.get('originalCreditsPenalty', 0))

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

        # Промежуточные итоги
        battle_earnings = original_credits + achievement_credits - team_damage_penalty
        total_expenses = auto_repair_cost + ammo_cost + equipment_credits_cost
        net_result = battle_earnings - total_expenses

        # Премиум факторы
        premium_credit_factor = (int(personal.get('premiumCreditsFactor100', 100))) / 100.0
        is_premium = premium_credit_factor > 1.0

        # Премиум расчеты
        premium_original_credits = int(original_credits * premium_credit_factor)
        premium_achievement_credits = int(
            achievement_credits * premium_credit_factor) if achievement_credits > 0 else achievement_credits
        premium_battle_earnings = premium_original_credits + premium_achievement_credits - team_damage_penalty
        premium_net_result = premium_battle_earnings - total_expenses

        # === ОПЫТ ===
        original_xp = int(personal.get('originalXP', 0))
        original_free_xp = int(personal.get('originalFreeXP', 0))
        event_xp = int(personal.get('eventXP', 0))
        event_free_xp = int(personal.get('eventFreeXP', 0))

        total_original_xp = original_xp + event_xp

        premium_xp_factor = (int(personal.get('premiumXPFactor100', 100))) / 100.0

        premium_xp = int(original_xp * premium_xp_factor)
        premium_free_xp = int(original_free_xp * premium_xp_factor)
        premium_event_xp = int(event_xp * premium_xp_factor)
        premium_event_free_xp = int(event_free_xp * premium_xp_factor)

        total_premium_xp = premium_xp + premium_event_xp

        # === БОНДЫ/КРИСТАЛЛЫ ===
        crystal = int(personal.get('crystal', 0))
        original_crystal = int(personal.get('originalCrystal', 0))
        achievement_crystal = crystal - original_crystal if crystal > original_crystal else 0
        special_vehicle_crystal = max(0, original_crystal)  # "За особые свойства машины"

        economics = {
            # Базовые доходы
            "original_credits": original_credits,
            "achievement_credits": achievement_credits,
            "battle_earnings": battle_earnings,

            # Премиум доходы
            "premium_original_credits": premium_original_credits,
            "premium_achievement_credits": premium_achievement_credits,
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
            "original_xp": original_xp,
            "original_free_xp": original_free_xp,
            "event_xp": event_xp,
            "event_free_xp": event_free_xp,
            "total_original_xp": total_original_xp,

            "premium_xp": premium_xp,
            "premium_free_xp": premium_free_xp,
            "premium_event_xp": premium_event_xp,
            "premium_event_free_xp": premium_event_free_xp,
            "total_premium_xp": total_premium_xp,

            # Кристаллы
            "achievement_crystal": achievement_crystal,
            "special_vehicle_crystal": special_vehicle_crystal,
            "total_crystal": crystal,

            "is_premium": is_premium,
        }

        # === ВРЕМЯ ===
        battle_duration = int(common.get('duration', 0))
        lifetime = int(personal.get('lifeTime', 0))

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
            date_time_str = payload.get('dateTime', '')
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
            "lifetime_formatted": f"{lifetime // 60}:{lifetime % 60:02d}",
            "survival_time_percent": round((lifetime / battle_duration * 100), 1) if battle_duration > 0 else 0,
            "battle_start_time": arena_create_time,
            "battle_start_formatted": battle_start_formatted,
            "battle_start_datetime": battle_start_datetime,
        }

        # === ИНФОРМАЦИЯ О ТЕХНИКЕ === (оставляем как есть)
        vehicle_type = payload.get('playerVehicle', '')
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
            "time_stats": time_stats,
            "vehicle_info": vehicle_info,
        }

    @staticmethod
    def parse_players_payload(payload: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        Достаёт из payload кортежи (nickname, clan_tag).
        Ожидаемый формат payload["players"] = { "45977": {...}, "94007": {...}, ... }.

        Возвращает список без пустых/битых записей, без дублей.
        """
        data = payload.get("players") or {}
        seen: set[Tuple[str, str]] = set()
        result: List[Tuple[str, str]] = []

        # Внутри словаря ключи — любые ID; берём только значения
        for p in data.values():
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

    @staticmethod
    def get_replay_owner_from_payload(payload):
        """
        Возвращает кортеж (name, real_name, clan_tag) — всегда 3 значения, пустые строки если нет данных.
        """
        owner_real_name = (payload.get('playerName') or '').strip()
        if owner_real_name and 'players' in payload:
            for _, player_data in (payload.get('players') or {}).items():
                if (player_data.get('realName') or '').strip() == owner_real_name:
                    owner_name = (player_data.get('name') or '').strip()
                    clan_tag = (player_data.get('clanAbbrev') or '').strip()
                    return owner_name, owner_real_name, clan_tag
            # не нашли в players — вернём без клана, и name=real_name
            return owner_real_name, owner_real_name, ''
        return '', '', ''
