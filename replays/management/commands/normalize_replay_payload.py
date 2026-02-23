import json

from django.core.management.base import BaseCommand

from replays.models import Replay


class Command(BaseCommand):
    help = (
        "Конвертирует старые строковые Replay.payload в JSON-объекты "
        "для корректного хранения в JSONField."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Размер батча для bulk_update (по умолчанию: 500).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Обработать только первые N реплеев (0 = все).",
        )
        parser.add_argument(
            "--from-id",
            type=int,
            default=0,
            help="Начинать обработку с этого ID (включительно).",
        )
        parser.add_argument(
            "--to-id",
            type=int,
            default=0,
            help="Закончить обработку на этом ID (включительно).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать статистику, без записи в БД.",
        )

    def handle(self, *args, **options):
        batch_size = max(int(options["batch_size"]), 1)
        limit = max(int(options["limit"]), 0)
        from_id = max(int(options["from_id"]), 0)
        to_id = max(int(options["to_id"]), 0)
        dry_run = bool(options["dry_run"])

        queryset = Replay.objects.only("id", "payload").order_by("id")
        if from_id:
            queryset = queryset.filter(id__gte=from_id)
        if to_id:
            queryset = queryset.filter(id__lte=to_id)
        if limit:
            queryset = queryset[:limit]

        total = 0
        converted = 0
        updated = 0
        already_json = 0
        invalid_json = 0
        invalid_type = 0
        update_errors = 0

        to_update = []

        def flush_updates():
            nonlocal updated, update_errors, to_update
            if not to_update:
                return

            try:
                Replay.objects.bulk_update(to_update, ["payload"], batch_size=batch_size)
                updated += len(to_update)
            except Exception:
                # Fallback на поштучное обновление, чтобы не потерять весь батч.
                for replay in to_update:
                    try:
                        Replay.objects.filter(pk=replay.pk).update(payload=replay.payload)
                        updated += 1
                    except Exception:
                        update_errors += 1
            finally:
                to_update = []

        for replay in queryset.iterator(chunk_size=batch_size):
            total += 1
            payload = replay.payload

            if not isinstance(payload, str):
                already_json += 1
                continue

            try:
                parsed = json.loads(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                invalid_json += 1
                continue

            if not isinstance(parsed, (list, dict)):
                invalid_type += 1
                continue

            converted += 1
            if dry_run:
                continue

            replay.payload = parsed
            to_update.append(replay)
            if len(to_update) >= batch_size:
                flush_updates()

        if not dry_run:
            flush_updates()

        self.stdout.write(
            self.style.SUCCESS(
                "Готово: "
                f"processed={total}, converted={converted}, updated={updated}, "
                f"already_json={already_json}, invalid_json={invalid_json}, "
                f"invalid_type={invalid_type}, update_errors={update_errors}, "
                f"dry_run={dry_run}"
            )
        )
