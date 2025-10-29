"""
Unit-тесты для ReplayDataCache.

Проверяет корректность работы кеширования данных реплея.
"""

from django.test import TestCase
import json
from replays.parser.replay_cache import ReplayDataCache


class TestReplayDataCache(TestCase):
    """Тесты для класса ReplayDataCache"""

    def setUp(self):
        """Создаёт тестовый payload перед каждым тестом"""
        self.sample_payload = [
            {
                "playerID": 12345,
                "playerName": "TestPlayer",
                "playerVehicle": "ussr:R01_IS",
                "gameplayID": "ctf",
                "arenaUniqueID": 123456789,
            },
            [
                {
                    "common": {
                        "winnerTeam": 1,
                        "finishReason": 1,
                        "duration": 360,
                        "arenaUniqueID": 123456789
                    },
                    "personal": {
                        "12345": {
                            "accountDBID": 12345,
                            "xp": 1000,
                            "credits": 50000,
                            "damageDealt": 2000,
                            "kills": 2,
                            "achievements": [521, 39],
                            "details": {
                                "(67890,0)": {
                                    "damageDealt": 500,
                                    "spotted": 1,
                                }
                            }
                        }
                    },
                    "players": {
                        "12345": {
                            "name": "TestPlayer",
                            "team": 1,
                            "clanAbbrev": "TEST"
                        },
                        "67890": {
                            "name": "Enemy",
                            "team": 2
                        }
                    },
                    "vehicles": {
                        "12345": [
                            {
                                "typeCompDescr": 12345,
                                "accountDBID": 12345
                            }
                        ],
                        "67890": [
                            {
                                "typeCompDescr": 67890,
                                "accountDBID": 67890
                            }
                        ]
                    }
                },
                {
                    "12345": {
                        "vehicleType": "ussr:R01_IS",
                        "team": 1
                    },
                    "67890": {
                        "vehicleType": "germany:G04_PzVI_Tiger_I",
                        "team": 2
                    }
                }
            ]
        ]

    def test_cache_initialization_with_dict(self):
        """Тест создания кеша из словаря"""
        cache = ReplayDataCache(self.sample_payload)

        self.assertIsNotNone(cache.first_block)
        self.assertIsNotNone(cache.second_block)
        self.assertIsInstance(cache.first_block, dict)
        self.assertIsInstance(cache.second_block, list)

    def test_cache_initialization_with_json_string(self):
        """Тест создания кеша из JSON-строки"""
        json_string = json.dumps(self.sample_payload)
        cache = ReplayDataCache(json_string)

        self.assertEqual(cache.player_id, 12345)
        self.assertEqual(cache.first_block["playerName"], "TestPlayer")

    def test_invalid_payload_raises_error(self):
        """Тест, что невалидный payload вызывает ошибку"""
        invalid_payload = {"invalid": "structure"}

        with self.assertRaises(ValueError):
            ReplayDataCache(invalid_payload)

    def test_player_id_property(self):
        """Тест получения ID игрока"""
        cache = ReplayDataCache(self.sample_payload)

        self.assertEqual(cache.player_id, 12345)
        # Проверяем кеширование
        self.assertIs(cache.player_id, cache.player_id)

    def test_player_team_property(self):
        """Тест получения команды игрока"""
        cache = ReplayDataCache(self.sample_payload)

        self.assertEqual(cache.player_team, 1)

    def test_common_property(self):
        """Тест получения общих данных боя"""
        cache = ReplayDataCache(self.sample_payload)
        common = cache.common

        self.assertIsInstance(common, dict)
        self.assertEqual(common["winnerTeam"], 1)
        self.assertEqual(common["finishReason"], 1)
        self.assertEqual(common["duration"], 360)

    def test_common_property_caching(self):
        """Тест, что common кешируется"""
        cache = ReplayDataCache(self.sample_payload)

        common1 = cache.common
        common2 = cache.common

        # Должны вернуться те же объекты (проверка идентичности, а не равенства)
        self.assertIs(common1, common2)

    def test_personal_property(self):
        """Тест получения персональных данных"""
        cache = ReplayDataCache(self.sample_payload)
        personal = cache.personal

        self.assertIsInstance(personal, dict)
        self.assertEqual(personal.get("accountDBID"), 12345)
        self.assertEqual(personal.get("xp"), 1000)
        self.assertEqual(personal.get("credits"), 50000)

    def test_personal_property_caching(self):
        """Тест, что personal кешируется"""
        cache = ReplayDataCache(self.sample_payload)

        personal1 = cache.personal
        personal2 = cache.personal

        self.assertIs(personal1, personal2)

    def test_players_property(self):
        """Тест получения данных всех игроков"""
        cache = ReplayDataCache(self.sample_payload)
        players = cache.players

        self.assertIsInstance(players, dict)
        self.assertEqual(len(players), 2)
        self.assertEqual(players["12345"]["name"], "TestPlayer")
        self.assertEqual(players["67890"]["name"], "Enemy")

    def test_players_property_caching(self):
        """Тест, что players кешируется"""
        cache = ReplayDataCache(self.sample_payload)

        players1 = cache.players
        players2 = cache.players

        self.assertIs(players1, players2)

    def test_vehicles_property(self):
        """Тест получения данных техники"""
        cache = ReplayDataCache(self.sample_payload)
        vehicles = cache.vehicles

        self.assertIsInstance(vehicles, dict)
        self.assertEqual(len(vehicles), 2)
        self.assertIn("12345", vehicles)
        self.assertIn("67890", vehicles)

    def test_avatars_property(self):
        """Тест получения данных аватаров"""
        cache = ReplayDataCache(self.sample_payload)
        avatars = cache.avatars

        self.assertIsInstance(avatars, dict)
        self.assertEqual(len(avatars), 2)
        self.assertEqual(avatars["12345"]["vehicleType"], "ussr:R01_IS")
        self.assertEqual(avatars["67890"]["vehicleType"], "germany:G04_PzVI_Tiger_I")

    def test_get_achievements(self):
        """Тест получения списка достижений"""
        cache = ReplayDataCache(self.sample_payload)
        achievements = cache.get_achievements()

        self.assertIsInstance(achievements, list)
        self.assertEqual(len(achievements), 2)
        self.assertIn(521, achievements)
        self.assertIn(39, achievements)

    def test_get_achievements_empty(self):
        """Тест получения достижений, когда их нет"""
        payload_no_achievements = self.sample_payload.copy()
        payload_no_achievements[1][0]["personal"]["12345"].pop("achievements")

        cache = ReplayDataCache(payload_no_achievements)
        achievements = cache.get_achievements()

        self.assertEqual(achievements, [])

    def test_multiple_cache_instances_independent(self):
        """Тест, что разные экземпляры кеша независимы"""
        cache1 = ReplayDataCache(self.sample_payload)

        # Создаём другой payload
        other_payload = self.sample_payload.copy()
        other_payload[0]["playerID"] = 99999
        cache2 = ReplayDataCache(other_payload)

        self.assertNotEqual(cache1.player_id, cache2.player_id)
        self.assertEqual(cache1.player_id, 12345)
        self.assertEqual(cache2.player_id, 99999)

    def test_lazy_loading(self):
        """Тест, что свойства загружаются лениво"""
        cache = ReplayDataCache(self.sample_payload)

        # До обращения свойства должны быть None
        self.assertIsNone(cache._personal)
        self.assertIsNone(cache._common)
        self.assertIsNone(cache._players)

        # После обращения должны быть загружены
        _ = cache.personal
        self.assertIsNotNone(cache._personal)

        _ = cache.common
        self.assertIsNotNone(cache._common)

    def test_complex_personal_data_access(self):
        """Тест доступа к вложенным данным в personal"""
        cache = ReplayDataCache(self.sample_payload)
        personal = cache.personal

        # Проверяем доступ к details
        self.assertIn("details", personal)
        details = personal["details"]
        self.assertIsInstance(details, dict)

        # Проверяем конкретную цель
        target_key = "(67890,0)"
        self.assertIn(target_key, details)
        self.assertEqual(details[target_key]["damageDealt"], 500)
        self.assertEqual(details[target_key]["spotted"], 1)
