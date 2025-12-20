from django.test import TestCase
from replays.parser.parsers import extract_replay_data
from replays.parser.extractor import ExtractorV2
import json

class TestPlayerIDZero(TestCase):
    def setUp(self):
        self.payload = [
            {
                "playerID": 0,
                "playerName": "ApTa_KyIIIaeT",
                "playerVehicle": "ussr:R01_IS",
                "dateTime": "20.12.2025 11:18:10",
                "mapName": "map_name",
                "mapDisplayName": "Map Name",
                "gameplayID": "ctf",
                "battleType": 1
            },
            [
                {
                    "common": {
                        "winnerTeam": 1,
                        "finishReason": 1,
                        "duration": 360,
                        "bonusType": 1,
                    },
                    "personal": {
                        "12345": {
                            "accountDBID": 12345,
                            "xp": 1000,
                            "originalXP": 1000,
                            "credits": 50000,
                            "originalCredits": 50000,
                            "damageDealt": 2000,
                            "kills": 2,
                            "team": 1,
                            "markOfMastery": 3,
                            "details": {}
                        }
                    },
                    "players": {
                        "12345": {
                            "name": "ApTa_KyIIIaeT",
                            "realName": "ApTa_KyIIIaeT",
                            "team": 1,
                            "clanAbbrev": "TEST"
                        }
                    },
                    "vehicles": {
                        "12345": [
                            {
                                "typeCompDescr": 12345,
                                "accountDBID": 12345
                            }
                        ]
                    }
                },
                {}
            ]
        ]

    def test_extract_replay_data_with_player_id_zero(self):
        # parsers.py uses a slightly different structure (old one or combined)
        # but let's test the logic we modified in find_player_data
        
        # Mocking the data structure expected by extract_replay_data in parsers.py
        # Based on the code, it expects a dict with 'playerID', 'personal', etc.
        data = {
            "playerID": 0,
            "playerName": "ApTa_KyIIIaeT",
            "personal": {
                "12345": {
                    "accountDBID": 12345,
                    "xp": 1000,
                    "originalXP": 1000,
                    "credits": 50000,
                    "originalCredits": 50000,
                    "damageDealt": 2000,
                    "kills": 2,
                    "team": 1,
                    "markOfMastery": 3,
                    "details": {}
                }
            },
            "common": {"winnerTeam": 1},
            "vehicles": {},
            "players": {},
            "mapName": "map_name",
            "mapDisplayName": "Map Name",
            "battleType": 1,
            "gameplayID": "ctf",
            "dateTime": "20.12.2025 11:18:10"
        }
        
        result = extract_replay_data(data)
        # Now player_id should be updated to 12345
        self.assertEqual(result["player_id"], 12345)
        self.assertEqual(result["damage_dealt"], 2000)
        self.assertEqual(result["xp"], 1000)

    def test_extractor_v2_with_player_id_zero(self):
        fields = ExtractorV2.extract_replay_fields_v2(self.payload, "test.mtreplay")
        # Now player_id should be updated to 12345
        self.assertEqual(fields["player_id"], 12345)
        self.assertEqual(fields["damage"], 2000)
        self.assertEqual(fields["xp"], 1000)
        self.assertEqual(fields["kills"], 2)

    def test_get_replay_owner_from_payload_with_player_id_zero(self):
        owner = ExtractorV2.get_replay_owner_from_payload(self.payload)
        self.assertEqual(owner["accountDBID"], 12345)
        self.assertEqual(owner["real_name"], "ApTa_KyIIIaeT")

    def test_replay_cache_with_player_id_zero(self):
        from replays.parser.replay_cache import ReplayDataCache
        
        # Create a payload structure similar to what ReplayDataCache expects
        # payload = [metadata, battle_results]
        metadata = {"playerID": 0}
        battle_results = [
            {
                "personal": {
                    "12345": {
                        "accountDBID": 12345,
                        "xp": 1000,
                        "credits": 50000,
                        "team": 1
                    }
                },
                "common": {},
                "players": {},
                "vehicles": {},
                "avatars": {}
            },
            {}, # extended info
            {}  # frags
        ]
        payload = [metadata, battle_results]
        
        cache = ReplayDataCache(payload)
        
        # Verify player_id is correctly resolved to 12345
        self.assertEqual(cache.player_id, 12345)
        
        # Verify personal data is correctly found
        self.assertIsNotNone(cache.personal)
        self.assertEqual(cache.personal.get("accountDBID"), 12345)
