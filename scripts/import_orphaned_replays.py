#!/usr/bin/env python
"""
Скрипт для загрузки файлов реплеев из папки media/orphaned_replays в базу данных.

Использует ReplayProcessingService для обработки каждого файла,
как если бы он был загружен через веб-интерфейс.

Алгоритм:
1. Сканирует папку media/orphaned_replays/{source}
2. Для каждого файла .mtreplay вызывает ReplayProcessingService.process_replay()
3. Собирает статистику успешных/неудачных импортов
4. Перемещает успешно импортированные файлы в media (корень)
"""
import sys
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Настраиваем Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lesta_replays.settings")
import django
django.setup()

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from replays.services import ReplayProcessingService
from replays.parser.parser import ParseError


class FileWrapper:
    """
    Обертка для файла, эмулирующая UploadedFile из Django.

    ReplayProcessingService ожидает объект с методами:
    - .seek(0) - сброс указателя
    - .read() - чтение содержимого
    - .chunks() - чтение по частям
    - .name - имя файла
    """

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.name = file_path.name
        self._content = None

    def seek(self, position: int):
        """Сброс указателя (не нужен для нашей реализации)."""
        pass

    def read(self) -> bytes:
        """Чтение всего содержимого файла."""
        if self._content is None:
            with open(self.file_path, 'rb') as f:
                self._content = f.read()
        return self._content

    def chunks(self, chunk_size: int = 64 * 1024):
        """Чтение файла по частям."""
        content = self.read()
        for i in range(0, len(content), chunk_size):
            yield content[i:i + chunk_size]


def get_orphaned_files(source_dir: Path) -> List[Path]:
    """
    Получает список всех файлов .mtreplay из указанной папки.

    Args:
        source_dir: Путь к папке с файлами

    Returns:
        Список путей к файлам
    """
    if not source_dir.exists():
        print(f"⚠️  Папка {source_dir} не существует!")
        return []

    files = list(source_dir.glob("*.mtreplay"))
    return sorted(files)


