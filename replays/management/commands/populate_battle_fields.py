# replays/management/commands/populate_battle_fields.py
"""
Management-команда для заполнения полей:
- battle_duration
- is_alive
- is_platoon

Корректно обрабатывает payload, если он хранится как:
- JSONField (dict/list)
- строка JSON (TextField)

Использует bulk_update для производительности.
"""

import json
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q
from replays.models import Replay
from replays.parser.extractor import ExtractorV2


class Command(BaseCommand):
    help = "Заполняет battle поля из payload существующих реплеев"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Размер батча (по умолчанию 100)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Тестовый режим без сохранения",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Ограничить количество записей",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Обновить все записи",
        )

    def handle(self, *args, **options):
        batch_size: int = options["batch_size"]
        dry_run: bool = options["dry_run"]
        limit: int | None = options["limit"]
        force: bool = options["force"]

        self.stdout.write(
            self.style.WARNING(
                f"Режим: {'ТЕСТОВЫЙ' if dry_run else 'БОЕВОЙ'}"
            )
        )

        # --- Формируем queryset ---
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
            self.stdout.write(f"Ограничение: {limit}")

        total_count = queryset.count()
        self.stdout.write(f"Реплеев для обработки: {total_count}")

        updated_count = 0
        skipped_count = 0
        error_count = 0

        replay_ids = list(queryset.values_list("pk", flat=True))

        # --- Батч-обработка ---
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

                    # --- Если payload строка → парсим JSON ---
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except json.JSONDecodeError:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"[PK={replay.pk}] payload невалидный JSON"
                                )
                            )
                            skipped_count += 1
                            continue

                    # --- Проверяем структуру ---
                    if not isinstance(payload, (list, tuple)):
                        skipped_count += 1
                        continue

                    metadata = payload[0] if len(payload) > 0 else {}

                    battle_results = None
                    if len(payload) > 1:
                        second_block = payload[1]
                        if (
                            isinstance(second_block, (list, tuple))
                            and len(second_block) > 0
                        ):
                            battle_results = second_block[0]

                    if not isinstance(battle_results, dict):
                        skipped_count += 1
                        continue

                    common_data = battle_results.get("common", {})
                    personal_data = battle_results.get("personal", {})
                    players_data = battle_results.get("players", {})
                    player_id = metadata.get("playerID")

                    changed = False

                    # --- battle_duration ---
                    raw_duration = common_data.get("duration")

                    try:
                        duration = (
                            int(raw_duration)
                            if raw_duration is not None
                            else None
                        )
                    except (TypeError, ValueError):
                        duration = None

                    if replay.battle_duration != duration:
                        replay.battle_duration = duration
                        changed = True

                    # --- is_alive ---
                    death_reason = personal_data.get("deathReason")

                    try:
                        is_alive = (
                            int(death_reason) == -1
                            if death_reason is not None
                            else None
                        )
                    except (TypeError, ValueError):
                        is_alive = None

                    if replay.is_alive != is_alive:
                        replay.is_alive = is_alive
                        changed = True

                    # --- is_platoon ---
                    try:
                        is_platoon = ExtractorV2._is_owner_in_platoon(
                            player_id,
                            players_data,
                        )
                    except Exception:
                        is_platoon = None

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
                        self.style.ERROR(
                            f"[ERROR] PK={replay.pk}: {e}"
                        )
                    )

            # --- bulk_update ---
            if to_update and not dry_run:
                Replay.objects.bulk_update(
                    to_update,
                    ["battle_duration", "is_alive", "is_platoon"],
                    batch_size=batch_size,
                )

            processed = min(offset + batch_size, len(replay_ids))
            self.stdout.write(
                f"Обработано: {processed}/{total_count} "
                f"(обновлено: {updated_count}, "
                f"пропущено: {skipped_count}, "
                f"ошибок: {error_count})"
            )

        # --- Финальный отчёт ---
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("ЗАВЕРШЕНО"))
        self.stdout.write(f"Всего: {total_count}")
        self.stdout.write(self.style.SUCCESS(f"Обновлено: {updated_count}"))
        self.stdout.write(self.style.WARNING(f"Пропущено: {skipped_count}"))

        if error_count:
            self.stdout.write(
                self.style.ERROR(f"Ошибок: {error_count}")
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN — изменения не сохранены")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Изменения сохранены")
            )