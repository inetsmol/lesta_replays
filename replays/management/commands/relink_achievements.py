"""
Management-команда для пересвязки достижений (M2M) у существующих реплеев.

Проходит по всем реплеям, извлекает achievement_id из payload
(dossierLogRecords) и привязывает соответствующие Achievement объекты.

Использование:
    python manage.py relink_achievements          # dry-run (только показать)
    python manage.py relink_achievements --apply  # применить изменения
"""

from django.core.management.base import BaseCommand

from replays.models import Replay, Achievement
from replays.parser.extractor import ExtractorV2


class Command(BaseCommand):
    help = "Пересвязать достижения (M2M) для существующих реплеев из payload"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Применить изменения (без флага — dry-run)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]

        # Все achievement_id, которые есть в БД
        known_ids = set(
            Achievement.objects.values_list("achievement_id", flat=True)
        )
        self.stdout.write(f"Achievement в БД: {len(known_ids)}")

        replays = Replay.objects.all()
        total = replays.count()
        linked = 0
        skipped = 0
        errors = 0

        for i, replay in enumerate(replays.iterator(), 1):
            try:
                ach_ids = ExtractorV2.get_achievements(replay.payload)
            except Exception as e:
                errors += 1
                self.stderr.write(f"  [{i}/{total}] Replay #{replay.pk}: ошибка — {e}")
                continue

            if not ach_ids:
                skipped += 1
                continue

            # Только те, что есть в справочнике
            valid_ids = set(ach_ids) & known_ids

            if not valid_ids:
                skipped += 1
                continue

            if apply:
                achievements = Achievement.objects.filter(
                    achievement_id__in=valid_ids
                )
                replay.achievements.set(achievements)
                replay.achievement_count = achievements.count()
                replay.save(update_fields=["achievement_count"])

            linked += 1
            if i % 100 == 0 or i == total:
                self.stdout.write(f"  [{i}/{total}] обработано...")

        mode = "ПРИМЕНЕНО" if apply else "DRY-RUN"
        self.stdout.write(self.style.SUCCESS(
            f"\n{mode}: всего {total}, привязано {linked}, "
            f"пропущено {skipped}, ошибок {errors}"
        ))
        if not apply:
            self.stdout.write(
                "Запустите с --apply для применения изменений."
            )
