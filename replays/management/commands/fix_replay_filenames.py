import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from replays.models import Replay


class Command(BaseCommand):
    help = 'Исправление file_name реплеев на основе совпадения payload данных'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='Количество записей для обработки (по умолчанию: 5, 0 = все)'
        )
        parser.add_argument(
            '--mismatches-file',
            type=str,
            default='replay_data_mismatches.json',
            help='Файл с несовпадениями (по умолчанию: replay_data_mismatches.json)'
        )
        parser.add_argument(
            '--arena-player-file',
            type=str,
            default='replay_arena_player_data.json',
            help='Файл с правильными данными (по умолчанию: replay_arena_player_data.json)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Тестовый прогон без сохранения изменений'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        mismatches_file = Path(settings.BASE_DIR) / options['mismatches_file']
        arena_player_file = Path(settings.BASE_DIR) / options['arena_player_file']
        dry_run = options['dry_run']

        # Загружаем файл с несовпадениями
        if not mismatches_file.exists():
            self.stdout.write(self.style.ERROR(f'Файл {mismatches_file} не найден'))
            return

        with open(mismatches_file, 'r', encoding='utf-8') as f:
            mismatches = json.load(f)

        self.stdout.write(self.style.SUCCESS(f'Загружено {len(mismatches)} записей из {mismatches_file}'))

        # Загружаем файл с правильными данными
        if not arena_player_file.exists():
            self.stdout.write(self.style.ERROR(f'Файл {arena_player_file} не найден'))
            return

        with open(arena_player_file, 'r', encoding='utf-8') as f:
            arena_player_data = json.load(f)

        self.stdout.write(self.style.SUCCESS(f'Загружено {len(arena_player_data)} записей из {arena_player_file}\n'))

        # Создаем индекс для быстрого поиска по payload
        # Ключ: (arenaUniqueID, playerName) -> file_name
        payload_index = {}
        for file_name, data in arena_player_data.items():
            if data.get('status') == 'success':
                arena_id = data.get('arenaUniqueID')
                player_name = data.get('playerName')
                if arena_id and player_name:
                    key = (arena_id, player_name)
                    payload_index[key] = file_name

        self.stdout.write(self.style.SUCCESS(f'Создан индекс из {len(payload_index)} записей\n'))

        if dry_run:
            self.stdout.write(self.style.WARNING('ТЕСТОВЫЙ ПРОГОН - изменения НЕ будут сохранены!\n'))

        # Обрабатываем записи
        records_to_process = mismatches[:limit] if limit > 0 else mismatches
        total = len(records_to_process)

        self.stdout.write(self.style.SUCCESS(f'Обработка {total} записей...\n'))
        self.stdout.write('=' * 80)

        found_matches = []
        not_found_matches = []
        found_count = 0
        not_found_count = 0
        updated_count = 0
        error_count = 0

        for i, record in enumerate(records_to_process, 1):
            replay_id = record.get('replay_id')
            current_file_name = record.get('file_name')
            payload = record.get('payload', {})

            arena_id = payload.get('arenaUniqueID')
            player_name = payload.get('playerName')

            self.stdout.write(f'\n[{i}/{total}] Replay ID: {replay_id}')
            self.stdout.write(f'  Текущий file_name: {current_file_name}')
            self.stdout.write(f'  Payload: arenaID={arena_id}, player={player_name}')

            if not arena_id or not player_name:
                self.stdout.write(self.style.WARNING('  ⚠️  Пропущено: неполные данные payload'))
                not_found_count += 1
                not_found_matches.append({
                    **record,
                    'reason': 'incomplete_payload'
                })
                continue

            # Ищем совпадение по payload
            search_key = (arena_id, player_name)
            correct_file_name = payload_index.get(search_key)

            if correct_file_name:
                found_count += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ Найдено совпадение: {correct_file_name}'))

                match_info = {
                    **record,
                    'correct_file_name': correct_file_name,
                    'old_file_name': current_file_name
                }

                if correct_file_name == current_file_name:
                    self.stdout.write('  → file_name уже корректный, обновление не требуется')
                    match_info['action'] = 'already_correct'
                    found_matches.append(match_info)
                    continue

                # Обновляем запись в БД
                try:
                    if not dry_run:
                        replay = Replay.objects.get(id=replay_id)
                        replay.file_name = correct_file_name
                        replay.save(update_fields=['file_name'])
                        updated_count += 1
                        match_info['action'] = 'updated'
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Обновлено: {current_file_name} → {correct_file_name}'))
                    else:
                        updated_count += 1
                        match_info['action'] = 'will_update'
                        self.stdout.write(self.style.SUCCESS(f'  [DRY RUN] Будет обновлено: {current_file_name} → {correct_file_name}'))

                    found_matches.append(match_info)

                except Replay.DoesNotExist:
                    error_count += 1
                    match_info['action'] = 'error'
                    match_info['error'] = 'Replay not found in DB'
                    found_matches.append(match_info)
                    self.stdout.write(self.style.ERROR(f'  ✗ Ошибка: Replay с ID {replay_id} не найден в БД'))
                except Exception as e:
                    error_count += 1
                    match_info['action'] = 'error'
                    match_info['error'] = str(e)
                    found_matches.append(match_info)
                    self.stdout.write(self.style.ERROR(f'  ✗ Ошибка при обновлении: {e}'))

            else:
                not_found_count += 1
                not_found_matches.append({
                    **record,
                    'reason': 'no_match_in_arena_player_data'
                })
                self.stdout.write(self.style.WARNING('  ✗ Совпадение НЕ найдено в arena_player_data'))

        # Сохраняем результаты в файлы
        base_dir = Path(settings.BASE_DIR)

        if found_matches:
            found_file = base_dir / 'replay_filenames_found.json'
            with open(found_file, 'w', encoding='utf-8') as f:
                json.dump(found_matches, f, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f'\nНайденные совпадения сохранены в {found_file}'))

        if not_found_matches:
            not_found_file = base_dir / 'replay_filenames_not_found.json'
            with open(not_found_file, 'w', encoding='utf-8') as f:
                json.dump(not_found_matches, f, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.WARNING(f'Не найденные сохранены в {not_found_file}'))

        # Итоговая статистика
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('ИТОГИ'))
        self.stdout.write('=' * 80)
        self.stdout.write(f'Обработано записей:    {total}')
        self.stdout.write(f'Найдено совпадений:    {found_count}')
        if dry_run:
            self.stdout.write(self.style.WARNING(f'Будет обновлено:       {updated_count}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Обновлено:             {updated_count}'))
        self.stdout.write(self.style.WARNING(f'Не найдено:            {not_found_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Ошибок:                {error_count}'))
        self.stdout.write('=' * 80)

        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  Это был ТЕСТОВЫЙ ПРОГОН. Для применения изменений запустите без --dry-run'))
