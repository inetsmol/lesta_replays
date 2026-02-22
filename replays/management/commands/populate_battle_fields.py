# replays/management/commands/populate_battle_fields.py
"""
Management команда для заполнения полей battle_duration, is_alive, is_platoon
в существующих реплеях на основе данных из payload.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from replays.models import Replay
from replays.parser.extractor import ExtractorV2


class Command(BaseCommand):
    help = 'Заполняет поля battle_duration, is_alive, is_platoon из payload существующих реплеев'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Размер батча для обработки (по умолчанию: 100)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Режим тестирования без сохранения изменений'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Ограничить количество обрабатываемых записей'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Обновить все записи, даже если поля уже заполнены'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        limit = options['limit']
        force = options['force']

        self.stdout.write(self.style.WARNING(
            f"Режим: {'ТЕСТОВЫЙ (без сохранения)' if dry_run else 'БОЕВОЙ'}"
        ))

        # По умолчанию обрабатываем только записи с незаполненными полями
        queryset = Replay.objects.all()
        if not force:
            queryset = queryset.filter(
                battle_duration__isnull=True
            ) | queryset.filter(
                is_alive__isnull=True
            ) | queryset.filter(
                is_platoon__isnull=True
            )
            queryset = queryset.distinct()

        queryset = queryset.order_by('pk')
        if limit:
            queryset = queryset[:limit]
            self.stdout.write(self.style.WARNING(f"Обработка ограничена {limit} записями"))

        total_count = queryset.count()
        self.stdout.write(f"Реплеев для обработки: {total_count}")

        updated_count = 0
        error_count = 0
        skipped_count = 0

        replay_ids = list(queryset.values_list('pk', flat=True))

        for offset in range(0, len(replay_ids), batch_size):
            batch_ids = replay_ids[offset:offset + batch_size]
            batch = Replay.objects.filter(pk__in=batch_ids)

            to_update = []

            for replay in batch:
                try:
                    if not replay.payload:
                        skipped_count += 1
                        continue

                    payload = replay.payload

                    # Извлекаем данные из payload
                    metadata = payload[0] if isinstance(payload, (list, tuple)) and len(payload) > 0 else {}
                    battle_results = None
                    if isinstance(payload, (list, tuple)) and len(payload) > 1:
                        second_block = payload[1]
                        if isinstance(second_block, (list, tuple)) and len(second_block) > 0:
                            battle_results = second_block[0]

                    if not battle_results or not isinstance(battle_results, dict):
                        skipped_count += 1
                        continue

                    common_data = battle_results.get('common', {})
                    personal_data = battle_results.get('personal', {})
                    players_data = battle_results.get('players', {})
                    player_id = metadata.get('playerID')

                    changed = False

                    # battle_duration
                    duration = int(common_data.get('duration', 0)) or None
                    if replay.battle_duration != duration:
                        replay.battle_duration = duration
                        changed = True

                    # is_alive
                    death_reason = personal_data.get('deathReason', -1)
                    try:
                        is_alive = int(death_reason) == -1
                    except (TypeError, ValueError):
                        is_alive = None
                    if replay.is_alive != is_alive:
                        replay.is_alive = is_alive
                        changed = True

                    # is_platoon
                    is_platoon = ExtractorV2._is_owner_in_platoon(player_id, players_data)
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
                    self.stdout.write(self.style.ERROR(
                        f"  [ERROR] Реплей #{replay.pk}: {e}"
                    ))

            if to_update and not dry_run:
                Replay.objects.bulk_update(to_update, ['battle_duration', 'is_alive', 'is_platoon'], batch_size=batch_size)

            processed = min(offset + batch_size, len(replay_ids))
            self.stdout.write(
                f"Обработано: {processed}/{total_count} "
                f"(обновлено: {updated_count}, пропущено: {skipped_count}, ошибок: {error_count})"
            )

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("ЗАВЕРШЕНО"))
        self.stdout.write(f"Всего реплеев: {total_count}")
        self.stdout.write(self.style.SUCCESS(f"Обновлено: {updated_count}"))
        self.stdout.write(self.style.WARNING(f"Пропущено: {skipped_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"Ошибок: {error_count}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("\nРежим тестирования - изменения НЕ сохранены"))
        else:
            self.stdout.write(self.style.SUCCESS("\nИзменения сохранены"))
