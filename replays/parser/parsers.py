# replays/parsers.py
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import logging


logger = logging.getLogger(__name__)


def extract_replay_data(json_data: Union[str, dict]) -> dict:
    """
    Извлекает структурированные данные из JSON реплея World of Tanks.

    Args:
        json_data: JSON строка или словарь с данными реплея

    Returns:
        dict: Структурированные данные боя

    Raises:
        ValueError: Если не удается найти данные игрока
        json.JSONDecodeError: Если JSON невалидный
    """

    # Парсим JSON если передана строка
    if isinstance(json_data, str):
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Невалидный JSON: {str(e)}", "", 0)
    else:
        data = json_data

    def safe_get(obj: Any, key: str, default: Any = None) -> Any:
        """Безопасное получение значения из словаря или объекта"""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return default

    def calculate_hit_rate(hits: int, shots: int) -> float:
        """Вычисляет процент попаданий"""
        if shots == 0:
            return 0.0
        return round((hits / shots) * 100, 2)

    def calculate_total_assist(personal_data: dict) -> int:
        """Вычисляет общий ассист"""
        assist_types = [
            'damageAssistedRadio',
            'damageAssistedTrack',
            'damageAssistedStun',
            'damageAssistedSmoke',
            'damageAssistedInspire'
        ]
        return sum(safe_get(personal_data, assist_type, 0) for assist_type in assist_types)

    def extract_detailed_enemy_stats(details: dict, vehicles_data: dict) -> dict:
        """Извлекает детальную статистику по каждому противнику"""
        enemies = {}

        for enemy_key, damage_data in details.items():
            if not isinstance(damage_data, dict):
                continue

            enemy_id = enemy_key.strip('()').split(',')[0].strip() if isinstance(enemy_key,
                                                                                 str) and enemy_key.startswith(
                '(') else str(enemy_key)

            # Находим данные противника в секции vehicles
            enemy_vehicle_data = None
            for vehicle_id, vehicle_info_list in vehicles_data.items():
                if str(vehicle_id) == enemy_id and vehicle_info_list:
                    enemy_vehicle_data = vehicle_info_list[0]
                    break

            enemies[enemy_id] = {
                # Урон и попадания
                "damage_dealt": safe_get(damage_data, 'damageDealt', 0),
                "direct_hits": safe_get(damage_data, 'directHits', 0),
                "piercings": safe_get(damage_data, 'piercings', 0),
                "target_kills": safe_get(damage_data, 'targetKills', 0),

                # Критические попадания (детальная статистика)
                "crits_total": bin(safe_get(damage_data, 'crits', 0)).count('1') if safe_get(damage_data,
                                                                                             'crits') else 0,
                "crits_bitmask": safe_get(damage_data, 'crits', 0),

                # Ассист по этому противнику
                "damage_assisted_radio": safe_get(damage_data, 'damageAssistedRadio', 0),
                "damage_assisted_track": safe_get(damage_data, 'damageAssistedTrack', 0),
                "damage_assisted_stun": safe_get(damage_data, 'damageAssistedStun', 0),

                # Блокированный урон от этого противника
                "damage_blocked": safe_get(damage_data, 'damageBlockedByArmor', 0),
                "damage_received": safe_get(damage_data, 'damageReceived', 0),
                "ricochets": safe_get(damage_data, 'rickochetsReceived', 0),
                "no_damage_hits": safe_get(damage_data, 'noDamageDirectHitsReceived', 0),

                # Информация о танке противника (если доступна)
                "enemy_vehicle_info": {
                    "max_health": safe_get(enemy_vehicle_data, 'maxHealth', 0) if enemy_vehicle_data else 0,
                    "type_comp_descr": safe_get(enemy_vehicle_data, 'typeCompDescr', 0) if enemy_vehicle_data else 0,
                    "final_health": safe_get(enemy_vehicle_data, 'health', 0) if enemy_vehicle_data else 0,
                    "is_dead": safe_get(enemy_vehicle_data, 'deathCount', 0) > 0 if enemy_vehicle_data else False,
                    "killer_id": safe_get(enemy_vehicle_data, 'killerID', 0) if enemy_vehicle_data else 0,
                    "team": safe_get(enemy_vehicle_data, 'team', 0) if enemy_vehicle_data else 0,
                } if enemy_vehicle_data else None
            }

        return enemies

    def extract_ricochets_and_bounces(player_data: dict, details: dict) -> dict:
        """Извлекает детальную статистику рикошетов и непробитий"""
        total_ricochets = 0
        total_bounces = 0
        blocked_damage = 0

        # Подсчитываем рикошеты и непробития по всем противникам
        for enemy_data in details.values():
            if isinstance(enemy_data, dict):
                total_ricochets += safe_get(enemy_data, 'rickochetsReceived', 0)
                total_bounces += safe_get(enemy_data, 'noDamageDirectHitsReceived', 0)
                blocked_damage += safe_get(enemy_data, 'damageBlockedByArmor', 0)

        return {
            "ricochets": total_ricochets,
            "bounces": total_bounces,
            "blocked_damage": blocked_damage,
            "total_armor_effectiveness": total_ricochets + total_bounces
        }

    def calculate_battle_performance(player_data: dict) -> dict:
        """Вычисляет показатели эффективности боя"""
        damage = safe_get(player_data, 'damageDealt', 0)
        max_hp = safe_get(player_data, 'maxHealth', 1)

        return {
            "damage_ratio": round(damage / max_hp, 2) if max_hp > 0 else 0,
            "survival_factor": 1 if safe_get(player_data, 'deathReason', 0) == -1 else 0,
            "experience_per_damage": round(safe_get(player_data, 'xp', 0) / damage, 2) if damage > 0 else 0,
            "credits_per_damage": round(safe_get(player_data, 'credits', 0) / damage, 2) if damage > 0 else 0,
        }

    def extract_enemy_damage_details(details: dict) -> dict:
        """Извлекает детали урона по противникам"""
        if not details or not isinstance(details, dict):
            return {}

        enemy_damage = {}
        for enemy_key, damage_data in details.items():
            if not isinstance(damage_data, dict):
                continue

            damage_dealt = safe_get(damage_data, 'damageDealt', 0)
            if damage_dealt > 0:
                # Извлекаем ID противника из строки вида "(46118422, 0)"
                if isinstance(enemy_key, str) and enemy_key.startswith('('):
                    try:
                        # Извлекаем первое число из строки "(46118422, 0)"
                        enemy_id = enemy_key.strip('()').split(',')[0].strip()
                        enemy_damage[enemy_id] = damage_dealt
                    except (ValueError, IndexError):
                        continue
                else:
                    enemy_damage[str(enemy_key)] = damage_dealt
        return enemy_damage

    def determine_battle_result(winner_team: int, player_team: int) -> str:
        """Определяет результат боя для игрока"""
        if winner_team == player_team:
            return "victory"
        elif winner_team == 0:
            return "draw"
        else:
            return "defeat"

    def find_player_data(personal_section: dict, target_player_id: int) -> Optional[dict]:
        """Находит данные игрока в секции personal"""
        if not personal_section:
            return None

        # Ищем данные по accountDBID в каждом разделе personal
        for key, data in personal_section.items():
            if key == 'avatar':  # пропускаем секцию avatar
                continue

            if isinstance(data, dict):
                account_id = safe_get(data, 'accountDBID')
                if account_id == target_player_id:
                    return data

        return None

    # Находим ID игрока
    player_id = safe_get(data, 'playerID')
    if not player_id:
        raise ValueError("Не найден playerID в данных реплея")

    personal_section = safe_get(data, 'personal', {})
    if not personal_section:
        raise ValueError("Не найдена секция 'personal' в данных реплея")

    player_data = find_player_data(personal_section, player_id)
    if not player_data:
        raise ValueError(f"Не найдены персональные данные для игрока {player_id}")

    # Получаем дополнительные данные
    common_data = safe_get(data, 'common', {})
    vehicles_data = safe_get(data, 'vehicles', {})
    players_data = safe_get(data, 'players', {})

    # Вычисляем производные значения
    shots = safe_get(player_data, 'shots', 0)
    direct_hits = safe_get(player_data, 'directHits', 0)
    hit_rate = calculate_hit_rate(direct_hits, shots)
    total_assist = calculate_total_assist(player_data)

    # Извлекаем детали по противникам
    details = safe_get(player_data, 'details', {})
    enemy_damage_details = extract_enemy_damage_details(details)
    detailed_enemy_stats = extract_detailed_enemy_stats(details, vehicles_data)
    armor_stats = extract_ricochets_and_bounces(player_data, details)
    battle_performance = calculate_battle_performance(player_data)

    # Определяем результат боя
    winner_team = safe_get(common_data, 'winnerTeam', 0)
    player_team = safe_get(player_data, 'team', 0)
    battle_result = determine_battle_result(winner_team, player_team)

    return {
        # Общая информация о бою
        "battle_result": battle_result,
        "winner_team": winner_team,
        "finish_reason": safe_get(common_data, 'finishReason'),
        "map_name": safe_get(data, 'mapName'),
        "map_display_name": safe_get(data, 'mapDisplayName'),
        "battle_type": safe_get(data, 'battleType'),
        "gameplay_id": safe_get(data, 'gameplayID'),
        "battle_date": safe_get(data, 'dateTime'),
        "duration": safe_get(common_data, 'duration'),
        "arena_type_id": safe_get(common_data, 'arenaTypeID'),
        "bonus_type": safe_get(common_data, 'bonusType'),

        # Команды и здоровье
        "team_health": safe_get(common_data, 'teamHealth', {}),
        "player_team": player_team,

        # Информация о игроке и технике
        "player_id": player_id,
        "player_name": safe_get(data, 'playerName'),
        "player_vehicle": safe_get(data, 'playerVehicle'),
        "type_comp_descr": safe_get(player_data, 'typeCompDescr'),
        "survival_status": safe_get(player_data, 'deathReason'),
        "life_time": safe_get(player_data, 'lifeTime'),
        "killer_id": safe_get(player_data, 'killerID', 0),

        # Финансовые показатели (детальные)
        "credits": safe_get(player_data, 'credits', 0),
        "original_credits": safe_get(player_data, 'originalCredits', 0),
        "xp": safe_get(player_data, 'xp', 0),
        "original_xp": safe_get(player_data, 'originalXP', 0),
        "free_xp": safe_get(player_data, 'freeXP', 0),
        "crystal": safe_get(player_data, 'crystal', 0),
        "auto_repair_cost": safe_get(player_data, 'autoRepairCost', 0),
        "auto_load_cost": safe_get(player_data, 'autoLoadCost', [0, 0]),

        # Премиум факторы
        "premium_credits_factor": safe_get(player_data, 'premiumCreditsFactor100', 0),
        "premium_xp_factor": safe_get(player_data, 'premiumXPFactor100', 0),
        "is_premium": safe_get(player_data, 'isPremium', False),

        # Боевая статистика (основная)
        "damage_dealt": safe_get(player_data, 'damageDealt', 0),
        "kills": safe_get(player_data, 'kills', 0),
        "shots": shots,
        "direct_hits": direct_hits,
        "piercings": safe_get(player_data, 'piercings', 0),
        "hit_rate": hit_rate,
        "explosion_hits": safe_get(player_data, 'explosionHits', 0),

        # Ассисты (детальные)
        "damage_assisted_radio": safe_get(player_data, 'damageAssistedRadio', 0),
        "damage_assisted_track": safe_get(player_data, 'damageAssistedTrack', 0),
        "damage_assisted_stun": safe_get(player_data, 'damageAssistedStun', 0),
        "damage_assisted_smoke": safe_get(player_data, 'damageAssistedSmoke', 0),
        "damage_assisted_inspire": safe_get(player_data, 'damageAssistedInspire', 0),
        "total_assist": total_assist,

        # Защита (детальная)
        "damage_blocked_by_armor": safe_get(player_data, 'damageBlockedByArmor', 0),
        "damage_received": safe_get(player_data, 'damageReceived', 0),
        "potential_damage_received": safe_get(player_data, 'potentialDamageReceived', 0),
        "no_damage_hits_received": safe_get(player_data, 'noDamageDirectHitsReceived', 0),
        "damage_from_invisibles": safe_get(player_data, 'damageReceivedFromInvisibles', 0),

        # Статистика брони (из armor_stats)
        "ricochets_received": armor_stats["ricochets"],
        "bounces_received": armor_stats["bounces"],
        "total_blocked_damage": armor_stats["blocked_damage"],
        "armor_effectiveness": armor_stats["total_armor_effectiveness"],

        # Разведка
        "spotted": safe_get(player_data, 'spotted', 0),

        # Достижения и награды
        "mark_of_mastery": safe_get(player_data, 'markOfMastery'),
        "prev_mark_of_mastery": safe_get(player_data, 'prevMarkOfMastery', 0),
        "achievements": safe_get(player_data, 'achievements', []),
        "is_first_blood": safe_get(player_data, 'isFirstBlood', False),
        "achievement_xp": safe_get(player_data, 'achievementXP', 0),
        "achievement_credits": safe_get(player_data, 'achievementCredits', 0),

        # Дополнительная статистика
        "mileage": safe_get(player_data, 'mileage', 0),
        "max_health": safe_get(player_data, 'maxHealth', 0),
        "health_remaining": safe_get(player_data, 'health', 0),
        "capture_points": safe_get(player_data, 'capturePoints', 0),
        "dropped_capture_points": safe_get(player_data, 'droppedCapturePoints', 0),
        "damaged_vehicles": safe_get(player_data, 'damaged', 0),
        "team_kills": safe_get(player_data, 'tkills', 0),
        "direct_team_hits": safe_get(player_data, 'directTeamHits', 0),

        # Показатели эффективности
        "battle_performance": battle_performance,
        "percent_team_damage": safe_get(player_data, 'percentFromTotalTeamDamage', 0),
        "percent_second_best_damage": safe_get(player_data, 'percentFromSecondBestDamage', 0),

        # Урон по противникам (простой формат)
        "enemy_damage_details": enemy_damage_details,

        # Детальная статистика по противникам
        "detailed_enemy_stats": detailed_enemy_stats,

        # Метаданные
        "client_version": safe_get(data, 'clientVersionFromXml'),
        "server_name": safe_get(data, 'serverName'),
        "region_code": safe_get(data, 'regionCode'),
        "arena_unique_id": safe_get(data, 'arenaUniqueID'),

        # Информация о ботах (если есть)
        "bots": safe_get(common_data, 'bots', {}),

        # Дополнительная статистика активности
        "destructibles_hits": safe_get(player_data, 'destructiblesHits', 0),
        "destructibles_destroyed": safe_get(player_data, 'destructiblesNumDestroyed', 0),
        "equipment_damage": safe_get(player_data, 'equipmentDamageDealt', 0),
        "piercings_received": safe_get(player_data, 'piercingsReceived', 0),
        "direct_hits_received": safe_get(player_data, 'directHitsReceived', 0),
        "explosion_hits_received": safe_get(player_data, 'explosionHitsReceived', 0),

        # Прочие флаги и счетчики
        "rollouts_count": safe_get(player_data, 'rolloutsCount', 0),
        "stun_duration": safe_get(player_data, 'stunDuration', 0.0),
        "stunned_count": safe_get(player_data, 'stunned', 0),
        "flag_capture": safe_get(player_data, 'flagCapture', 0),
        "flag_actions": safe_get(player_data, 'flagActions', [0, 0, 0, 0]),
    }


def load_and_extract_replay(file_path: str) -> dict:
    """
    Загружает JSON из файла и извлекает данные реплея.

    Args:
        file_path: Путь к JSON файлу

    Returns:
        dict: Извлеченные данные реплея
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        return extract_replay_data(json_data)
    except FileNotFoundError:
        raise FileNotFoundError(f"Файл {file_path} не найден")
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Ошибка парсинга JSON из файла {file_path}: {str(e)}", "", 0)


# Пример использования:
if __name__ == "__main__":
    # Для загрузки из файла
    replay_data = load_and_extract_replay('sample_json.json')

    # Для работы с JSON строкой
    # replay_data = extract_replay_data(json_string)
    # print(replay_data)