# replays/management/commands/populate_battle_fields.py

import json
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q
from replays.models import Replay
from replays.parser.extractor import ExtractorV2


class Command(BaseCommand):
    help = "Заполняет battle поля из payload (логика как в миграции)"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        force = options["force"]

        if force:
            queryset = Replay.objects.all()
        else:
            queryset = Replay.objects.filter(
                Q(battle_duration__isnull=True)
                | Q(is_alive__isnull=True)
                | Q(is_platoon__isnull=True)
            )

        queryset = queryset.order_by("pk")

        if limit:
            queryset = queryset[:limit]

        total = queryset.count()
        self.stdout.write(f"Найдено реплеев: {total}")

        replay_ids = list(queryset.values_list("pk", flat=True))

        updated_count = 0
        skipped_count = 0
        error_count = 0

        for offset in range(0, len(replay_ids), batch_size):
            batch_ids = replay_ids[offset:offset + batch_size]
            batch = Replay.objects.filter(pk__in=batch_ids)

            to_update = []

            for replay in batch:
                try:
                    payload: Any = replay.payload
                    if not payload:
                        skipped_count += 1
                        continue

                    # Если строка — парсим
                    if isinstance(payload, str):
                        payload = json.loads(payload)

                    if not isinstance(payload, (list, tuple)) or len(payload) < 2:
                        skipped_count += 1
                        continue

                    metadata = payload[0] if isinstance(payload[0], dict) else {}
                    player_id = metadata.get("playerID")

                    second_block = payload[1]
                    if not isinstance(second_block, (list, tuple)) or not second_block:
                        skipped_count += 1
                        continue

                    first_result = second_block[0]
                    if not isinstance(first_result, dict):
                        skipped_count += 1
                        continue

                    # -----------------------------
                    # 1. battle_duration
                    # -----------------------------
                    common = first_result.get("common", {})
                    raw_duration = common.get("duration")

                    try:
                        duration = int(raw_duration) if raw_duration is not None else None
                    except (TypeError, ValueError):
                        duration = None

                    # -----------------------------
                    # 2. is_alive (логика миграции)
                    # -----------------------------
                    personal = first_result.get("personal", {})

                    personal_data = None

                    if isinstance(personal, dict):

                        if player_id == 0:
                            for key, value in personal.items():
                                if key == "avatar":
                                    continue
                                if isinstance(value, dict) and "accountDBID" in value:
                                    personal_data = value
                                    break

                        elif player_id is not None:
                            if (
                                personal.get("accountDBID") == player_id
                            ):
                                personal_data = personal
                            else:
                                for value in personal.values():
                                    if (
                                        isinstance(value, dict)
                                        and value.get("accountDBID") == player_id
                                    ):
                                        personal_data = value
                                        break

                    if personal_data:
                        try:
                            death_reason = int(
                                personal_data.get("deathReason", -1)
                            )
                            is_alive = death_reason == -1
                        except (TypeError, ValueError):
                            is_alive = None
                    else:
                        is_alive = None

                    # -----------------------------
                    # 3. is_platoon
                    # -----------------------------
                    players_data = first_result.get("players", {})
                    try:
                        is_platoon = ExtractorV2._is_owner_in_platoon(
                            player_id,
                            players_data,
                        )
                    except Exception:
                        is_platoon = None

                    # -----------------------------
                    # Проверка изменений
                    # -----------------------------
                    changed = False

                    if replay.battle_duration != duration:
                        replay.battle_duration = duration
                        changed = True

                    if replay.is_alive != is_alive:
                        replay.is_alive = is_alive
                        changed = True

                    if replay.is_platoon != is_platoon:
                        replay.is_platoon = is_platoon
                        changed = True

                    if changed:
                        to_update.append(replay)
                        updated_count += 1
                    else:
                        skipped_count += 1

                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"PK={replay.pk} ERROR: {e}")
                    )

            if to_update and not dry_run:
                Replay.objects.bulk_update(
                    to_update,
                    ["battle_duration", "is_alive", "is_platoon"],
                    batch_size=batch_size,
                )

            processed = min(offset + batch_size, len(replay_ids))
            self.stdout.write(
                f"{processed}/{total} "
                f"(обновлено: {updated_count}, "
                f"пропущено: {skipped_count}, "
                f"ошибок: {error_count})"
            )

        self.stdout.write("\nЗАВЕРШЕНО")
        self.stdout.write(f"Обновлено: {updated_count}")
        self.stdout.write(f"Пропущено: {skipped_count}")
        self.stdout.write(f"Ошибок: {error_count}")