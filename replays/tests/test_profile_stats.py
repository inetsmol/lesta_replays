import json
import os
import struct
import tempfile
import zipfile
from datetime import datetime
from io import BytesIO
import xml.etree.ElementTree as ET

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from replays.models import ReplayStatBattle, ReplayStatPlayer, SubscriptionPlan
from replays.parser.parser import MAGIC
from replays.services import SubscriptionService

User = get_user_model()


def build_mtreplay_bytes(
        *,
        arena_unique_id: int = 987654321,
        winner_team: int = 1,
        player_team: int = 1,
        player_id: int = 12345,
        player_name: str = "TestPlayer",
        battle_datetime: str = "22.02.2026 12:00:00",
        include_ally: bool = True,
        team_as_string: bool = False,
        include_enemy: bool = False,
        ally_in_personal: bool = True,
        include_vehicle_stats: bool = True,
        include_avatar_personal: bool = False,
) -> bytes:
    ally_id = 54321
    ally_name = "AllyPlayer"
    enemy_id = 65432
    enemy_name = "EnemyPlayer"
    player_team_value = str(player_team) if team_as_string else player_team
    enemy_team = 2 if player_team == 1 else 1
    enemy_team_value = str(enemy_team) if team_as_string else enemy_team
    first_block = {
        "playerID": player_id,
        "playerName": player_name,
        "playerVehicle": "ussr:R01_IS",
        "dateTime": battle_datetime,
        "mapName": "test_map",
        "mapDisplayName": "Тестовая карта",
        "battleType": 1,
        "gameplayID": "ctf",
        "arenaUniqueID": arena_unique_id,
    }
    second_block = [
        {
            "common": {
                "winnerTeam": winner_team,
                "finishReason": 1,
                "duration": 360,
                "arenaUniqueID": arena_unique_id,
            },
            "vehicles": {},
            "personal": {
                str(player_id): {
                    "accountDBID": player_id,
                    "team": player_team_value,
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
                    "team": player_team_value,
                }
            },
        },
        {
            "1": {
                "name": player_name,
                "fakeName": player_name,
                "vehicleType": "ussr:R01_IS",
                "team": player_team_value,
            }
        },
    ]

    if include_ally:
        if ally_in_personal:
            second_block[0]["personal"][str(ally_id)] = {
                "accountDBID": ally_id,
                "team": player_team_value,
                "originalXP": 800,
                "originalCredits": 32000,
                "kills": 1,
                "damageDealt": 1500,
                "damageBlockedByArmor": 200,
                "damageAssistedTrack": 100,
                "damageAssistedRadio": 50,
                "deathReason": 0,
            }
        second_block[0]["players"][str(ally_id)] = {
            "name": ally_name,
            "realName": ally_name,
            "clanAbbrev": "ALLY",
            "team": player_team_value,
        }
        second_block[1]["2"] = {
            "name": ally_name,
            "fakeName": ally_name,
            "vehicleType": "usa:A01_T1_Cunningham",
            "team": player_team_value,
        }

    if include_enemy:
        second_block[0]["personal"][str(enemy_id)] = {
            "accountDBID": enemy_id,
            "team": enemy_team_value,
            "originalXP": 600,
            "originalCredits": 21000,
            "kills": 0,
            "damageDealt": 700,
            "damageBlockedByArmor": 100,
            "damageAssistedTrack": 0,
            "damageAssistedRadio": 0,
            "deathReason": 0,
        }
        second_block[0]["players"][str(enemy_id)] = {
            "name": enemy_name,
            "realName": enemy_name,
            "clanAbbrev": "ENM",
            "team": enemy_team_value,
        }
        second_block[1]["3"] = {
            "name": enemy_name,
            "fakeName": enemy_name,
            "vehicleType": "germany:G02_Hummel",
            "team": enemy_team_value,
        }

    if include_vehicle_stats:
        second_block[0]["vehicles"]["1"] = [{
            "accountDBID": player_id,
            "team": player_team_value,
            "xp": 1200,
            "achievementXP": 0,
            "kills": 3,
            "damageDealt": 2400,
            "damageBlockedByArmor": 700,
            "damageAssistedTrack": 300,
            "damageAssistedRadio": 200,
        }]
        if include_ally:
            second_block[0]["vehicles"]["2"] = [{
                "accountDBID": ally_id,
                "team": player_team_value,
                "xp": 800,
                "achievementXP": 0,
                "kills": 1,
                "damageDealt": 1500,
                "damageBlockedByArmor": 200,
                "damageAssistedTrack": 100,
                "damageAssistedRadio": 50,
            }]
        if include_enemy:
            second_block[0]["vehicles"]["3"] = [{
                "accountDBID": enemy_id,
                "team": enemy_team_value,
                "xp": 600,
                "achievementXP": 0,
                "kills": 0,
                "damageDealt": 700,
                "damageBlockedByArmor": 100,
                "damageAssistedTrack": 0,
                "damageAssistedRadio": 0,
            }]

    if include_avatar_personal:
        # В реальных реплеях avatar-блок может быть в personal и содержать accountDBID владельца,
        # но не содержать боевых полей (damage/kills/assist/block).
        second_block[0]["personal"]["avatar"] = {
            "accountDBID": player_id,
            "xp": 9999,
            "credits": 777777,
        }

    first_json = json.dumps(first_block, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    second_json = json.dumps(second_block, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

    header = struct.pack("<III", MAGIC, 2, len(first_json))
    second_len = struct.pack("<I", len(second_json))
    return header + first_json + second_len + second_json


class ProfileStatsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="stats_user", password="test-pass-123")
        SubscriptionService.activate_subscription(self.user, SubscriptionPlan.PLAN_PRO, days=30, activated_by='admin')
        self.client.login(username="stats_user", password="test-pass-123")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.override_media = override_settings(MEDIA_ROOT=self.temp_dir.name)
        self.override_media.enable()

    def tearDown(self):
        self.override_media.disable()
        self.temp_dir.cleanup()

    def _create_battle(
            self,
            signature: str,
            battle_date: datetime,
            arena_unique_id: int | None = None,
            outcome: str = ReplayStatBattle.OUTCOME_WIN,
    ):
        return ReplayStatBattle.objects.create(
            user=self.user,
            battle_date=battle_date,
            map_name="test_map",
            map_display_name="Тестовая карта",
            outcome=outcome,
            arena_unique_id=arena_unique_id,
            battle_signature=signature,
        )

    def test_stats_upload_creates_entry_and_does_not_save_file(self):
        replay_bytes = build_mtreplay_bytes()
        upload = SimpleUploadedFile(
            "battle_1.mtreplay",
            replay_bytes,
            content_type="application/octet-stream",
        )

        response = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [upload]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["summary"]["created"], 1)
        self.assertEqual(body["summary"]["duplicates"], 0)
        self.assertEqual(body["summary"]["errors"], 0)

        self.assertEqual(ReplayStatBattle.objects.count(), 1)
        self.assertEqual(ReplayStatPlayer.objects.count(), 2)

        battle = ReplayStatBattle.objects.get(user=self.user)
        players = set(battle.players.values_list("player_name", flat=True))
        self.assertEqual(players, {"TestPlayer", "AllyPlayer"})

        owner_player = battle.players.get(player_name="TestPlayer")
        ally_player = battle.players.get(player_name="AllyPlayer")
        self.assertEqual(battle.outcome, ReplayStatBattle.OUTCOME_WIN)
        self.assertEqual(owner_player.damage, 2400)
        self.assertEqual(ally_player.damage, 1500)
        self.assertEqual(body["results"][0]["rows_created"], 2)
        self.assertEqual(os.listdir(self.temp_dir.name), [])

    def test_stats_upload_detects_duplicate(self):
        replay_bytes = build_mtreplay_bytes(arena_unique_id=222)

        response_1 = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [SimpleUploadedFile("battle_dup.mtreplay", replay_bytes)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response_1.status_code, 200)

        response_2 = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [SimpleUploadedFile("battle_dup_again.mtreplay", replay_bytes)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response_2.status_code, 200)
        body = response_2.json()
        self.assertEqual(body["summary"]["created"], 0)
        self.assertEqual(body["summary"]["duplicates"], 1)
        self.assertEqual(ReplayStatBattle.objects.count(), 1)
        self.assertEqual(ReplayStatPlayer.objects.count(), 2)
        self.assertEqual(body["results"][0]["rows_duplicates"], 2)

    def test_stats_upload_keeps_allies_when_team_is_string(self):
        replay_bytes = build_mtreplay_bytes(
            arena_unique_id=333,
            include_ally=True,
            include_enemy=True,
            team_as_string=True,
        )
        response = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [SimpleUploadedFile("battle_string_team.mtreplay", replay_bytes)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["summary"]["created"], 1)

        battle = ReplayStatBattle.objects.get(user=self.user, arena_unique_id=333)
        players = set(battle.players.values_list("player_name", flat=True))
        self.assertEqual(players, {"TestPlayer", "AllyPlayer"})

    def test_stats_upload_uses_vehicle_stats_when_allies_have_no_personal(self):
        replay_bytes = build_mtreplay_bytes(
            arena_unique_id=444,
            include_ally=True,
            ally_in_personal=False,
            include_vehicle_stats=True,
        )
        response = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [SimpleUploadedFile("battle_vehicle_fallback.mtreplay", replay_bytes)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["summary"]["created"], 1)

        battle = ReplayStatBattle.objects.get(user=self.user, arena_unique_id=444)
        ally = battle.players.get(player_name="AllyPlayer")
        self.assertEqual(ally.damage, 1500)
        self.assertEqual(ally.xp, 800)
        self.assertEqual(ally.kills, 1)
        self.assertEqual(ally.assist, 150)
        self.assertEqual(ally.block, 200)

    def test_stats_upload_duplicate_updates_zero_rows_when_new_stats_available(self):
        first_upload = build_mtreplay_bytes(
            arena_unique_id=555,
            include_ally=True,
            ally_in_personal=False,
            include_vehicle_stats=False,
        )
        second_upload = build_mtreplay_bytes(
            arena_unique_id=555,
            include_ally=True,
            ally_in_personal=False,
            include_vehicle_stats=True,
        )

        response_1 = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [SimpleUploadedFile("battle_zero_first.mtreplay", first_upload)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response_1.status_code, 200)

        battle = ReplayStatBattle.objects.get(user=self.user, arena_unique_id=555)
        ally_before = battle.players.get(player_name="AllyPlayer")
        self.assertEqual(ally_before.damage, 0)
        self.assertEqual(ally_before.xp, 0)

        response_2 = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [SimpleUploadedFile("battle_zero_fix.mtreplay", second_upload)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response_2.status_code, 200)
        body_2 = response_2.json()
        self.assertEqual(body_2["summary"]["created"], 0)
        self.assertEqual(body_2["summary"]["duplicates"], 1)

        ally_after = ReplayStatPlayer.objects.get(battle=battle, player_name="AllyPlayer")
        self.assertEqual(ally_after.damage, 1500)
        self.assertEqual(ally_after.xp, 800)
        self.assertEqual(ally_after.kills, 1)
        self.assertEqual(ally_after.assist, 150)
        self.assertEqual(ally_after.block, 200)

    def test_stats_upload_owner_stats_not_overridden_by_avatar_personal(self):
        replay_bytes = build_mtreplay_bytes(
            arena_unique_id=666,
            include_ally=True,
            include_vehicle_stats=True,
            include_avatar_personal=True,
        )
        response = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [SimpleUploadedFile("battle_owner_avatar.mtreplay", replay_bytes)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["summary"]["created"], 1)

        battle = ReplayStatBattle.objects.get(user=self.user, arena_unique_id=666)
        owner = battle.players.get(player_name="TestPlayer")
        self.assertEqual(owner.damage, 2400)
        self.assertEqual(owner.xp, 1200)
        self.assertEqual(owner.kills, 3)
        self.assertEqual(owner.assist, 500)
        self.assertEqual(owner.block, 700)

    def test_stats_upload_invalid_extension_returns_error(self):
        upload = SimpleUploadedFile("not_replay.txt", b"invalid data")
        response = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [upload]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["summary"]["errors"], 1)
        self.assertEqual(body["results"][0]["status"], "error")
        self.assertEqual(ReplayStatBattle.objects.count(), 0)
        self.assertEqual(ReplayStatPlayer.objects.count(), 0)

    def test_profile_stats_page_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("profile_stats"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_profile_stats_page_is_blurred_for_non_pro(self):
        free_user = User.objects.create_user(username="free_user_stats", password="test-pass-123")
        self.client.logout()
        self.client.login(username="free_user_stats", password="test-pass-123")

        response = self.client.get(reverse("profile_stats"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Раздел статистики доступен только для подписчиков")
        self.assertContains(response, "Оформить ПРО")

    def test_profile_stats_upload_forbidden_for_non_pro(self):
        free_user = User.objects.create_user(username="free_user_upload", password="test-pass-123")
        self.client.logout()
        self.client.login(username="free_user_upload", password="test-pass-123")

        replay_bytes = build_mtreplay_bytes(arena_unique_id=777)
        response = self.client.post(
            reverse("profile_stats_upload"),
            {"files": [SimpleUploadedFile("battle_non_pro.mtreplay", replay_bytes)]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIn("ПРО", body["error"])
        self.assertEqual(body["redirect_url"], reverse("subscription_info"))

    def test_profile_stats_export_redirects_for_non_pro(self):
        free_user = User.objects.create_user(username="free_user_export", password="test-pass-123")
        self.client.logout()
        self.client.login(username="free_user_export", password="test-pass-123")

        response = self.client.get(reverse("profile_stats_export"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("subscription_info"))

    def test_profile_stats_page_contains_allies_button(self):
        response = self.client.get(
            reverse("profile_stats"),
            {"date_from": "2026-02-20", "date_to": "2026-02-22", "sort": "battle_date"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "статистика союзников")
        self.assertEqual(
            response.context["allies_stats_url"],
            f'{reverse("profile_stats_allies")}?date_from=2026-02-20&date_to=2026-02-22',
        )

    def test_profile_stats_allies_redirects_for_non_pro(self):
        free_user = User.objects.create_user(username="free_user_allies", password="test-pass-123")
        self.client.logout()
        self.client.login(username="free_user_allies", password="test-pass-123")

        response = self.client.get(reverse("profile_stats_allies"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("subscription_info"))

    def test_profile_stats_page_shows_replay_rows_not_player_rows(self):
        battle = self._create_battle(
            signature="row-sig-1",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 12, 0, 0), timezone.get_current_timezone()),
            arena_unique_id=111,
        )
        ReplayStatPlayer.objects.create(
            battle=battle,
            player_account_id=1,
            player_name="Игрок 1",
            damage=2000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )
        ReplayStatPlayer.objects.create(
            battle=battle,
            player_account_id=2,
            player_name="Игрок 2",
            damage=1000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )

        response = self.client.get(reverse("profile_stats"))
        self.assertEqual(response.status_code, 200)
        items = list(response.context["items"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["players_count"], 2)
        self.assertEqual(items[0]["total_damage"], 3000)

    @staticmethod
    def _read_first_sheet_values(xlsx_bytes: bytes):
        ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

        def col_to_index(cell_ref: str) -> int:
            letters = ''.join(ch for ch in cell_ref if ch.isalpha())
            result = 0
            for ch in letters:
                result = result * 26 + (ord(ch) - 64)
            return result

        with zipfile.ZipFile(BytesIO(xlsx_bytes)) as archive:
            sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))

        rows = []
        for row in sheet.findall('.//a:sheetData/a:row', ns):
            values_map = {}
            max_col = 0
            for cell in row.findall('a:c', ns):
                ref = cell.attrib.get('r', '')
                col_idx = col_to_index(ref)
                max_col = max(max_col, col_idx)
                cell_type = cell.attrib.get('t')
                if cell_type == 'inlineStr':
                    text_node = cell.find('a:is/a:t', ns)
                    value = text_node.text if text_node is not None else ''
                else:
                    v_node = cell.find('a:v', ns)
                    value = v_node.text if v_node is not None else ''
                values_map[col_idx] = value
            values = [values_map.get(idx, '') for idx in range(1, max_col + 1)]
            rows.append(values)
        return rows

    @staticmethod
    def _read_first_row_styles(xlsx_bytes: bytes):
        ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

        def col_to_index(cell_ref: str) -> int:
            letters = ''.join(ch for ch in cell_ref if ch.isalpha())
            result = 0
            for ch in letters:
                result = result * 26 + (ord(ch) - 64)
            return result

        with zipfile.ZipFile(BytesIO(xlsx_bytes)) as archive:
            sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            styles_xml = archive.read('xl/styles.xml').decode('utf-8')

        first_row = sheet.find('.//a:sheetData/a:row', ns)
        style_map = {}
        if first_row is not None:
            for cell in first_row.findall('a:c', ns):
                ref = cell.attrib.get('r', '')
                style_map[col_to_index(ref)] = int(cell.attrib.get('s', '0'))

        return style_map, styles_xml

    def test_profile_stats_export_returns_xlsx_matrix(self):
        tz = timezone.get_current_timezone()
        battle_1 = self._create_battle(
            signature="exp-sig-1",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 0, 0), tz),
        )
        battle_2 = self._create_battle(
            signature="exp-sig-2",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 10, 0), tz),
        )

        ReplayStatPlayer.objects.create(
            battle=battle_1,
            player_account_id=11,
            player_name="Ник 1",
            damage=2000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )
        ReplayStatPlayer.objects.create(
            battle=battle_2,
            player_account_id=11,
            player_name="Ник 1",
            damage=3000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )
        ReplayStatPlayer.objects.create(
            battle=battle_1,
            player_account_id=22,
            player_name="Ник 2",
            damage=1000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )

        response = self.client.get(reverse("profile_stats_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment; filename="replay_stats_', response['Content-Disposition'])

        rows = self._read_first_sheet_values(response.content)
        self.assertEqual(
            rows[0],
            ['', '22.02.2026 10:00\nТестовая карта\nПобеда', '22.02.2026 10:10\nТестовая карта\nПобеда', 'Средний урон'],
        )
        self.assertEqual(rows[1], ['Ник 1', '2000', '3000', '2500'])
        self.assertEqual(rows[2], ['Ник 2', '1000', '', '1000'])
        self.assertEqual(rows[3], ['Итог: побед 2 из 2 боев'])

    def test_profile_stats_export_period_filter(self):
        tz = timezone.get_current_timezone()
        battle_1 = self._create_battle(
            signature="period-sig-1",
            battle_date=timezone.make_aware(datetime(2026, 2, 21, 10, 0, 0), tz),
        )
        battle_2 = self._create_battle(
            signature="period-sig-2",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 0, 0), tz),
        )

        ReplayStatPlayer.objects.create(
            battle=battle_1,
            player_account_id=1,
            player_name="Ник 1",
            damage=1000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )
        ReplayStatPlayer.objects.create(
            battle=battle_2,
            player_account_id=1,
            player_name="Ник 1",
            damage=3000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )

        response = self.client.get(
            reverse("profile_stats_export"),
            {"date_from": "2026-02-22", "date_to": "2026-02-22"},
        )
        self.assertEqual(response.status_code, 200)
        rows = self._read_first_sheet_values(response.content)
        self.assertEqual(rows[0], ['', '22.02.2026 10:00\nТестовая карта\nПобеда', 'Средний урон'])
        self.assertEqual(rows[1], ['Ник 1', '3000', '3000'])
        self.assertEqual(rows[2], ['Итог: побед 1 из 1 боев'])

    def test_profile_stats_allies_page_returns_matrix(self):
        tz = timezone.get_current_timezone()
        battle_1 = self._create_battle(
            signature="allies-sig-1",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 0, 0), tz),
        )
        battle_2 = self._create_battle(
            signature="allies-sig-2",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 10, 0), tz),
        )

        ReplayStatPlayer.objects.create(
            battle=battle_1,
            player_account_id=11,
            player_name="Ник 1",
            damage=2000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )
        ReplayStatPlayer.objects.create(
            battle=battle_2,
            player_account_id=11,
            player_name="Ник 1",
            damage=3000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )
        ReplayStatPlayer.objects.create(
            battle=battle_1,
            player_account_id=22,
            player_name="Ник 2",
            damage=1000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )

        response = self.client.get(reverse("profile_stats_allies"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary_label"], "Итог: побед 2 из 2 боев")
        self.assertEqual(
            response.context["data_rows"][0],
            ["Ник 1", 2000, 3000, 2500],
        )
        self.assertEqual(
            response.context["data_rows"][1],
            ["Ник 2", 1000, "", 1000],
        )
        self.assertEqual(
            response.context["header_cells"][1]["title"],
            "22.02.2026 10:00\nТестовая карта\nПобеда",
        )

    def test_profile_stats_export_selected_battles_only(self):
        tz = timezone.get_current_timezone()
        battle_1 = self._create_battle(
            signature="select-sig-1",
            battle_date=timezone.make_aware(datetime(2026, 2, 21, 9, 0, 0), tz),
        )
        battle_2 = self._create_battle(
            signature="select-sig-2",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 0, 0), tz),
        )

        ReplayStatPlayer.objects.create(
            battle=battle_1,
            player_account_id=1,
            player_name="Ник 1",
            damage=1000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )
        ReplayStatPlayer.objects.create(
            battle=battle_2,
            player_account_id=1,
            player_name="Ник 1",
            damage=3000,
            xp=1,
            kills=1,
            assist=1,
            block=1,
        )

        response = self.client.get(
            reverse("profile_stats_export"),
            {"battle_signature": ["select-sig-2"]},
        )
        self.assertEqual(response.status_code, 200)
        rows = self._read_first_sheet_values(response.content)
        self.assertEqual(rows[0], ['', '22.02.2026 10:00\nТестовая карта\nПобеда', 'Средний урон'])
        self.assertEqual(rows[1], ['Ник 1', '3000', '3000'])
        self.assertEqual(rows[2], ['Итог: побед 1 из 1 боев'])

    def test_profile_stats_export_header_colors_by_outcome(self):
        tz = timezone.get_current_timezone()
        battle_win = self._create_battle(
            signature="color-win",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 0, 0), tz),
            outcome=ReplayStatBattle.OUTCOME_WIN,
        )
        battle_loss = self._create_battle(
            signature="color-loss",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 10, 0), tz),
            outcome=ReplayStatBattle.OUTCOME_LOSS,
        )
        battle_draw = self._create_battle(
            signature="color-draw",
            battle_date=timezone.make_aware(datetime(2026, 2, 22, 10, 20, 0), tz),
            outcome=ReplayStatBattle.OUTCOME_DRAW,
        )

        for battle in (battle_win, battle_loss, battle_draw):
            ReplayStatPlayer.objects.create(
                battle=battle,
                player_account_id=1,
                player_name="Ник 1",
                damage=1000,
                xp=1,
                kills=1,
                assist=1,
                block=1,
            )

        response = self.client.get(reverse("profile_stats_export"))
        self.assertEqual(response.status_code, 200)

        first_row_styles, styles_xml = self._read_first_row_styles(response.content)
        self.assertNotIn(1, first_row_styles)
        self.assertEqual(first_row_styles[2], 2)  # Победа -> зеленый
        self.assertEqual(first_row_styles[3], 3)  # Поражение -> красный
        self.assertEqual(first_row_styles[4], 4)  # Ничья -> желтый
        self.assertEqual(first_row_styles[5], 1)

        self.assertIn('rgb="FFC6EFCE"', styles_xml)  # light green
        self.assertIn('rgb="FFFFC7CE"', styles_xml)  # light red
        self.assertIn('rgb="FFFFEB9C"', styles_xml)  # light yellow