def import_orphaned_replays(
    source: str,
    dry_run: bool = True,
    user_id: int = None,
    move_to_root: bool = True
) -> None:
    """
    Импортирует файлы реплеев из orphaned_replays в БД.

    Args:
        source: Имя подпапки в orphaned_replays (например, "20250101_120000")
        dry_run: Если True, только показывает что будет импортировано
        user_id: ID пользователя, от имени которого загружать (опционально)
        move_to_root: Если True, перемещает успешно импортированные файлы в media
    """
    print("=" * 80)
    print("ИМПОРТ РЕПЛЕЕВ ИЗ ORPHANED_REPLAYS")
    print("=" * 80)

    if dry_run:
        print("\n⚠️  РЕЖИМ ПРЕДПРОСМОТРА (dry_run=True)")
        print("   Файлы будут обработаны, но записи НЕ будут сохранены в БД\n")
    else:
        print("\n✅ РЕЖИМ ИМПОРТА (dry_run=False)")
        print("   Записи БУДУТ созданы в базе данных\n")

    media_root = Path(settings.MEDIA_ROOT)
    orphaned_dir = media_root / "orphaned_replays" / source

    if not orphaned_dir.exists():
        print(f"❌ Папка не найдена: {orphaned_dir}")
        print("\nДоступные папки:")

        orphaned_base = media_root / "orphaned_replays"
        if orphaned_base.exists():
            subdirs = [d.name for d in orphaned_base.iterdir() if d.is_dir()]
            if subdirs:
                for subdir in sorted(subdirs):
                    print(f"  - {subdir}")
            else:
                print("  (нет доступных папок)")
        return

    print(f"📂 Папка источник: {orphaned_dir}")

    # Получаем пользователя (опционально)
    user = None
    if user_id:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
            print(f"👤 Пользователь: {user.username} (ID: {user_id})")
        except User.DoesNotExist:
            print(f"⚠️  Пользователь с ID {user_id} не найден, файлы будут загружены без пользователя")

    # Получаем список файлов
    print("\nСканирование файлов...")
    files = get_orphaned_files(orphaned_dir)

    if not files:
        print("\n✅ Файлов для импорта не найдено!")
        return

    print(f"  Найдено файлов: {len(files)}\n")

    # Обработка файлов
    service = ReplayProcessingService()

    results: Dict[str, List[Dict[str, Any]]] = {
        'success': [],
        'duplicate': [],
        'parse_error': [],
        'validation_error': [],
        'other_error': []
    }

    print("Обработка файлов:\n")

    for i, file_path in enumerate(files, 1):
        file_name = file_path.name
        print(f"  [{i}/{len(files)}] {file_name:60s} ", end='')

        try:
            # Создаем обертку для файла
            file_wrapper = FileWrapper(file_path)

            if not dry_run:
                # Реальная обработка с сохранением в БД
                replay = service.process_replay(
                    uploaded_file=file_wrapper,
                    description='',
                    user=user
                )
                results['success'].append({
                    'file': file_name,
                    'replay_id': replay.id,
                    'tank': replay.tank.name if replay.tank else 'Unknown',
                    'owner': replay.owner.real_name
                })
                print("✅ OK")

                # Перемещаем файл в media (корень), если требуется
                if move_to_root:
                    # Файл уже был сохранен ReplayProcessingService в media
                    # с именем replay.file_name, удаляем оригинал
                    file_path.unlink(missing_ok=True)
            else:
                # Dry-run: только парсинг без сохранения
                from replays.parser.parser import Parser
                from replays.parser.extractor import ExtractorV2

                parser = Parser()
                content = file_wrapper.read()
                data = parser.parse_bytes(content)
                fields = ExtractorV2.extract_replay_fields_v2(data, file_name)

                results['success'].append({
                    'file': file_name,
                    'tank': fields.get('tank_tag', 'Unknown'),
                    'owner': 'N/A (dry-run)'
                })
                print("✅ OK (dry-run)")

        except ValidationError as e:
            error_msg = str(e)
            if "уже существует" in error_msg.lower():
                results['duplicate'].append({
                    'file': file_name,
                    'error': error_msg
                })
                print("⚠️  ДУБЛИКАТ")
            else:
                results['validation_error'].append({
                    'file': file_name,
                    'error': error_msg
                })
                print(f"❌ ОШИБКА: {error_msg}")

        except ParseError as e:
            results['parse_error'].append({
                'file': file_name,
                'error': str(e)
            })
            print(f"❌ PARSE ERROR: {e}")

        except Exception as e:
            results['other_error'].append({
                'file': file_name,
                'error': str(e)
            })
            print(f"❌ ERROR: {e}")

    # Итоговая статистика
    print("\n" + "=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print(f"Всего файлов:           {len(files)}")
    print(f"Успешно импортировано:  {len(results['success'])}")
    print(f"Дубликаты:              {len(results['duplicate'])}")
    print(f"Ошибки парсинга:        {len(results['parse_error'])}")
    print(f"Ошибки валидации:       {len(results['validation_error'])}")
    print(f"Другие ошибки:          {len(results['other_error'])}")

    # Детали ошибок
    if results['duplicate']:
        print(f"\n📋 Дубликаты ({len(results['duplicate'])}):")
        for item in results['duplicate'][:10]:
            print(f"  - {item['file']}")
        if len(results['duplicate']) > 10:
            print(f"  ... и ещё {len(results['duplicate']) - 10}")

    if results['parse_error']:
        print(f"\n❌ Ошибки парсинга ({len(results['parse_error'])}):")
        for item in results['parse_error'][:5]:
            print(f"  - {item['file']}: {item['error']}")
        if len(results['parse_error']) > 5:
            print(f"  ... и ещё {len(results['parse_error']) - 5}")

    if results['validation_error']:
        print(f"\n❌ Ошибки валидации ({len(results['validation_error'])}):")
        for item in results['validation_error'][:5]:
            print(f"  - {item['file']}: {item['error']}")
        if len(results['validation_error']) > 5:
            print(f"  ... и ещё {len(results['validation_error']) - 5}")

    if results['other_error']:
        print(f"\n❌ Другие ошибки ({len(results['other_error'])}):")
        for item in results['other_error'][:5]:
            print(f"  - {item['file']}: {item['error']}")
        if len(results['other_error']) > 5:
            print(f"  ... и ещё {len(results['other_error']) - 5}")

    if dry_run:
        print("\n💡 Для применения импорта запустите:")
        print(f"   python scripts/import_orphaned_replays.py --source {source} --apply")
        if user_id:
            print(f"   (с пользователем: --user-id {user_id})")
        if not move_to_root:
            print(f"   (без перемещения: --no-move)")

    print("=" * 80)


def main():
    """Главная функция."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Импортирует реплеи из orphaned_replays в базу данных"
    )
    parser.add_argument(
        '--source',
        required=True,
        help='Имя подпапки в orphaned_replays (например, 20250101_120000)'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Применить импорт (по умолчанию только предпросмотр)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Режим предпросмотра (по умолчанию)'
    )
    parser.add_argument(
        '--user-id',
        type=int,
        help='ID пользователя, от имени которого загружать файлы (опционально)'
    )
    parser.add_argument(
        '--no-move',
        action='store_true',
        help='НЕ перемещать успешно импортированные файлы в media'
    )

    args = parser.parse_args()

    # Если указан --apply, отключаем dry_run
    dry_run = not args.apply
    move_to_root = not args.no_move

    try:
        import_orphaned_replays(
            source=args.source,
            dry_run=dry_run,
            user_id=args.user_id,
            move_to_root=move_to_root
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
