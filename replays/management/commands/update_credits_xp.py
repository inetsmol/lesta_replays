# replays/management/commands/update_credits_xp.py
"""
Management команда для обновления полей credits и xp во всех реплеях.
Использует данные из payload через ExtractorV2.get_personal_data().
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from replays.models import Replay
from replays.parser.extractor import ExtractorV2


class Command(BaseCommand):
    help = 'Обновляет поля credits и xp во всех реплеях на основе данных из payload'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Размер батча для обработки записей (по умолчанию: 100)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Режим тестирования без сохранения изменений в БД'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Ограничить количество обрабатываемых записей (для тестирования)'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        limit = options['limit']

        self.stdout.write(self.style.WARNING(
            f"Режим: {'ТЕСТОВЫЙ (без сохранения)' if dry_run else 'БОЕВОЙ'}"
        ))

        # Получаем queryset всех реплеев
        queryset = Replay.objects.all()
        if limit:
            queryset = queryset[:limit]
            self.stdout.write(self.style.WARNING(f"Обработка ограничена {limit} записями"))

        total_count = queryset.count()
        self.stdout.write(f"Всего реплеев для обработки: {total_count}")

        updated_count = 0
        error_count = 0
        skipped_count = 0

        # Обрабатываем батчами для оптимизации памяти
        for offset in range(0, total_count, batch_size):
            batch = queryset[offset:offset + batch_size]

            with transaction.atomic():
                for replay in batch:
                    try:
                        # Проверяем наличие payload
                        if not replay.payload:
                            self.stdout.write(self.style.WARNING(
                                f"  [SKIP] Реплей #{replay.pk}: отсутствует payload"
                            ))
                            skipped_count += 1
                            continue

                        # Извлекаем персональные данные через ExtractorV2
                        personal_data = ExtractorV2.get_personal_data(replay.payload)

                        # Получаем значения original_credits и original_xp
                        original_credits = personal_data.get('original_credits')
                        original_xp = personal_data.get('original_xp')

                        # Проверяем, что значения существуют
                        if original_credits is None and original_xp is None:
                            self.stdout.write(self.style.WARNING(
                                f"  [SKIP] Реплей #{replay.pk}: нет данных original_credits и original_xp"
                            ))
                            skipped_count += 1
                            continue

                        # Сохраняем старые значения для логирования
                        old_credits = replay.credits
                        old_xp = replay.xp

                        # Обновляем поля (используем 0 если значение None)
                        new_credits = original_credits if original_credits is not None else replay.credits
                        new_xp = original_xp if original_xp is not None else replay.xp

                        # Проверяем, изменились ли значения
                        if old_credits == new_credits and old_xp == new_xp:
                            skipped_count += 1
                            continue

                        if not dry_run:
                            replay.credits = new_credits
                            replay.xp = new_xp
                            replay.save(update_fields=['credits', 'xp'])

                        updated_count += 1

                        # Выводим информацию о каждом обновлении
                        changes = []
                        if old_credits != new_credits:
                            changes.append(f"credits: {old_credits} → {new_credits}")
                        if old_xp != new_xp:
                            changes.append(f"xp: {old_xp} → {new_xp}")

                        self.stdout.write(self.style.SUCCESS(
                            f"  [OK] Реплей #{replay.pk}: {', '.join(changes)}"
                        ))

                    except Exception as e:
                        error_count += 1
                        self.stdout.write(self.style.ERROR(
                            f"  [ERROR] Реплей #{replay.pk}: {str(e)}"
                        ))

                # Если dry-run, откатываем транзакцию
                if dry_run:
                    transaction.set_rollback(True)

            # Прогресс
            processed = min(offset + batch_size, total_count)
            self.stdout.write(
                f"Обработано: {processed}/{total_count} "
                f"(обновлено: {updated_count}, пропущено: {skipped_count}, ошибок: {error_count})"
            )

        # Итоговая статистика
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("ЗАВЕРШЕНО"))
        self.stdout.write(f"Всего реплеев: {total_count}")
        self.stdout.write(self.style.SUCCESS(f"Обновлено: {updated_count}"))
        self.stdout.write(self.style.WARNING(f"Пропущено: {skipped_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"Ошибок: {error_count}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  Режим тестирования - изменения НЕ сохранены в БД"))
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ Изменения успешно сохранены в БД"))
