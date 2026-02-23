import json
from datetime import timedelta

from django.core.management.base import BaseCommand

from replays.models import Replay
from replays.parser.extractor import ParserUtils


class Command(BaseCommand):
    help = (
        "Normalize Replay.battle_date using payload common.arenaCreateTime "
        "to fix timezone-shifted records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving.",
        )
        parser.add_argument(
            "--threshold-minutes",
            type=int,
            default=30,
            help="Update only when abs(current - corrected) >= this many minutes (default: 30).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Process only first N replays (0 = all).",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        threshold_minutes = max(int(options["threshold_minutes"]), 0)
        limit = max(int(options["limit"]), 0)

        qs = Replay.objects.only("id", "payload", "battle_date").order_by("id")
        if limit:
            qs = qs[:limit]

        total = 0
        skipped = 0
        parse_errors = 0
        to_update = []
        threshold = timedelta(minutes=threshold_minutes)

        for replay in qs.iterator():
            total += 1
            payload = replay.payload
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (TypeError, ValueError, json.JSONDecodeError):
                    parse_errors += 1
                    continue

            if not isinstance(payload, (list, tuple)) or len(payload) < 2:
                parse_errors += 1
                continue

            first_block = payload[0] if isinstance(payload[0], dict) else {}
            second_block = payload[1] if isinstance(payload[1], (list, tuple)) else ()
            first_result = second_block[0] if second_block and isinstance(second_block[0], dict) else {}
            common = first_result.get("common", {}) if isinstance(first_result, dict) else {}

            dt_raw = first_block.get("dateTime")
            arena_create_time = common.get("arenaCreateTime")
            if not isinstance(dt_raw, str) and arena_create_time in (None, "", 0, "0"):
                skipped += 1
                continue

            dt_fallback = dt_raw if isinstance(dt_raw, str) else "01.01.1970 00:00:00"
            try:
                corrected_dt = ParserUtils._parse_battle_datetime(
                    dt_fallback,
                    arena_create_time=arena_create_time,
                )
            except Exception:
                parse_errors += 1
                continue

            current_dt = replay.battle_date
            if current_dt is None:
                delta = threshold
            else:
                delta = abs(current_dt - corrected_dt)

            if delta >= threshold:
                to_update.append((replay, current_dt, corrected_dt, delta))
            else:
                skipped += 1

        if to_update:
            if not dry_run:
                update_instances = []
                for replay, _, corrected_dt, _ in to_update:
                    replay.battle_date = corrected_dt
                    update_instances.append(replay)
                Replay.objects.bulk_update(update_instances, ["battle_date"], batch_size=500)

        self.stdout.write(f"Processed: {total}")
        self.stdout.write(f"Will update: {len(to_update)}")
        self.stdout.write(f"Skipped: {skipped}")
        self.stdout.write(f"Parse errors: {parse_errors}")
        self.stdout.write(f"Mode: {'dry-run' if dry_run else 'apply'}")

        if to_update:
            self.stdout.write("")
            self.stdout.write("Examples:")
            for replay, current_dt, corrected_dt, delta in to_update[:10]:
                self.stdout.write(
                    f"  Replay #{replay.id}: {current_dt} -> {corrected_dt} "
                    f"(shift={delta})"
                )
