import json
import struct
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from replays.models import Replay
from replays.parser.parser import MAGIC
from replays.services import ReplayProcessingService


def build_mtreplay_bytes(*, owner_personal_overrides: dict | None = None) -> bytes:
    player_id = 12345
    player_name = "TestPlayer"
    first_block = {
        "playerID": player_id,
        "playerName": player_name,
        "playerVehicle": "ussr:R01_IS",
        "dateTime": "22.02.2026 12:00:00",
        "mapName": "test_map",
        "mapDisplayName": "Тестовая карта",
        "battleType": 1,
        "gameplayID": "ctf",
        "arenaUniqueID": 987654321,
    }
    second_block = [
        {
            "common": {
                "winnerTeam": 1,
                "finishReason": 1,
                "duration": 360,
                "arenaUniqueID": 987654321,
            },
            "vehicles": {
                "1": [{
                    "accountDBID": player_id,
                    "team": 1,
                    "xp": 1200,
                    "achievementXP": 0,
                    "kills": 3,
                    "damageDealt": 2400,
                    "damageBlockedByArmor": 700,
                    "damageAssistedTrack": 300,
                    "damageAssistedRadio": 200,
                }]
            },
            "personal": {
                str(player_id): {
                    "accountDBID": player_id,
                    "team": 1,
                    "originalXP": 1200,
                    "originalCredits": 50000,
                    "kills": 3,
                    "damageDealt": 2400,
                    "damageBlockedByArmor": 700,
                    "damageAssistedTrack": 300,
                    "damageAssistedRadio": 200,
                    "deathReason": -1,
                    "markOfMastery": 2,
                }
            },
            "players": {
                str(player_id): {
                    "name": player_name,
                    "realName": player_name,
                    "clanAbbrev": "TST",
                    "team": 1,
                }
            },
        },
        {
            "1": {
                "name": player_name,
                "fakeName": player_name,
                "vehicleType": "ussr:R01_IS",
                "team": 1,
            }
        },
    ]

    if owner_personal_overrides:
        second_block[0]["personal"][str(player_id)].update(owner_personal_overrides)

    first_json = json.dumps(first_block, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    second_json = json.dumps(second_block, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

    header = struct.pack("<III", MAGIC, 2, len(first_json))
    second_len = struct.pack("<I", len(second_json))
    return header + first_json + second_len + second_json


class ReplayUploadTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.override_media = override_settings(MEDIA_ROOT=self.temp_dir.name)
        self.override_media.enable()

    def tearDown(self):
        self.override_media.disable()
        self.temp_dir.cleanup()

    def test_normalize_payload_for_storage_keeps_regular_payload(self):
        payload = [
            {"playerID": 12345, "playerName": "TestPlayer"},
            [{"personal": {"12345": {"originalXP": 1200}}}],
        ]

        normalized = ReplayProcessingService._normalize_payload_for_storage(json.dumps(payload))

        self.assertEqual(normalized, payload)

    def test_process_replay_strips_null_chars_from_payload_before_save(self):
        replay_bytes = build_mtreplay_bytes(
            owner_personal_overrides={"equipCoinReplay": "\x01\x00abc"}
        )
        upload = SimpleUploadedFile(
            "null_payload.mtreplay",
            replay_bytes,
            content_type="application/octet-stream",
        )

        replay = ReplayProcessingService().process_replay(upload, description="test")

        self.assertEqual(Replay.objects.count(), 1)
        self.assertEqual(replay.file_name, "null_payload.mtreplay")
        self.assertTrue((Path(self.temp_dir.name) / "null_payload.mtreplay").exists())

        stored_value = replay.payload[1][0]["personal"]["12345"]["equipCoinReplay"]
        self.assertEqual(stored_value, "\x01abc")
        self.assertNotIn("\x00", stored_value)

