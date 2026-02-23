import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from replays.models import Replay
from replays.parser.extractor import ExtractorV2


class Command(BaseCommand):
    help = 'Сравнение данных реплеев с данными в replay_arena_player_data.json'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='Количество реплеев для проверки (по умолчанию: 5, 0 = все)'
        )
        parser.add_argument(
            '--json-file',
            type=str,
            default='replay_arena_player_data.json',
            help='Путь к JSON файлу с данными (по умолчанию: replay_arena_player_data.json)'
        )
        parser.add_argument(
            '--output',
            type=str,
            default='replay_data_mismatches.json',
            help='Файл для сохранения несовпадений (по умолчанию: replay_data_mismatches.json)'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        json_file_path = Path(settings.BASE_DIR) / options['json_file']
        output_file_path = Path(settings.BASE_DIR) / options['output']

        # Загружаем данные из JSON файла
        if not json_file_path.exists():
            self.stdout.write(self.style.ERROR(f'Файл {json_file_path} не найден'))
            return

        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        self.stdout.write(self.style.SUCCESS(f'Загружено {len(json_data)} записей из {json_file_path}\n'))

        # Получаем реплеи
        if limit > 0:
            replays = Replay.objects.all()[:limit]
        else:
            replays = Replay.objects.all()

        if not replays:
            self.stdout.write(self.style.WARNING('Реплеи не найдены'))
            return

        total_count = replays.count() if limit == 0 else len(replays)
        self.stdout.write(self.style.SUCCESS(f'Проверка {total_count} реплеев...\n'))

        # Список проблемных реплеев
        issues = []
        checked_count = 0
        match_count = 0
        mismatch_count = 0
        not_found_count = 0
        error_count = 0

        for i, replay in enumerate(replays, 1):
            checked_count += 1

            # Прогресс каждые 10 реплеев
            if i % 10 == 0:
                self.stdout.write(f'Обработано: {i}/{total_count}...', ending='\r')

            try:
                # Получаем первый блок (метаданные) из payload
                first_block = ExtractorV2.get_first_block(replay.payload)

                # Извлекаем данные напрямую из метаданных
                payload_arena_id = first_block.get('arenaUniqueID')
                payload_player_name = first_block.get('playerName')

                # Ищем запись в JSON файле
                json_record = json_data.get(replay.file_name)

                if json_record is None:
                    not_found_count += 1

                    # Добавляем в список проблемных
                    issues.append({
                        'replay_id': replay.id,
                        'file_name': replay.file_name,
                        'issue_type': 'not_found_in_json',
                        'payload': {
                            'arenaUniqueID': payload_arena_id,
                            'playerName': payload_player_name
                        },
                        'json_file': None
                    })

                    self.stdout.write(
                        self.style.WARNING(f'[{i}] {replay.file_name} - НЕ НАЙДЕН в JSON файле')
                    )
                    continue

                # Сравниваем данные
                json_arena_id = json_record.get('arenaUniqueID')
                json_player_name = json_record.get('playerName')

                if payload_arena_id == json_arena_id and payload_player_name == json_player_name:
                    match_count += 1
                    # Данные совпадают - переходим к следующему
                    continue

                # Данные отличаются - добавляем в список
                mismatch_count += 1

                differences = []
                if payload_arena_id != json_arena_id:
                    differences.append('arenaUniqueID')
                if payload_player_name != json_player_name:
                    differences.append('playerName')

                issues.append({
                    'replay_id': replay.id,
                    'file_name': replay.file_name,
                    'issue_type': 'mismatch',
                    'payload': {
                        'arenaUniqueID': payload_arena_id,
                        'playerName': payload_player_name
                    },
                    'json_file': {
                        'arenaUniqueID': json_arena_id,
                        'playerName': json_player_name
                    },
                    'differences': differences
                })

                self.stdout.write(
                    self.style.ERROR(
                        f'\n[{i}] НЕСОВПАДЕНИЕ: {replay.file_name} (ID: {replay.id})'
                    )
                )
                self.stdout.write(f'    Payload:   arenaID={payload_arena_id}, player={payload_player_name}')
                self.stdout.write(f'    JSON file: arenaID={json_arena_id}, player={json_player_name}')
                self.stdout.write(f'    Различия:  {", ".join(differences)}\n')

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'\n[{i}] ОШИБКА при обработке {replay.file_name}: {e}\n'
                    )
                )

        # Сохраняем результаты
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(issues, f, ensure_ascii=False, indent=2)

        self.stdout.write(
            self.style.SUCCESS(f'\nРезультаты сохранены в {output_file_path}')
        )

        # Итоговая статистика
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('ИТОГИ ПРОВЕРКИ'))
        self.stdout.write('=' * 80)
        self.stdout.write(f'Проверено реплеев:     {checked_count}')
        self.stdout.write(f'Совпадений:            {match_count}')
        self.stdout.write(self.style.ERROR(f'Несовпадений:          {mismatch_count}'))
        self.stdout.write(self.style.WARNING(f'Не найдено в JSON:     {not_found_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Ошибок:                {error_count}'))
        self.stdout.write('=' * 80)
