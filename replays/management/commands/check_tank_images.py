"""
Django management команда для проверки наличия изображений танков.

Проверяет, что для каждого танка в БД существует соответствующее изображение
в static/style/images/wot/shop/vehicles/180x135/

Использование:
    python manage.py check_tank_images
"""

import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Проверяет наличие изображений для всех танков в БД.
    Выводит отчет и сохраняет данные об отсутствующих изображениях в JSON файл.
    """

    help = 'Проверяет наличие изображений танков в static и записывает отсутствующие в JSON'

    def add_arguments(self, parser):
        """Добавление аргументов командной строки."""
        parser.add_argument(
            '--output',
            type=str,
            default='missing_tank_images.json',
            help='Имя выходного JSON файла (по умолчанию: missing_tank_images.json)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Выводить информацию о всех танках (не только отсутствующих)'
        )

    def handle(self, *args, **options):
        """Основная логика команды."""
        from replays.models import Tank

        output_file = options['output']
        verbose = options['verbose']

        # Путь к директории с изображениями танков
        images_dir = Path(settings.BASE_DIR) / 'static' / 'style' / 'images' / 'wot' / 'shop' / 'vehicles' / '180x135'

        if not images_dir.exists():
            self.stdout.write(
                self.style.ERROR(f'[ОШИБКА] Директория с изображениями не найдена: {images_dir}')
            )
            return

        # Получаем все танки из БД
        tanks = Tank.objects.all().order_by('nation', 'level', 'type')
        total_tanks = tanks.count()

        if total_tanks == 0:
            self.stdout.write(
                self.style.WARNING('[!] В БД нет танков!')
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f'\nНачинаем проверку {total_tanks} танков...')
        )
        self.stdout.write('=' * 100)

        # Счетчики
        found_count = 0
        missing_count = 0

        # Список отсутствующих изображений
        missing_images = []

        for tank in tanks:
            # Преобразуем vehicleId в имя файла
            # Формат: R232_IS-7W -> R232_IS-7W.png
            # Или: usa:A01_T1_Cunningham -> A01_T1_Cunningham.png

            # Убираем префикс нации, если есть (формат "nation:code")
            vehicle_code = tank.vehicleId.split(':', 1)[-1]

            # Формируем имя файла
            image_filename = f"{vehicle_code}.png"
            image_path = images_dir / image_filename

            # Проверяем существование файла
            exists = image_path.exists()

            if exists:
                found_count += 1
                if verbose:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[OK] {tank.vehicleId:<35} -> {image_filename:<40} [НАЙДЕНО]"
                        )
                    )
            else:
                missing_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"[!] {tank.vehicleId:<35} -> {image_filename:<40} [ОТСУТСТВУЕТ]"
                    )
                )

                # Добавляем в список отсутствующих
                missing_images.append({
                    'vehicleId': tank.vehicleId,
                    'name': tank.name,
                    'level': tank.level,
                    'type': tank.type,
                    'nation': tank.nation,
                    'expected_filename': image_filename,
                    'expected_path': f"static/style/images/wot/shop/vehicles/180x135/{image_filename}"
                })

        # Итоговая статистика
        self.stdout.write('=' * 100)
        self.stdout.write(
            self.style.SUCCESS(f'\nСтатистика:')
        )
        self.stdout.write(f'   Всего танков: {total_tanks}')
        self.stdout.write(
            self.style.SUCCESS(f'   [OK] Изображения найдены: {found_count} ({found_count * 100 / total_tanks:.1f}%)')
        )

        if missing_count > 0:
            self.stdout.write(
                self.style.WARNING(f'   [!] Изображения отсутствуют: {missing_count} ({missing_count * 100 / total_tanks:.1f}%)')
            )

            # Сохраняем отсутствующие изображения в JSON
            output_path = Path(settings.BASE_DIR) / output_file

            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(missing_images, f, ensure_ascii=False, indent=2)

                self.stdout.write(
                    self.style.SUCCESS(f'\nДанные об отсутствующих изображениях сохранены в: {output_path}')
                )
                self.stdout.write(
                    f'   Записей в файле: {len(missing_images)}'
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'\n[ОШИБКА] Ошибка при сохранении JSON: {str(e)}')
                )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\nВсе изображения найдены!')
            )

        self.stdout.write('')
