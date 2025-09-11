from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import ListView

from .models import Replay, Tank, Nation
from .utils import extract_all_json_from_mtreplay

FILES_DIR = Path(settings.MEDIA_ROOT)
FILES_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


class ReplayUploadView(View):
    """
    View для загрузки файлов реплеев World of Tanks.
    Принимает .mtreplay файлы, извлекает данные и создает объект Replay.
    """

    def post(self, request):
        try:
            # Получаем файл из запроса
            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                return self._error_response("Файл не выбран")

            # Валидация файла
            validation_error = self._validate_file(uploaded_file)
            if validation_error:
                return validation_error

            # Сохраняем файл и создаем реплей
            with transaction.atomic():
                replay = self._process_replay_file(uploaded_file)

            messages.success(request, f"Реплей успешно загружен: {replay.file_name}")

            # Для AJAX запросов возвращаем JSON с редиректом
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f"Реплей успешно загружен: {replay.file_name}",
                    'redirect_url': reverse('replay_detail', kwargs={'pk': replay.id})
                })

            return redirect('replay_detail', pk=replay.id)

        except ValidationError as e:
            # ValidationError может содержать список ошибок или строку
            error_message = self._extract_error_message(e)
            logger.warning(f"Ошибка валидации реплея: {error_message}")
            return self._error_response(error_message)

        except Exception as e:
            error_message = "Произошла ошибка при обработке файла"
            logger.error(f"Ошибка загрузки реплея: {str(e)}")
            return self._error_response(error_message)

    def _extract_error_message(self, validation_error):
        """Извлекает читаемое сообщение об ошибке из ValidationError"""
        if hasattr(validation_error, 'message_dict'):
            # Ошибки формы
            messages = []
            for field, errors in validation_error.message_dict.items():
                if isinstance(errors, list):
                    messages.extend(errors)
                else:
                    messages.append(str(errors))
            return '; '.join(messages)
        elif hasattr(validation_error, 'messages'):
            # Список сообщений
            if isinstance(validation_error.messages, list):
                return '; '.join(validation_error.messages)
            else:
                return str(validation_error.messages)
        else:
            # Простое сообщение
            return str(validation_error)

    def _error_response(self, message):
        """Возвращает ошибку в зависимости от типа запроса"""
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': message,
                'redirect_url': reverse('replay_list')
            }, status=400)
        else:
            messages.error(self.request, message)
            return redirect('replay_list')

    def _validate_file(self, uploaded_file):
        """Валидация загружаемого файла"""
        # Проверка расширения
        if not uploaded_file.name.lower().endswith('.mtreplay'):
            return self._error_response("Неподдерживаемый формат файла. Разрешены только .mtreplay файлы")

        # Проверка размера (50MB)
        max_size = 50 * 1024 * 1024
        if uploaded_file.size > max_size:
            return self._error_response("Файл слишком большой. Максимальный размер: 50MB")

        # Проверка уникальности имени файла
        if Replay.objects.filter(file_name=uploaded_file.name).exists():
            return self._error_response("Файл с таким именем уже загружен")

        return None

    def _process_replay_file(self, uploaded_file):
        """
        Обрабатывает загруженный файл реплея:
        1. Сохраняет файл в MEDIA_ROOT
        2. Извлекает JSON данные
        3. Парсит данные и создает объект Replay
        """
        # Сохраняем файл
        file_path = self._save_file(uploaded_file)

        try:
            # Извлекаем JSON данные из файла
            json_str = extract_all_json_from_mtreplay(str(file_path))
            if not json_str.strip():
                raise ValueError("Файл не содержит данных реплея")

            payload = json.loads(json_str)

            # Парсим данные для создания реплея
            replay_data = self._parse_replay_data(payload)

            # Находим или создаем танк
            tank = self._get_or_create_tank(replay_data['vehicle_id'])

            # Создаем объект реплея
            replay = Replay.objects.create(
                file_name=uploaded_file.name,
                payload=payload,
                tank=tank,
                battle_date=replay_data.get('battle_date'),
                map_name=replay_data.get('map_name'),
                map_display_name=replay_data.get('map_display_name'),
                mastery=replay_data.get('mastery'),
                credits=replay_data.get('credits', 0),
                xp=replay_data.get('xp', 0),
                kills=replay_data.get('kills', 0),
                damage=replay_data.get('damage', 0),
                assist=replay_data.get('assist', 0),
                block=replay_data.get('block', 0)
            )

            logger.info(f"Реплей создан: {replay.id} - {uploaded_file.name}")
            return replay

        except (json.JSONDecodeError, ValueError) as e:
            # Удаляем файл при ошибке парсинга
            file_path.unlink(missing_ok=True)
            raise ValidationError(f"Ошибка обработки файла реплея: {str(e)}")
        except Exception as e:
            # Удаляем файл при любой другой ошибке
            file_path.unlink(missing_ok=True)
            raise

    def _save_file(self, uploaded_file):
        """Сохраняет загруженный файл в MEDIA_ROOT"""
        from django.conf import settings

        files_dir = Path(settings.MEDIA_ROOT)
        files_dir.mkdir(parents=True, exist_ok=True)

        file_path = files_dir / uploaded_file.name

        # Проверяем, что файл с таким именем не существует
        if file_path.exists():
            raise ValidationError("Файл с таким именем уже существует")

        # Сохраняем файл
        with open(file_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        return file_path

    def _parse_replay_data(self, payload):
        """
        Парсит JSON данные реплея и извлекает нужные поля.
        Основано на структуре данных из закомментированной функции _extract_wot_brief_for_list
        """
        # Извлекаем ID техники (убираем префикс до '-')
        player_vehicle = payload.get("playerVehicle", "")
        if "-" in player_vehicle:
            vehicle_id = player_vehicle.split("-", 1)[1]
        else:
            vehicle_id = player_vehicle

        # Извлекаем статистику из personal секции
        personal = payload.get("personal", {})
        vehicle_stats = {}

        # Ищем числовой ключ техники в personal
        for key, value in personal.items():
            if isinstance(key, str) and key.isdigit():
                vehicle_stats = value
                break

        # Парсим дату боя
        battle_date = None
        date_str = payload.get("dateTime")
        if date_str:
            try:
                # Формат: '25.08.2025 15:57:56'
                battle_date = datetime.strptime(date_str, '%d.%m.%Y %H:%M:%S')
            except ValueError:
                logger.warning(f"Не удалось распарсить дату: {date_str}")

        # Собираем ассист из различных компонентов
        assist = (
                vehicle_stats.get("damageAssistedTrack", 0) +
                vehicle_stats.get("damageAssistedRadio", 0) +
                vehicle_stats.get("damageAssistedStun", 0) +
                vehicle_stats.get("damageAssistedSmoke", 0) +
                vehicle_stats.get("damageAssistedInspire", 0)
        )

        return {
            'vehicle_id': vehicle_id,
            'battle_date': battle_date,
            'map_name': payload.get('mapName'),
            'map_display_name': payload.get('mapDisplayName'),
            'mastery': vehicle_stats.get('markOfMastery'),
            'credits': vehicle_stats.get('credits', 0),
            'xp': vehicle_stats.get('xp', 0),
            'kills': vehicle_stats.get('kills', 0),
            'damage': vehicle_stats.get('damageDealt', 0),
            'assist': assist,
            'block': vehicle_stats.get('damageBlockedByArmor', 0)
        }

    def _get_or_create_tank(self, vehicle_id):
        """
        Находит существующий танк или создает заглушку если танк не найден
        """
        if not vehicle_id:
            return None

        try:
            return Tank.objects.get(vehicleId=vehicle_id)
        except Tank.DoesNotExist:
            logger.warning(f"Танк с ID {vehicle_id} не найден в базе, создаем заглушку")
            # Создаем заглушку для неизвестного танка
            return Tank.objects.create(
                vehicleId=vehicle_id,
                name=f"Неизвестный танк ({vehicle_id})",
                level=1,
                type="unknown"
            )


class ReplayListView(ListView):
    """
    Представление списка реплеев с пагинацией и фильтрацией.
    """
    model = Replay
    template_name = 'replays/list.html'
    context_object_name = 'items'
    paginate_by = 10

    def get_queryset(self):
        """
        Получение отфильтрованного QuerySet с применением фильтров.
        """
        queryset = Replay.objects.select_related('tank').order_by('-battle_date', '-created_at')

        # Применяем фильтры
        queryset = self._apply_filters(queryset)

        return queryset

    def _apply_filters(self, queryset):
        """
        Применение всех фильтров к QuerySet.
        Следует принципу Single Responsibility.
        """
        # Фильтр по танку
        if tank_id := self.request.GET.get('tank'):
            try:
                queryset = queryset.filter(tank_id=int(tank_id))
            except (ValueError, TypeError):
                pass

        # Фильтр по знаку мастерства
        if mastery := self.request.GET.get('mastery'):
            try:
                queryset = queryset.filter(mastery=int(mastery))
            except (ValueError, TypeError):
                pass

        # Фильтры по дате боя
        if date_from := self.request.GET.get('date_from'):
            if parsed_date := parse_date(date_from):
                queryset = queryset.filter(battle_date__date__gte=parsed_date)

        if date_to := self.request.GET.get('date_to'):
            if parsed_date := parse_date(date_to):
                queryset = queryset.filter(battle_date__date__lte=parsed_date)

        # Фильтр по карте (поиск по названию)
        if map_search := self.request.GET.get('map_search'):
            queryset = queryset.filter(
                Q(map_display_name__icontains=map_search) |
                Q(map_name__icontains=map_search)
            )

        # Числовые фильтры (минимум/максимум)
        numeric_fields = {
            'damage': 'damage',
            'xp': 'xp',
            'kills': 'kills',
            'credits': 'credits',
            'assist': 'assist',
            'block': 'block'
        }

        for param_prefix, field_name in numeric_fields.items():
            # Минимальное значение
            if min_val := self.request.GET.get(f'{param_prefix}_min'):
                try:
                    queryset = queryset.filter(**{f'{field_name}__gte': int(min_val)})
                except (ValueError, TypeError):
                    pass

            # Максимальное значение
            if max_val := self.request.GET.get(f'{param_prefix}_max'):
                try:
                    queryset = queryset.filter(**{f'{field_name}__lte': int(max_val)})
                except (ValueError, TypeError):
                    pass

        # Фильтры по характеристикам танка
        if level := self.request.GET.get('level'):
            try:
                queryset = queryset.filter(tank__level=int(level))
            except (ValueError, TypeError):
                pass

        if tank_type := self.request.GET.get('type'):
            queryset = queryset.filter(tank__type=tank_type)

        if nation := self.request.GET.get('nation'):
            queryset = queryset.filter(tank__nation=nation)

        # Фильтр только побед/поражений
        victory_filter = self.request.GET.get('victory')
        if victory_filter == 'win':
            queryset = queryset.filter(credits__gt=0)
        elif victory_filter == 'loss':
            queryset = queryset.filter(credits__lte=0)

        return queryset

    def get_context_data(self, **kwargs):
        """
        Добавление контекста для фильтров и пагинации.
        """
        context = super().get_context_data(**kwargs)

        # Добавляем данные для форм фильтров
        context.update({
            'filter_data': self._get_filter_context(),
            'current_filters': dict(self.request.GET.items()),
        })

        return context

    def _get_filter_context(self):
        """
        Получение данных для выпадающих списков фильтров.
        """
        return {
            'tanks': Tank.objects.order_by('level', 'name'),
            'nations': Nation.choices,
            'tank_types': Tank.objects.values_list('type', flat=True).distinct().order_by('type'),
            'levels': range(1, 11),  # Уровни танков 1-10
            'mastery_choices': [(i, f'Знак {i}') for i in range(5)],  # 0-4
        }


# --- пример, как быстро превратить заглушку в настоящую детальную страницу ---
def replay_detail(request, pk: int):
    """
    Реальная детальная страница (пример).
    """
    replay = get_object_or_404(Replay, pk=pk)
    # Можно переиспользовать краткий экстрактор:
    # data = _extract_wot_brief_for_list(replay.payload)
    return render(request, "replays/detail.html", {"replay": replay})