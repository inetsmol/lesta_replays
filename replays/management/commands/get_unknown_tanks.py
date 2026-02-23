"""
Django management команда для получения и обновления неизвестных танков.

Использование:
    python manage.py get_unknown_tanks
"""

from django.core.management.base import BaseCommand
from django.db.models import Q


class Command(BaseCommand):
    """
    Получает список vehicleId записей с "Неизвестный танк" и обновляет их данные.
    """

    help = 'Находит и обновляет записи с "Неизвестный танк" в названии'

    def _find_matching_tank(self, vehicle_id: str):
        """
        Ищет танк в базе данных по вхождению vehicleId без префикса нации.

        Args:
            vehicle_id: ID танка без префикса (например, 'PzI_ausf_C', 'E-25')

        Returns:
            vehicleId найденного танка с префиксом или None
        """
        from replays.models import Tank

        # Убираем возможные суффиксы
        clean_id = vehicle_id
        suffixes = ['_hb25_Boss', '_hb25_Elite', '_hb25', '_WT_bot', '_NewOnBoarding', '_Halloween']
        for suffix in suffixes:
            if clean_id.endswith(suffix):
                clean_id = clean_id[:-len(suffix)]
                break

        # Ищем танки где vehicleId заканчивается на наш ID
        # Например: для 'E-25' найдем 'G48_E-25'
        matching_tanks = Tank.objects.filter(
            ~Q(name__contains='Неизвестный танк'),
            vehicleId__endswith=clean_id
        ).exclude(
            name__contains='Неизвестный танк'
        )

        if matching_tanks.exists():
            # Берём первое совпадение
            match = matching_tanks.first()
            return match.vehicleId

        return None

    def _process_vehicle_id(self, vehicle_id: str) -> str:
        """
        Обрабатывает vehicle_id: удаляет суффиксы и преобразует префиксы.

        Args:
            vehicle_id: Исходный ID танка

        Returns:
            Обработанный ID для поиска
        """
        vehicle_id_for_search = vehicle_id

        # Убираем суффиксы
        if vehicle_id_for_search.endswith('_hb25_Boss'):
            vehicle_id_for_search = vehicle_id_for_search[:-10]  # Убираем _hb25_Boss
        elif vehicle_id_for_search.endswith('_hb25_Elite'):
            vehicle_id_for_search = vehicle_id_for_search[:-11]  # Убираем _hb25_Elite
        elif vehicle_id_for_search.endswith('_hb25'):
            vehicle_id_for_search = vehicle_id_for_search[:-5]  # Убираем _hb25
        elif vehicle_id_for_search.endswith('_WT_bot'):
            vehicle_id_for_search = vehicle_id_for_search[:-7]  # Убираем _WT_bot
        elif vehicle_id_for_search.endswith('_NewOnBoarding'):
            vehicle_id_for_search = vehicle_id_for_search[:-14]  # Убираем _NewOnBoarding
        elif vehicle_id_for_search.endswith('_Halloween'):
            vehicle_id_for_search = vehicle_id_for_search[:-10]  # Убираем _Halloween

        # Обрабатываем префиксы в формате Letter+4digits (например, F1038, G1134)
        # Работает как для "nation:code" так и для "code" без префикса nation
        tank_code = vehicle_id_for_search.split(':', 1)[-1]  # Берём код после : или всю строку

        # Если код начинается с буквы и 4 цифр
        if len(tank_code) >= 5 and tank_code[0].isalpha() and tank_code[1:5].isdigit():
            letter = tank_code[0]
            numbers = tank_code[1:5]
            rest = tank_code[5:]

            # Убираем первую цифру '1' и '0' (F1038 -> F38, G1134 -> G134)
            if numbers.startswith('10'):
                # F1038 -> F38
                new_numbers = numbers[2:]
            elif numbers.startswith('1'):
                # G1134 -> G134
                new_numbers = numbers[1:]
            else:
                new_numbers = numbers

            new_tank_code = f"{letter}{new_numbers}{rest}"

            # Заменяем код в исходной строке
            if ':' in vehicle_id_for_search:
                nation = vehicle_id_for_search.split(':', 1)[0]
                vehicle_id_for_search = f"{nation}:{new_tank_code}"
            else:
                vehicle_id_for_search = new_tank_code

        return vehicle_id_for_search

    def handle(self, *args, **options):
        """Основная логика команды."""
        from replays.models import Tank
        from tools.tank_parser import get_tank_info

        # Получаем все записи где name содержит "Неизвестный танк"
        unknown_tanks = Tank.objects.filter(name__contains='Неизвестный танк')

        total = unknown_tanks.count()

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ Неизвестные танки не найдены!')

            )
            return

        self.stdout.write(
            self.style.WARNING(f'\n🔍 Найдено {total} неизвестных танков')
        )
        self.stdout.write('=' * 80)

        updated_count = 0
        skipped_count = 0
        error_count = 0

        for tank in unknown_tanks:
            try:
                vehicle_id_for_search = tank.vehicleId

                # Сначала пробуем найти совпадение в базе
                matched_vehicle_id = self._find_matching_tank(vehicle_id_for_search)

                if matched_vehicle_id:
                    self.stdout.write(
                        f"🔎 {tank.vehicleId:<30} -> Найдено совпадение: {matched_vehicle_id}"
                    )
                    vehicle_id_for_search = matched_vehicle_id
                else:
                    # Если не нашли - применяем старую логику обработки
                    vehicle_id_for_search = self._process_vehicle_id(vehicle_id_for_search)

                # Получаем информацию о танке
                tank_info = get_tank_info(vehicle_id_for_search)

                # КРИТИЧЕСКИ ВАЖНО: Проверяем что ВСЕ данные присутствуют
                required_fields = ['level', 'type', 'tank_name', 'tank_nation']
                missing_fields = []

                for field in required_fields:
                    if field not in tank_info or tank_info[field] is None:
                        missing_fields.append(field)

                # Если хотя бы одно поле отсутствует - пропускаем танк
                if missing_fields:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠️  {tank.vehicleId:<30} -> Пропущен (нет данных: {', '.join(missing_fields)})"
                        )
                    )
                    continue

                # Дополнительная валидация данных
                if not isinstance(tank_info['level'], int) or tank_info['level'] < 1:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠️  {tank.vehicleId:<30} -> Пропущен (некорректный level: {tank_info['level']})"
                        )
                    )
                    continue

                if not tank_info['type'] or not tank_info['tank_name']:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠️  {tank.vehicleId:<30} -> Пропущен (пустое название или тип)"
                        )
                    )
                    continue

                # Все проверки пройдены - обновляем данные
                tank.name = tank_info['tank_name']
                tank.level = tank_info['level']
                tank.type = tank_info['type']
                tank.nation = tank_info['tank_nation']
                tank.save()

                updated_count += 1

                self.stdout.write(
                    f"✅ {tank.vehicleId:<30} -> {tank_info['tank_name']:<20} "
                    f"(Lvl {tank_info['level']}, {tank_info['type']}, {tank_info['tank_nation']})"
                )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"❌ {tank.vehicleId:<30} -> Ошибка: {str(e)}"
                    )
                )

        # Итоговая статистика
        self.stdout.write('=' * 80)
        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Обновлено: {updated_count} из {total}')
        )

        if skipped_count > 0:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Пропущено: {skipped_count} (неполные данные)')
            )

        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'❌ Ошибок: {error_count}')
            )
