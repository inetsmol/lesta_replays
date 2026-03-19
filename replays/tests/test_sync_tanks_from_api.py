from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase

from replays.models import Tank


def make_response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class SyncTanksFromAPITests(TestCase):
    @patch("replays.management.commands.sync_tanks_from_api.requests.get")
    def test_sync_updates_existing_tank_and_fetches_all_pages(self, mock_get):
        Tank.objects.create(
            vehicleId="R01_IS",
            name="Неизвестный танк (R01_IS)",
            level=1,
            type="unknown",
            nation=None,
        )

        mock_get.side_effect = [
            make_response(
                {
                    "status": "ok",
                    "meta": {"count": 1, "page_total": 2, "total": 2, "limit": 100, "page": 1},
                    "data": {
                        "1001": {
                            "tag": "R01_IS",
                            "name": "ИС",
                            "short_name": "ИС",
                            "tier": 7,
                            "type": "heavyTank",
                            "nation": "ussr",
                        }
                    },
                }
            ),
            make_response(
                {
                    "status": "ok",
                    "meta": {"count": 1, "page_total": 2, "total": 2, "limit": 100, "page": 2},
                    "data": {
                        "1002": {
                            "tag": "G04_PzVI_Tiger_I",
                            "name": "Tiger I",
                            "short_name": "Tiger I",
                            "tier": 7,
                            "type": "heavyTank",
                            "nation": "germany",
                        }
                    },
                }
            ),
        ]

        stdout = StringIO()
        call_command(
            "sync_tanks_from_api",
            application_id="test-app-id",
            skip_images=True,
            stdout=stdout,
        )

        updated_tank = Tank.objects.get(vehicleId="R01_IS")
        self.assertEqual(updated_tank.name, "ИС")
        self.assertEqual(updated_tank.level, 7)
        self.assertEqual(updated_tank.type, "heavyTank")
        self.assertEqual(updated_tank.nation, "ussr")

        created_tank = Tank.objects.get(vehicleId="G04_PzVI_Tiger_I")
        self.assertEqual(created_tank.name, "Tiger I")
        self.assertEqual(created_tank.level, 7)
        self.assertEqual(created_tank.type, "heavyTank")
        self.assertEqual(created_tank.nation, "germany")

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_get.call_args_list[0].kwargs["params"]["page_no"], 1)
        self.assertEqual(mock_get.call_args_list[1].kwargs["params"]["page_no"], 2)
        self.assertIn("Создано: 1 | обновлено: 1 | без изменений: 0", stdout.getvalue())

    @patch("replays.management.commands.sync_tanks_from_api.requests.get")
    def test_dry_run_does_not_write_to_database(self, mock_get):
        mock_get.return_value = make_response(
            {
                "status": "ok",
                "meta": {"count": 1, "page_total": 1, "total": 1, "limit": 100, "page": 1},
                "data": {
                    "2001": {
                        "tag": "A01_T1_Cunningham",
                        "name": "T1 Cunningham",
                        "short_name": "T1 Cunningham",
                        "tier": 1,
                        "type": "lightTank",
                        "nation": "usa",
                    }
                },
            }
        )

        stdout = StringIO()
        call_command(
            "sync_tanks_from_api",
            application_id="test-app-id",
            dry_run=True,
            skip_images=True,
            stdout=stdout,
        )

        self.assertFalse(Tank.objects.filter(vehicleId="A01_T1_Cunningham").exists())
        self.assertIn("DRY-RUN", stdout.getvalue())

    @patch("replays.management.commands.sync_tanks_from_api.sync_tank_images_from_client")
    @patch("replays.management.commands.sync_tanks_from_api.requests.get")
    def test_sync_runs_client_image_step(self, mock_get, mock_sync_images):
        mock_get.return_value = make_response(
            {
                "status": "ok",
                "meta": {"count": 1, "page_total": 1, "total": 1, "limit": 100, "page": 1},
                "data": {
                    "3001": {
                        "tag": "A01_T1_Cunningham",
                        "name": "T1 Cunningham",
                        "short_name": "T1 Cunningham",
                        "tier": 1,
                        "type": "lightTank",
                        "nation": "usa",
                    }
                },
            }
        )

        stdout = StringIO()
        call_command(
            "sync_tanks_from_api",
            application_id="test-app-id",
            client_root="tmp/test-client",
            temp_root="tmp/test-client-sync",
            output_dir="tmp/test-static",
            webp_quality=77,
            clean=True,
            stdout=stdout,
        )

        mock_sync_images.assert_called_once()
        kwargs = mock_sync_images.call_args.kwargs
        self.assertEqual(kwargs["client_root"], Path("tmp/test-client").expanduser().resolve())
        self.assertEqual(kwargs["temp_root"], Path("tmp/test-client-sync").expanduser().resolve())
        self.assertEqual(kwargs["output_dir"], Path("tmp/test-static").expanduser().resolve())
        self.assertEqual(kwargs["webp_quality"], 77)
        self.assertTrue(kwargs["clean"])
        self.assertFalse(kwargs["dry_run"])
        self.assertIn("Шаг 2/2", stdout.getvalue())
