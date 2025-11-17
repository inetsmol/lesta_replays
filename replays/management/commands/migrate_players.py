"""
Management команда для миграции игроков на новую структуру с accountDBID.

Команда проходит по всем реплеям в базе данных, извлекает данные игроков
из payload и создаёт новые записи Player с правильными полями:
- accountDBID (уникальный ID)
- real_name (настоящее имя)
- fake_name (имя в бою)
- clan_tag (тег клана)

Использование:
    python manage.py migrate_players
    python manage.py migrate_players --dry-run  # Без изменений в БД
    python manage.py migrate_players --batch-size 100  # Обработка порциями
    python manage.py migrate_players --cleanup-unused  # С удалением старых записей
    python manage.py migrate_players --cleanup-unused --dry-run  # Просмотр без изменений
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from replays.models import Replay, Player
from replays.parser.extractor import ExtractorV2
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Мигрирует игроков на новую структуру с accountDBID из payload реплеев'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет сделано, но не вносить изменения в БД',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Количество реплеев для обработки за один раз (по умолчанию: 50)',
        )
        parser.add_argument(
            '--clear-players',
            action='store_true',
            help='Удалить всех существующих игроков перед миграцией',
        )
        parser.add_argument(
            '--cleanup-unused',
            action='store_true',
            help='Удалить неиспользуемых игроков без accountDBID после миграции',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        clear_players = options['clear_players']
        cleanup_unused = options['cleanup_unused']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN режим - изменения НЕ будут сохранены'))

        # Статистика
        total_replays = Replay.objects.count()
        processed = 0
        created_players = 0
        updated_players = 0
        errors = 0

        self.stdout.write(self.style.SUCCESS(f'📊 Найдено реплеев: {total_replays}'))

        # Очистка M2M связей participants (они будут пересозданы)
        if not dry_run:
            self.stdout.write('🔄 Очистка M2M связей participants...')
            for replay in Replay.objects.all():
                replay.participants.clear()
            self.stdout.write(self.style.SUCCESS('✅ Очищены participants у всех реплеев'))

        # Обработка реплеев порциями
        for offset in range(0, total_replays, batch_size):
            replays = Replay.objects.all()[offset:offset + batch_size]

            for replay in replays:
                try:
                    processed += 1

                    if processed % 10 == 0:
                        self.stdout.write(f'⏳ Обработано: {processed}/{total_replays}')

                    # Извлекаем владельца
                    owner_data = ExtractorV2.get_replay_owner_from_payload(replay.payload)
                    if not owner_data or not owner_data.get("accountDBID"):
                        self.stdout.write(
                            self.style.WARNING(f'⚠️  Replay {replay.id}: не удалось извлечь владельца')
                        )
                        errors += 1
                        continue

                    # Извлекаем участников
                    participants_data = ExtractorV2.parse_players_payload(replay.payload)

                    if not dry_run:
                        with transaction.atomic():
                            # Проверяем, существует ли уже Player с таким accountDBID
                            try:
                                existing_player = Player.objects.get(accountDBID=owner_data["accountDBID"])
                                # Игрок с таким accountDBID уже существует
                                # Обновляем его данные
                                existing_player.real_name = owner_data["real_name"]
                                existing_player.fake_name = owner_data["fake_name"]
                                existing_player.clan_tag = owner_data["clan_tag"]
                                existing_player.save()
                                updated_players += 1

                                # Если это не тот же owner, заменяем
                                if replay.owner.id != existing_player.id:
                                    # Удаляем старую запись owner (если она не используется другими реплеями)
                                    old_owner = replay.owner
                                    replay.owner = existing_player
                                    replay.save()

                                    # Проверяем, можно ли удалить старую запись
                                    if not Replay.objects.filter(owner=old_owner).exists():
                                        old_owner.delete()

                                owner = existing_player

                            except Player.DoesNotExist:
                                # Игрока с таким accountDBID нет, обновляем текущего owner
                                old_owner = replay.owner
                                old_owner.accountDBID = owner_data["accountDBID"]
                                old_owner.real_name = owner_data["real_name"]
                                old_owner.fake_name = owner_data["fake_name"]
                                old_owner.clan_tag = owner_data["clan_tag"]
                                old_owner.save()
                                updated_players += 1
                                owner = old_owner

                            # Создаём/обновляем участников
                            participant_objs = []
                            for player_data in participants_data:
                                account_id = player_data.get("accountDBID")
                                if not account_id:
                                    continue

                                player, created = Player.objects.update_or_create(
                                    accountDBID=account_id,
                                    defaults={
                                        "real_name": player_data.get("real_name", ""),
                                        "fake_name": player_data.get("fake_name", ""),
                                        "clan_tag": player_data.get("clan_tag", ""),
                                    }
                                )
                                if created:
                                    created_players += 1
                                else:
                                    updated_players += 1

                                participant_objs.append(player)

                            # Очищаем старые связи и добавляем новые
                            replay.participants.clear()
                            if participant_objs:
                                replay.participants.add(*participant_objs)

                            replay.save()

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'❌ Ошибка обработки replay {replay.id}: {e}')
                    )
                    logger.exception(f"Ошибка при миграции replay {replay.id}")
                    errors += 1

        # Итоги
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('📈 ИТОГИ МИГРАЦИИ'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'✅ Обработано реплеев: {processed}')
        self.stdout.write(f'✨ Создано новых игроков: {created_players}')
        self.stdout.write(f'🔄 Обновлено игроков: {updated_players}')
        self.stdout.write(f'❌ Ошибок: {errors}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  DRY RUN - изменения НЕ были сохранены!'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ Миграция успешно завершена!'))

            # Финальная статистика
            total_players = Player.objects.count()
            self.stdout.write(f'👥 Всего игроков в базе: {total_players}')

        # Очистка неиспользуемых игроков
        if cleanup_unused and not dry_run:
            self.stdout.write('\n' + '=' * 60)
            self.stdout.write('🧹 ОЧИСТКА НЕИСПОЛЬЗУЕМЫХ ИГРОКОВ')
            self.stdout.write('=' * 60)

            # Находим игроков без accountDBID
            players_without_accountDBID = Player.objects.filter(accountDBID__isnull=True)
            unused_count = players_without_accountDBID.count()

            if unused_count == 0:
                self.stdout.write(self.style.SUCCESS('✅ Нет игроков без accountDBID'))
            else:
                self.stdout.write(f'🔍 Найдено игроков без accountDBID: {unused_count}')

                # Проверяем, используются ли они как owner
                used_as_owner = Replay.objects.filter(owner__accountDBID__isnull=True).count()
                self.stdout.write(f'📌 Используются как owner: {used_as_owner}')

                # Проверяем, используются ли они как participants
                used_as_participants = 0
                for player in players_without_accountDBID[:100]:  # проверим первые 100
                    if player.participated_replays.exists():
                        used_as_participants += 1

                self.stdout.write(f'📌 Используются как participants (из первых 100): {used_as_participants}')

                if used_as_owner == 0 and used_as_participants == 0:
                    self.stdout.write(self.style.WARNING(f'🗑️  Удаление {unused_count} неиспользуемых игроков...'))
                    deleted_count, _ = players_without_accountDBID.delete()
                    self.stdout.write(self.style.SUCCESS(f'✅ Удалено старых записей: {deleted_count}'))

                    # Обновлённая статистика
                    total_players_after = Player.objects.count()
                    self.stdout.write(f'👥 Игроков после очистки: {total_players_after}')
                else:
                    self.stdout.write(self.style.ERROR(
                        '⚠️  ВНИМАНИЕ: Некоторые игроки без accountDBID всё ещё используются!'
                    ))
                    self.stdout.write(self.style.ERROR(
                        '    Пропустите --cleanup-unused или сначала исправьте данные.'
                    ))
        elif cleanup_unused and dry_run:
            self.stdout.write('\n' + '=' * 60)
            self.stdout.write('🧹 ОЧИСТКА НЕИСПОЛЬЗУЕМЫХ ИГРОКОВ (DRY RUN)')
            self.stdout.write('=' * 60)

            players_without_accountDBID = Player.objects.filter(accountDBID__isnull=True)
            unused_count = players_without_accountDBID.count()

            self.stdout.write(f'🔍 Будет удалено игроков без accountDBID: {unused_count}')
            self.stdout.write(self.style.WARNING('⚠️  DRY RUN - удаление НЕ выполнено'))
