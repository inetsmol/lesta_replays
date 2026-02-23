import datetime as dt

from django.test import SimpleTestCase
from django.utils import timezone

from replays.parser.extractor import ExtractorV2, ParserUtils


class BattleDatetimeParsingTests(SimpleTestCase):
    def test_parse_prefers_arena_create_time(self):
        default_tz = timezone.get_default_timezone()
        expected_local = dt.datetime(2026, 2, 21, 19, 15, 26, tzinfo=default_tz)
        arena_ts = int(expected_local.astimezone(dt.timezone.utc).timestamp())

        parsed = ParserUtils._parse_battle_datetime(
            "21.02.2026 23:59:59",
            arena_create_time=arena_ts,
        )

        self.assertEqual(parsed, expected_local)

    def test_parse_supports_millisecond_arena_timestamp(self):
        default_tz = timezone.get_default_timezone()
        expected_local = dt.datetime(2026, 2, 21, 19, 15, 26, tzinfo=default_tz)
        arena_ts_ms = int(expected_local.astimezone(dt.timezone.utc).timestamp() * 1000)

        parsed = ParserUtils._parse_battle_datetime(
            "21.02.2026 23:59:59",
            arena_create_time=arena_ts_ms,
        )

        self.assertEqual(parsed, expected_local)

    def test_parse_falls_back_to_datetime_string(self):
        parsed = ParserUtils._parse_battle_datetime("22.02.2026 12:00:00", arena_create_time=None)
        expected = timezone.make_aware(
            dt.datetime(2026, 2, 22, 12, 0, 0),
            timezone.get_default_timezone(),
        )
        self.assertEqual(parsed, expected)

    def test_extractor_uses_arena_create_time_for_battle_date(self):
        default_tz = timezone.get_default_timezone()
        expected_local = dt.datetime(2026, 2, 21, 19, 15, 26, tzinfo=default_tz)
        arena_ts = int(expected_local.astimezone(dt.timezone.utc).timestamp())

        payload = [
            {
                "playerID": 12345,
                "playerName": "TestPlayer",
                "playerVehicle": "ussr:R01_IS",
                "dateTime": "21.02.2026 23:59:59",
                "mapName": "test_map",
                "mapDisplayName": "Test Map",
                "gameplayID": "ctf",
                "battleType": 1,
            },
            [
                {
                    "common": {
                        "arenaCreateTime": arena_ts,
                        "duration": 360,
                    },
                    "personal": {
                        "12345": {
                            "accountDBID": 12345,
                            "kills": 1,
                            "damageDealt": 1000,
                            "originalXP": 500,
                            "originalCredits": 20000,
                            "markOfMastery": 2,
                            "deathReason": -1,
                        }
                    },
                    "players": {
                        "12345": {
                            "name": "TestPlayer",
                            "realName": "TestPlayer",
                            "team": 1,
                        }
                    },
                    "vehicles": {},
                },
                {},
            ],
        ]

        fields = ExtractorV2.extract_replay_fields_v2(payload, "battle.mtreplay")
        self.assertEqual(fields["battle_date"], expected_local)
