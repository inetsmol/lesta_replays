# replays/views.py
from __future__ import annotations

import json
import logging
import mimetypes
import os
import urllib.parse
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, Http404, FileResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.encoding import escape_uri_path
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView

from wotreplay.helper.extractor import Extractor
from wotreplay.mtreplay import Replay as Rpl
from .models import Replay, Tank, Nation, Achievement

FILES_DIR = Path(settings.MEDIA_ROOT)
FILES_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


class ReplayUploadView(View):
    """
    View для загрузки файлов реплеев Мир Танков.
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

        r = Rpl(file_path)

        r.get_replay_fields()

        replay_fields = r.replay_fields

        try:
            # Извлекаем JSON данные из файла
            #
            # json_str = extract_all_json_from_mtreplay(str(file_path))
            # if not json_str.strip():
            #     raise ValueError("Файл не содержит данных реплея")
            #
            # payload = json.loads(json_str)
            #
            # # Парсим данные для создания реплея
            # replay_data = self._parse_replay_data(payload)

            # Находим или создаем танк
            # tank = self._get_or_create_tank(replay_data['vehicle_id'])
            tank = self._get_or_create_tank(replay_fields.get('tank_tag'))

            # Создаем объект реплея
            replay = Replay.objects.create(
                file_name=replay_fields.get('file_name'),
                payload=replay_fields.get('payload'),
                tank=tank,
                battle_date=replay_fields.get('battle_date'),
                map_name=replay_fields.get('map_name'),
                map_display_name=replay_fields.get('map_display_name'),
                mastery=replay_fields.get('mastery'),
                credits=replay_fields.get('credits', 0),
                xp=replay_fields.get('xp', 0),
                kills=replay_fields.get('kills', 0),
                damage=replay_fields.get('damage', 0),
                assist=replay_fields.get('assist', 0),
                block=replay_fields.get('block', 0)
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

    # --- утилиты ---
    def _getlist(self, key: str, alt: str | None = None) -> list[str]:
        """
        Вернёт объединённый список значений из GET по ключу key (+ alt, если задан).
        Убирает дубликаты, сохраняет порядок.
        """
        qd = self.request.GET
        vals = qd.getlist(key)
        if alt:
            vals += qd.getlist(alt)

        seen = set()
        out: list[str] = []
        for v in vals:
            if v in seen:
                continue
            seen.add(v)
            out.append(v)
        return out

    def _to_int_set(self, seq: list[str]) -> set[int]:
        """
        Сконвертировать список в множество int, игнорируя мусор.
        """
        out: set[int] = set()
        for v in seq:
            try:
                out.add(int(v))
            except (TypeError, ValueError):
                continue
        return out

    def _smart_set(self, seq: list[str]) -> set[int] | set[str]:
        """
        Универсальная нормализация: если все элементы — целые числа, вернёт set[int],
        иначе вернёт set[str] (обрезанные, не пустые).
        Удобно для полей, где тип может быть строковым (type, nation) или числовым.
        """
        cleaned: list[str] = []
        for v in seq:
            s = (v or "").strip()
            if s:
                cleaned.append(s)

        def _is_int(s: str) -> bool:
            return s.isdigit() or (s.startswith("-") and s[1:].isdigit())

        if cleaned and all(_is_int(s) for s in cleaned):
            return {int(s) for s in cleaned}
        return set(cleaned)

    # --- фильтры ---
    def _apply_filters(self, queryset):
        """
        Применение всех фильтров к QuerySet согласно параметрам GET.
        Работает с мультивыбором: tank, mastery, level/tier, type, nation.
        Поддерживает даты, поиск по карте и числовые диапазоны.
        """

        # Множественный выбор танков
        tank_ids = self._to_int_set(self._getlist("tank"))
        if tank_ids:
            queryset = queryset.filter(tank_id__in=tank_ids)

        # Мастерство (множественный выбор)
        mastery_vals = self._to_int_set(self._getlist("mastery"))
        if mastery_vals:
            queryset = queryset.filter(mastery__in=mastery_vals)

        # Даты боя
        if date_from := self.request.GET.get("date_from"):
            if d := parse_date(date_from):
                queryset = queryset.filter(battle_date__date__gte=d)

        if date_to := self.request.GET.get("date_to"):
            if d := parse_date(date_to):
                queryset = queryset.filter(battle_date__date__lte=d)

        # Поиск по карте
        if map_search := (self.request.GET.get("map_search") or "").strip():
            if map_search:
                queryset = queryset.filter(
                    Q(map_display_name__icontains=map_search) |
                    Q(map_name__icontains=map_search)
                )

        # Числовые диапазоны (мин/макс)
        numeric_fields = {
            "damage": "damage",
            "xp": "xp",
            "kills": "kills",
            "credits": "credits",
            "assist": "assist",
            "block": "block",
        }
        for param_prefix, field in numeric_fields.items():
            min_val = self.request.GET.get(f"{param_prefix}_min")
            if min_val not in (None, ""):
                try:
                    queryset = queryset.filter(**{f"{field}__gte": int(min_val)})
                except (TypeError, ValueError):
                    pass

            max_val = self.request.GET.get(f"{param_prefix}_max")
            if max_val not in (None, ""):
                try:
                    queryset = queryset.filter(**{f"{field}__lte": int(max_val)})
                except (TypeError, ValueError):
                    pass

        # Характеристики танка (множественный выбор)
        # level: поддерживаем alias "tier"
        levels = self._to_int_set(self._getlist("level", alt="tier"))
        if levels:
            queryset = queryset.filter(tank__level__in=levels)

        # type в БД обычно строковое поле ('lightTank', 'mediumTank', 'AT-SPG', 'SPG' и т.п.)
        types_ = self._smart_set(self._getlist("type"))
        if types_:
            queryset = queryset.filter(tank__type__in=types_)

        # nation: может быть строкой (коды) или числом — поддержим оба варианта
        nations = self._smart_set(self._getlist("nation"))
        if nations:
            queryset = queryset.filter(tank__nation__in=nations)

        # Победа/поражение (если нет явного поля is_win, оставим по прокси)
        victory_filter = (self.request.GET.get("victory") or "").strip().lower()
        if victory_filter == "win":
            queryset = queryset.filter(credits__gt=0)
        elif victory_filter == "loss":
            queryset = queryset.filter(credits__lte=0)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # выбранные значения для мультивыбора (всегда списки строк)
        selected_levels = self.request.GET.getlist('level') or self.request.GET.getlist('tier')
        selected = {
            'tank': self.request.GET.getlist('tank'),
            'mastery': self.request.GET.getlist('mastery'),
            'level': selected_levels,
            'type': self.request.GET.getlist('type'),
            'nation': self.request.GET.getlist('nation'),
            'victory': self.request.GET.get('victory', ''),  # одиночное
        }

        context.update({
            'filter_data': self._get_filter_context(),
            'params': self.request.GET,  # для одиночных полей (map_search, даты, min/max)
            'selected': selected,  # для чекбоксов/множественных полей
        })
        return context

    def _get_filter_context(self):
        return {
            'tanks': (Tank.objects
                      .only('id','name','nation','level','type')
                      .order_by('nation','level','type','name')),
            'nations': getattr(Nation, 'choices', ()),  # если это Django Choices
            'levels': range(1, 12),                      # 1..11
            'mastery_choices': [('4','Мастер'),('3','1 степень'),('2','2 степень'),('1','3 степень')],
            # если тип — числа 1..5:
            'type_choices': [('1','Лёгкий танк'),('2','Средний танк'),('3','Тяжёлый танк'),
                             ('4','ПТ-САУ'),('5','САУ')],
        }


class ReplayDetailView(DetailView):
    """
    Детальная страница реплея с полным анализом данных боя.
    """
    model = Replay
    template_name = 'replays/detail.html'
    context_object_name = 'replay'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Парсим данные реплея
            replay_data = self.object.payload

            # === ДОСТИЖЕНИЯ ===
            achievements_ids = Extractor.get_achievements(replay_data)
            if achievements_ids:
                ach_nonbattle, ach_battle = Extractor.split_achievements_by_section(achievements_ids)

                print(f"ach_nonbattle {ach_nonbattle}")
                print(f"ach_battle {ach_battle}")

                context['achievements_nonbattle'] = ach_nonbattle
                context['achievements_battle'] = ach_battle

                # мастерство — как и было
                m = int(self.object.mastery or 0)
                label_map = {
                    4: "100% — Мастер",
                    3: "95% — 1 степень",
                    2: "80% — 2 степень",
                    1: "50% — 3 степень",
                }
                context['has_mastery'] = m > 0
                context['mastery'] = m
                context['mastery_label'] = label_map.get(m, "")
                context['mastery_image'] = f"style/images/wot/achievement/markOfMastery{m}.png" if m else ""

                # сколько значков показать в «бейджах»
                context['achievements_count_in_badges'] = ach_nonbattle.count() + (1 if m > 0 else 0)
                context['achievements_battle_count'] = ach_battle.count()

            else:
                context['achievements_nonbattle'] = Achievement.objects.none()
                context['achievements_battle'] = Achievement.objects.none()
                context['achievements_count_in_badges'] = 0

            # кладём как вложенный словарь, чтобы в шаблоне обращаться: {{ details.playerName }}
            context['details'] = Extractor.get_details_data(replay_data)

            context["interactions"] = Extractor.get_player_interactions(replay_data)

            interaction_rows = Extractor.build_interaction_rows(replay_data)
            context["interaction_rows"] = interaction_rows

            context["interactions_summary"] = Extractor.build_interactions_summary(interaction_rows)

            context['death_reason_text'] = Extractor.get_death_text(replay_data)

            context['income'] = Extractor.build_income_summary(replay_data)

            context["battle_type_label"] = Extractor.get_battle_type_label(replay_data)

            context["battle_outcome"] = Extractor.get_battle_outcome(replay_data)

            context['team_results'] = Extractor.get_team_results(replay_data)

        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Ошибка парсинга реплея {self.object.id}: {str(e)}")
            context['parse_error'] = f"Ошибка обработки данных реплея: {str(e)}"

        return context

    def _get_result_class(self, result: str) -> str:
        """Возвращает CSS класс для результата боя"""
        return {
            'victory': 'victory',
            'defeat': 'defeat',
            'draw': 'draw'
        }.get(result, 'unknown')

    def _get_survival_status(self, death_reason: int) -> dict:
        """Определяет статус выживания"""
        if death_reason == -1:
            return {'status': 'survived', 'text': 'Выжил', 'class': 'survived'}
        else:
            return {'status': 'died', 'text': 'Погиб', 'class': 'died'}

    def _calculate_hit_efficiency(self, data: dict) -> dict:
        """Вычисляет эффективность стрельбы"""
        shots = data.get('shots', 0)
        hits = data.get('direct_hits', 0)
        piercings = data.get('piercings', 0)

        return {
            'hit_rate': data.get('hit_rate', 0),
            'penetration_rate': round((piercings / hits * 100), 2) if hits > 0 else 0,
            'shots_per_hit': round(shots / hits, 2) if hits > 0 else 0,
        }

    def _calculate_damage_efficiency(self, data: dict) -> dict:
        """Вычисляет эффективность урона"""
        damage = data.get('damage_dealt', 0)
        shots = data.get('shots', 0)
        max_hp = data.get('max_health', 1)

        return {
            'damage_per_shot': round(damage / shots, 1) if shots > 0 else 0,
            'damage_ratio': data['battle_performance']['damage_ratio'],
            'assist_ratio': round(data.get('total_assist', 0) / damage * 100, 1) if damage > 0 else 0,
        }

    def _calculate_armor_efficiency(self, data: dict) -> dict:
        """Вычисляет эффективность брони"""
        potential = data.get('potential_damage_received', 0)
        received = data.get('damage_received', 0)
        blocked = data.get('total_blocked_damage', 0)

        return {
            'damage_blocked': blocked,
            'armor_use_ratio': round(blocked / potential * 100, 1) if potential > 0 else 0,
            'ricochets': data.get('ricochets_received', 0),
            'bounces': data.get('bounces_received', 0),
        }

    def _prepare_enemy_list(self, enemy_stats: dict) -> list:
        """Подготавливает список противников для отображения"""
        enemies = []
        for enemy_id, stats in enemy_stats.items():
            if stats['damage_dealt'] > 0 or stats['target_kills'] > 0:
                enemy_info = stats.get('enemy_vehicle_info', {})
                enemies.append({
                    'id': enemy_id,
                    'damage': stats['damage_dealt'],
                    'hits': stats['direct_hits'],
                    'piercings': stats['piercings'],
                    'kills': stats['target_kills'],
                    'crits': stats['crits_total'],
                    'is_killed': enemy_info.get('is_dead', False) if enemy_info else False,
                    'max_hp': enemy_info.get('max_health', 0) if enemy_info else 0,
                })
        return sorted(enemies, key=lambda x: x['damage'], reverse=True)

    def _calculate_performance_rating(self, data: dict) -> dict:
        """Вычисляет общую оценку эффективности с готовыми процентами"""
        damage_rating = min(data.get('damage_dealt', 0) / 1000, 5.0)
        survival_rating = 1.0 if data.get('survival_status') == -1 else 0.0
        assist_rating = min(data.get('total_assist', 0) / 500, 2.0)
        armor_rating = min(data.get('total_blocked_damage', 0) / 1000, 2.0)

        total_rating = damage_rating + survival_rating + assist_rating + armor_rating

        return {
            'total': round(total_rating, 1),
            'max': 10.0,
            'percentage': round(total_rating / 10.0 * 100, 1),
            'components': {
                'damage': {
                    'value': round(damage_rating, 1),
                    'max': 5.0,
                    'percentage': round(damage_rating / 5.0 * 100, 1),
                },
                'survival': {
                    'value': round(survival_rating, 1),
                    'max': 1.0,
                    'percentage': round(survival_rating * 100, 1),
                },
                'assist': {
                    'value': round(assist_rating, 1),
                    'max': 2.0,
                    'percentage': round(assist_rating / 2.0 * 100, 1),
                },
                'armor': {
                    'value': round(armor_rating, 1),
                    'max': 2.0,
                    'percentage': round(armor_rating / 2.0 * 100, 1),
                },
            }
        }


class ReplayDownloadView(View):
    """
    View для скачивания файлов реплеев World of Tanks.
    Возвращает .mtreplay файл по ID реплея с оптимизацией для больших файлов.
    """

    # Максимальный размер файла для скачивания (100MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024

    # Размер чанка для потокового чтения (1MB)
    CHUNK_SIZE = 1024 * 1024

    def get(self, request, pk):
        """
        Обрабатывает GET запрос для скачивания реплея.

        Args:
            request: HTTP запрос
            pk: ID реплея для скачивания

        Returns:
            HttpResponse с файлом или Http404
        """
        try:
            # Получаем объект реплея
            replay = self._get_replay_object(pk)

            # Формируем путь к файлу
            file_path = self._get_file_path(replay.file_name)

            # Валидация безопасности и существования
            self._validate_file_security(file_path)
            self._validate_file_exists(file_path)

            # Возвращаем файл для скачивания
            return self._create_optimized_file_response(file_path, replay.file_name)

        except Replay.DoesNotExist:
            logger.warning(f"Попытка скачать несуществующий реплей: {pk}")
            raise Http404("Реплей не найден")
        except FileNotFoundError as e:
            logger.error(f"Файл реплея не найден для ID {pk}: {str(e)}")
            raise Http404("Файл реплея не найден")
        except PermissionError:
            logger.error(f"Нет прав доступа к файлу реплея ID {pk}")
            raise Http404("Нет доступа к файлу")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при скачивании реплея {pk}: {str(e)}")
            raise Http404("Ошибка при обработке файла")

    def _get_replay_object(self, pk):
        """
        Получает объект реплея по ID с оптимизированным запросом.

        Args:
            pk: ID реплея

        Returns:
            Replay: объект реплея

        Raises:
            Replay.DoesNotExist: если реплей не найден
        """
        try:
            # Оптимизированный запрос - нам нужно только file_name
            return Replay.objects.only('file_name').get(pk=pk)
        except Replay.DoesNotExist:
            raise

    def _get_file_path(self, file_name):
        """
        Формирует полный путь к файлу реплея.

        Args:
            file_name: имя файла реплея

        Returns:
            Path: полный путь к файлу
        """
        return Path(settings.MEDIA_ROOT) / file_name

    def _validate_file_security(self, file_path):
        """
        Проверяет безопасность пути к файлу (защита от path traversal).

        Args:
            file_path: путь к файлу

        Raises:
            PermissionError: если путь небезопасен
        """
        media_root = Path(settings.MEDIA_ROOT).resolve()
        resolved_file_path = file_path.resolve()

        # Проверяем, что файл находится в MEDIA_ROOT
        if not str(resolved_file_path).startswith(str(media_root)):
            logger.warning(f"Попытка доступа к файлу вне MEDIA_ROOT: {resolved_file_path}")
            raise PermissionError("Недопустимый путь к файлу")

    def _validate_file_exists(self, file_path):
        """
        Проверяет существование файла на диске и его размер.

        Args:
            file_path: путь к файлу

        Raises:
            FileNotFoundError: если файл не найден или слишком большой
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        if not file_path.is_file():
            raise FileNotFoundError(f"Путь не является файлом: {file_path}")

        # Проверяем размер файла
        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            logger.warning(f"Попытка скачать слишком большой файл: {file_path} ({file_size} bytes)")
            raise FileNotFoundError("Файл слишком большой для скачивания")

    def _create_optimized_file_response(self, file_path, file_name):
        """
        Создает оптимизированный HTTP ответ с файлом для скачивания.
        Использует потоковый ответ для больших файлов.

        Args:
            file_path: путь к файлу
            file_name: оригинальное имя файла

        Returns:
            HttpResponse или StreamingHttpResponse: ответ с файлом
        """
        try:
            file_size = file_path.stat().st_size
            content_type = self._get_content_type(file_name)

            # Для файлов больше 5MB используем потоковый ответ
            if file_size > 5 * 1024 * 1024:
                response = self._create_streaming_response(file_path, content_type)
            else:
                response = self._create_regular_response(file_path, content_type)

            # Устанавливаем общие заголовки
            safe_filename = escape_uri_path(file_name)
            response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
            response['Content-Length'] = file_size
            response['Cache-Control'] = 'public, max-age=3600'  # Кэш на 1 час

            logger.info(f"Файл реплея отправлен: {file_name} (размер: {file_size} bytes)")
            return response

        except IOError as e:
            logger.error(f"Ошибка чтения файла {file_path}: {str(e)}")
            raise FileNotFoundError("Ошибка чтения файла")

    def _create_streaming_response(self, file_path, content_type):
        """
        Создает потоковый HTTP ответ для больших файлов.

        Args:
            file_path: путь к файлу
            content_type: MIME-тип

        Returns:
            StreamingHttpResponse: потоковый ответ
        """

        def file_iterator():
            with open(file_path, 'rb') as file:
                while True:
                    chunk = file.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        return StreamingHttpResponse(
            file_iterator(),
            content_type=content_type
        )

    def _create_regular_response(self, file_path, content_type):
        """
        Создает обычный HTTP ответ для небольших файлов.

        Args:
            file_path: путь к файлу
            content_type: MIME-тип

        Returns:
            HttpResponse: ответ с файлом
        """
        with open(file_path, 'rb') as file:
            file_content = file.read()

        return HttpResponse(
            file_content,
            content_type=content_type
        )

    def _get_content_type(self, file_name):
        """
        Определяет MIME-тип файла.

        Args:
            file_name: имя файла

        Returns:
            str: MIME-тип
        """
        # Для .mtreplay файлов используем специальный тип
        if file_name.lower().endswith('.mtreplay'):
            return 'application/octet-stream'

        # Для других файлов пытаемся определить автоматически
        content_type, _ = mimetypes.guess_type(file_name)
        return content_type or 'application/octet-stream'


class AboutView(TemplateView):
    template_name = "about.html"