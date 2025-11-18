# replays/views.py
from __future__ import annotations

import logging
import mimetypes
import os
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, F, Count, OuterRef, Subquery, IntegerField, CharField, Value, FloatField
from django.db.models.functions import Coalesce, Cast
from django.http import JsonResponse, Http404, HttpResponse, StreamingHttpResponse, HttpRequest
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.encoding import escape_uri_path
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView

from django_comments.models import Comment

from .error_handlers import ReplayErrorHandler
from .models import Replay, Tank, Nation, Achievement
from .parser.extractor import ExtractorV2
from .services import ReplayProcessingService
from .validators import BatchUploadValidator, ReplayFileValidator

FILES_DIR = Path(settings.MEDIA_ROOT)
FILES_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def health(request):
    return HttpResponse("OK")


class ReplayBatchUploadView(LoginRequiredMixin, View):
    """
    Пакетная загрузка .mtreplay файлов.
    Принимает несколько файлов, валидирует и создаёт Replay по каждому.
    Требует авторизации пользователя.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.replay_service = ReplayProcessingService()
        self.error_handler = ReplayErrorHandler()

    def handle_no_permission(self):
        """Переопределяем обработку неавторизованного доступа для AJAX запросов."""
        request = getattr(self, 'request', None)
        if request and self._is_ajax_request(request):
            return JsonResponse({
                "success": False,
                "error": "Для загрузки реплеев необходимо авторизоваться",
                "redirect_url": f"{settings.LOGIN_URL}?next={request.path}"
            }, status=403)
        return super().handle_no_permission()

    @staticmethod
    def _is_ajax_request(request: HttpRequest) -> bool:
        """Проверяет, является ли запрос AJAX."""
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def post(self, request: HttpRequest):
        """Обрабатывает POST запрос с файлами реплеев."""
        files = request.FILES.getlist('files') or []
        descriptions = request.POST.getlist('descriptions')
        user = request.user if request.user.is_authenticated else None

        # Валидация пакета файлов
        if batch_error := BatchUploadValidator.validate_batch(files):
            return self._error_response(request, batch_error)

        # Обработка файлов
        results = self._process_files(files, descriptions, user)

        # Формирование ответа
        return self._build_response(request, results, len(files))

    def _process_files(self, files: list, descriptions: list, user) -> List[Dict[str, Any]]:
        """
        Обрабатывает список файлов.

        Args:
            files: Список загруженных файлов
            descriptions: Список описаний

        Returns:
            list: Результаты обработки каждого файла
        """
        results = []

        for idx, file in enumerate(files):
            description = self._get_description(descriptions, idx)
            result = self._process_single_file(file, description, user)
            results.append(result)

        return results

    def _process_single_file(self, file, description: str, user) -> Dict[str, Any]:
        """
        Обрабатывает один файл реплея.

        Args:
            file: Загруженный файл
            description: Описание

        Returns:
            dict: Результат обработки файла
        """
        file_result = {"file": file.name}

        # Валидация файла
        if validation_error := ReplayFileValidator.validate(file):
            logger.warning(f"[BATCH] Валидация не пройдена '{file.name}': {validation_error}")
            file_result["ok"] = False
            file_result["error"] = validation_error
            return file_result

        # Обработка файла
        try:
            replay = self.replay_service.process_replay(file, description, user=user)

            file_result["ok"] = True
            file_result["replay_id"] = replay.id
            file_result["redirect_url"] = reverse('replay_detail', kwargs={'pk': replay.id})

            logger.info(f"[BATCH] Успешно загружен '{file.name}' (ID: {replay.id})")

        except Exception as e:
            file_result.update(self.error_handler.handle_error(e, file.name))

        return file_result

    @staticmethod
    def _get_description(descriptions: list, index: int) -> str:
        """Получает описание по индексу или возвращает пустую строку."""
        if index < len(descriptions):
            desc = descriptions[index].strip()
            max_len = ReplayProcessingService.MAX_DESCRIPTION_LEN
            return desc[:max_len] if len(desc) > max_len else desc
        return ''

    def _build_response(self, request: HttpRequest, results: List[Dict[str, Any]], total: int):
        """
        Формирует ответ на основе результатов обработки.

        Args:
            request: HTTP запрос
            results: Результаты обработки файлов
            total: Общее количество файлов

        Returns:
            JsonResponse или redirect
        """
        created_count = sum(1 for r in results if r.get("ok"))
        error_count = total - created_count

        # Для обычного запроса (не AJAX)
        if not self._is_ajax_request(request):
            return self._build_html_response(request, created_count, error_count, total)

        # Для AJAX запроса
        return self._build_json_response(results, total, created_count, error_count)

    @staticmethod
    def _build_html_response(request: HttpRequest, created: int, errors: int, total: int):
        """Формирует HTML ответ с редиректом."""
        if created:
            messages.success(request, f"Загружено успешно: {created} из {total}")
        if errors:
            messages.error(request, f"Ошибки при загрузке: {errors} из {total}")

        return redirect('replay_list')

    @staticmethod
    def _build_json_response(
            results: List[Dict[str, Any]],
            total: int,
            created: int,
            errors: int
    ) -> JsonResponse:
        """
        Формирует JSON ответ.
        """
        # Определяем URL для редиректа
        redirect_url = reverse('replay_list')
        if total == 1 and results and results[0].get("ok"):
            redirect_url = results[0]["redirect_url"]

        return JsonResponse({
            "success": True,
            "summary": {
                "processed": total,
                "created": created,
                "errors": errors,
                "skipped": 0,
            },
            "results": results,
            "redirect_url": redirect_url,
        }, status=200)

    def _error_response(self, request: HttpRequest, message: str):
        """
        Формирует ответ с ошибкой.
        """
        if self._is_ajax_request(request):
            return JsonResponse({
                "success": False,
                "error": message,
                "redirect_url": reverse('replay_list')
            }, status=400)

        messages.error(request, message)
        return redirect('replay_list')


class ReplayListView(ListView):
    """
    Представление списка реплеев с пагинацией и фильтрацией.
    """
    model = Replay
    template_name = 'replays/list.html'
    context_object_name = 'items'
    paginate_by = 10

    SORTABLE_FIELDS = {
        'credits',
        'xp',
        'kills',
        'damage',
        'assist',
        'block',
        'created_at',
        'comment_count',
        'view_count',
        'download_count',
    }

    def dispatch(self, request, *args, **kwargs):
        """Логируем каждый запрос"""
        try:
            logger.info(f"ReplayListView: GET params = {dict(request.GET.lists())}")
            return super().dispatch(request, *args, **kwargs)
        except Exception as e:
            logger.exception(f"Ошибка в ReplayListView.dispatch: {e}")
            raise

    def get_queryset(self):
        """
        Получение отфильтрованного QuerySet с применением фильтров.
        """
        try:
            qs = (Replay.objects
                  .select_related('tank', 'owner', 'user')
                  .prefetch_related('participants')
                  )

            # СНАЧАЛА фильтры
            qs = self._apply_filters(qs)

            comment_ct = ContentType.objects.get_for_model(Replay)
            comment_counts = (
                Comment.objects.filter(
                    content_type=comment_ct,
                    object_pk=Cast(OuterRef('pk'), output_field=CharField()),
                    site_id=settings.SITE_ID,
                    is_public=True,
                    is_removed=False,
                )
                .values('object_pk')
                .annotate(total=Count('pk'))
                .values('total')
            )

            qs = qs.annotate(
                comment_count=Coalesce(
                    Subquery(comment_counts, output_field=IntegerField()),
                    Value(0),
                    output_field=IntegerField(),
                )
            )

            # ПОТОМ сортировка
            sort = (self.request.GET.get('sort') or '').strip()
            direction = (self.request.GET.get('dir') or 'desc').lower()

            if sort in self.SORTABLE_FIELDS:
                order = sort if direction == 'asc' else f'-{sort}'
                qs = qs.order_by(order, '-battle_date', '-created_at')
            else:
                qs = qs.order_by('-battle_date', '-created_at')

            logger.debug(f"QuerySet построен, SQL: {qs.query}")
            return qs

        except Exception as e:
            logger.exception(f"Ошибка в get_queryset: {e}")
            raise

    def _apply_filters(self, queryset):
        try:
            def _getlist(name):
                return self.request.GET.getlist(name)

            def _to_int_set(vals):
                out = set()
                for v in vals:
                    try:
                        out.add(int(v))
                    except (TypeError, ValueError):
                        pass
                return out

            m2m_used = False

            # tanks (multi)
            tank_ids = _to_int_set(_getlist("tank"))
            if tank_ids:
                queryset = queryset.filter(tank_id__in=tank_ids)
                logger.debug(f"Фильтр по танкам: {tank_ids}")

            # mastery (multi)
            mastery_vals = _to_int_set(_getlist("mastery"))
            if mastery_vals:
                queryset = queryset.filter(mastery__in=mastery_vals)
                logger.debug(f"Фильтр по мастерству: {mastery_vals}")

            # dates
            if date_from := self.request.GET.get("date_from"):
                if d := parse_date(date_from):
                    queryset = queryset.filter(battle_date__date__gte=d)
                    logger.debug(f"Фильтр date_from: {d}")
            if date_to := self.request.GET.get("date_to"):
                if d := parse_date(date_to):
                    queryset = queryset.filter(battle_date__date__lte=d)
                    logger.debug(f"Фильтр date_to: {d}")

            # map search
            if map_search := self.request.GET.get("map_search"):
                queryset = queryset.filter(map__map_display_name__icontains=map_search)
                logger.debug(f"Фильтр по карте: {map_search}")

            # numeric ranges
            numeric = ["damage", "xp", "kills", "credits", "assist", "block"]
            for f in numeric:
                vmin = self.request.GET.get(f"{f}_min")
                vmax = self.request.GET.get(f"{f}_max")
                if vmin:
                    try:
                        queryset = queryset.filter(**{f"{f}__gte": int(vmin)})
                    except (TypeError, ValueError):
                        pass
                if vmax:
                    try:
                        queryset = queryset.filter(**{f"{f}__lte": int(vmax)})
                    except (TypeError, ValueError):
                        pass

            # tank attrs (multi)
            levels = _to_int_set(_getlist("level")) or _to_int_set(_getlist("tier"))
            if levels:
                queryset = queryset.filter(tank__level__in=levels)

            types_ = set(_getlist("type"))
            if types_:
                queryset = queryset.filter(tank__type__in=types_)

            nations = set(_getlist("nation"))
            if nations:
                queryset = queryset.filter(tank__nation__in=nations)

            # win/loss
            vf = self.request.GET.get("victory")
            if vf == "win":
                queryset = queryset.filter(credits__gt=0)
            elif vf == "loss":
                queryset = queryset.filter(credits__lte=0)

            # game version
            gv = set(_getlist("game_version"))
            if gv:
                queryset = queryset.filter(game_version__in=gv)

            bt = set(_getlist("battle_type"))
            if bt:
                queryset = queryset.filter(battle_type__in=bt)

            owner_nick = (self.request.GET.get("owner_nick") or "").strip()
            if owner_nick:
                queryset = queryset.filter(owner__real_name__icontains=owner_nick)

            user_nick = (self.request.GET.get("user_nick") or "").strip()
            if user_nick:
                queryset = queryset.filter(user__username__icontains=user_nick)

            short_description = (self.request.GET.get("short_description") or "").strip()
            if short_description:
                queryset = queryset.filter(short_description__icontains=short_description)

            # поиск по нику участника
            participant_nick = (self.request.GET.get("participant_nick") or "").strip()
            if participant_nick:
                queryset = queryset.filter(participants__real_name__icontains=participant_nick)
                m2m_used = True

            # клантеги
            owner_clan = (self.request.GET.get("owner_clan") or "").strip().upper()
            if owner_clan:
                queryset = queryset.filter(owner__clan_tag__iexact=owner_clan)

            clan = (self.request.GET.get("clan") or "").strip().upper()
            if clan:
                queryset = queryset.filter(
                    Q(owner__clan_tag__iexact=clan) | Q(participants__clan_tag__iexact=clan)
                )
                m2m_used = True

            # поиск по версии
            game_version_search = (self.request.GET.get("game_version_search") or "").strip()
            if game_version_search:
                queryset = queryset.filter(game_version__icontains=game_version_search)

            if m2m_used:
                queryset = queryset.distinct()
                logger.debug("Применён distinct() из-за M2M фильтров")

            return queryset

        except Exception as e:
            logger.exception(f"Ошибка в _apply_filters: {e}")
            raise

    def get_context_data(self, **kwargs):
        try:
            ctx = super().get_context_data(**kwargs)

            q = self.request.GET.copy()
            q.pop("page", None)
            base_qs = q.urlencode()

            current_sort = (self.request.GET.get('sort') or '').strip()
            current_dir = (self.request.GET.get('dir') or 'desc').lower()

            def next_dir_for(field: str) -> str:
                if current_sort == field and current_dir == 'desc':
                    return 'asc'
                return 'desc'

            next_dir = {f: next_dir_for(f) for f in self.SORTABLE_FIELDS}

            tank_types = Tank.objects.values_list("type", flat=True).distinct().order_by("type")

            ctx.update({
                "filter_data": {
                    "tanks": Tank.objects.order_by("level", "name"),
                    "nations": Nation.choices,
                    "tank_types": tank_types,
                    "levels": Tank.objects.order_by('level').values_list('level', flat=True).distinct(),
                    "mastery_choices": [(i, f"Знак {i}") for i in range(5)],
                },
                "current_filters": dict(self.request.GET.lists()),
                "has_filters_applied": bool(base_qs),
                "filters_url": reverse("replay_filters"),
                "reset_url": self.request.path,

                "page_qs": base_qs,
                "page_qs_prefix": (base_qs + "&") if base_qs else "",

                "current_sort": current_sort,
                "current_dir": current_dir,
                "next_dir": next_dir,
            })

            logger.debug(f"Context подготовлен успешно")
            return ctx

        except Exception as e:
            logger.exception(f"Ошибка в get_context_data: {e}")
            raise


class MyReplaysView(LoginRequiredMixin, ReplayListView):
    template_name = 'replays/list.html'

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Мои реплеи"
        context['show_delete_button'] = True
        return context


class ReplayDeleteView(LoginRequiredMixin, View):
    """
    Удаление реплея.
    Только владелец может удалить свой реплей.
    """
    def post(self, request, pk):
        replay = get_object_or_404(Replay, pk=pk)

        if replay.user != request.user:
            messages.error(request, "Вы не можете удалить этот реплей.")
            return redirect('my_replay_list')

        try:
            # Store file name for success message
            replay_name = replay.file_name

            # Delete the replay file
            if replay.file_name:
                file_path = os.path.join(settings.MEDIA_ROOT, replay.file_name)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Файл реплея {file_path} был удален.")

            replay.delete()
            messages.success(request, f"Реплей '{replay_name}' был успешно удален.")

        except Exception as e:
            logger.exception(f"Ошибка при удалении реплея: {e}")
            messages.error(request, f"Ошибка при удалении реплея: {e}")

        return redirect('my_replay_list')


class ReplayFiltersView(TemplateView):
    """
    Страница с формой фильтрации. Сабмитит GET на список.
    """
    template_name = "replays/filters.html"

    def get_context_data(self, **kwargs):
        from django.urls import reverse
        ctx = super().get_context_data(**kwargs)
        tank_types = Tank.objects.values_list("type", flat=True).distinct().order_by("type")

        ctx.update({
            "filter_data": {
                "tanks": Tank.objects.order_by("level", "name"),
                "nations": Nation.choices,
                "tank_types": tank_types,
                "levels": Tank.objects.order_by('level').values_list('level', flat=True).distinct(),
                "mastery_choices": [(i, f"Знак {i}") for i in range(5)],
                "game_versions": (Replay.objects.values_list("game_version", flat=True)
                                  .exclude(game_version__isnull=True).exclude(game_version__exact="")
                                  .distinct().order_by("game_version")),
                "battle_types": (Replay.objects.values_list("battle_type", flat=True)
                                 .exclude(battle_type__isnull=True).exclude(battle_type__exact="")
                                 .distinct().order_by("battle_type")),
            },
            "current_filters": dict(self.request.GET.lists()),  # если пришли из списка с префиллом
            "list_url": reverse("replay_list"),
        })
        return ctx


class ReplayDetailView(DetailView):
    """
    Детальная страница реплея с полным анализом данных боя.
    """
    model = Replay
    template_name = 'replays/detail.html'
    context_object_name = 'replay'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        Replay.objects.filter(pk=self.object.pk).update(view_count=F('view_count') + 1)
        self.object.view_count = (self.object.view_count or 0) + 1
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def _preload_tanks(self, cache) -> Dict[str, Tank]:
        """
        Предзагружает все танки, используемые в бою, одним запросом.

        Args:
            cache: ReplayDataCache с данными реплея

        Returns:
            Словарь {vehicleId: Tank}
        """
        from replays.parser.replay_cache import ReplayDataCache

        tank_tags = set()

        # Танк владельца реплея
        player_vehicle = cache.first_block.get("playerVehicle")
        if player_vehicle and ":" in player_vehicle:
            _, tag = player_vehicle.split(":", 1)
            tank_tags.add(tag)

        # Танки всех участников боя из avatars
        for avatar_id, avatar_data in cache.avatars.items():
            if isinstance(avatar_data, dict):
                vehicle_type = avatar_data.get("vehicleType", "")
                if ":" in vehicle_type:
                    _, tag = vehicle_type.split(":", 1)
                    tank_tags.add(tag)

        # Танки из metadata_vehicles (используется в get_team_results)
        for avatar_id, vehicle_data in cache.metadata_vehicles.items():
            if isinstance(vehicle_data, dict):
                vehicle_type = vehicle_data.get("vehicleType", "")
                if ":" in vehicle_type:
                    _, tag = vehicle_type.split(":", 1)
                    tank_tags.add(tag)

        # Загружаем все танки одним запросом
        tanks = Tank.objects.filter(vehicleId__in=tank_tags)
        tanks_cache = {t.vehicleId: t for t in tanks}

        logger.debug(f"Предзагружено {len(tanks_cache)} танков из {len(tank_tags)} запрошенных")
        if len(tanks_cache) < len(tank_tags):
            missing = tank_tags - set(tanks_cache.keys())
            logger.warning(f"В базе отсутствуют {len(missing)} танков: {missing}")

        return tanks_cache

    def _preload_achievements(self, cache) -> tuple:
        """
        Предзагружает достижения текущего игрока одним запросом.

        Args:
            cache: ReplayDataCache с данными реплея

        Returns:
            Кортеж (achievements_nonbattle, achievements_battle)
        """
        achievement_ids = cache.get_achievements()

        if not achievement_ids:
            empty = Achievement.objects.none()
            return empty, empty

        # Нормализуем ID
        ids = []
        for aid in achievement_ids:
            try:
                ids.append(int(aid))
            except (TypeError, ValueError):
                continue

        if not ids:
            empty = Achievement.objects.none()
            return empty, empty

        # Загружаем ВСЕ достижения одним запросом
        achievements = Achievement.objects.filter(
            achievement_id__in=ids,
            is_active=True
        ).annotate(
            weight=Coalesce(
                Cast('order', FloatField()),
                Value(0.0),
                output_field=FloatField(),
            )
        )

        # Разделяем на battle и nonbattle
        # ВАЖНО: Материализуем QuerySet в список, чтобы избежать повторных SQL запросов при .count()
        battle_sections = ('battle', 'epic')
        all_achievements = list(achievements)  # Материализуем один раз!

        ach_battle = [a for a in all_achievements if a.section in battle_sections]
        ach_nonbattle = [a for a in all_achievements if a.section not in battle_sections]

        # Сортируем в Python (данные уже загружены)
        ach_battle.sort(key=lambda a: (-getattr(a, 'weight', 0.0), a.name))
        ach_nonbattle.sort(key=lambda a: (-getattr(a, 'weight', 0.0), a.name))

        logger.debug(
            f"Предзагружено достижений: {len(ach_nonbattle)} небоевых, {len(ach_battle)} боевых"
        )

        return ach_nonbattle, ach_battle

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Back URL
        fallback = reverse("replay_list")
        back = self.request.GET.get("back") or self.request.META.get("HTTP_REFERER", "")
        safe_back = fallback
        if back:
            try:
                back = urllib.parse.unquote(back)
                u = urllib.parse.urlparse(back)
                # запрещаем внешние адреса; разрешаем только относительные пути и путь списка
                if not u.scheme and not u.netloc and u.path.startswith(urllib.parse.urlparse(fallback).path):
                    safe_back = back
            except Exception:
                pass
        context["back_url"] = safe_back

        try:
            # ============================================================
            # ЭТАП 1: СОЗДАНИЕ КЕША (парсинг JSON один раз!)
            # ============================================================
            from replays.parser.replay_cache import ReplayDataCache
            cache = ReplayDataCache(self.object.payload)
            logger.debug(f"Создан кеш для реплея {self.object.id}")

            # ============================================================
            # ЭТАП 2: ПРЕДЗАГРУЗКА ДАННЫХ (минимум запросов к БД)
            # ============================================================
            tanks_cache = self._preload_tanks(cache)
            achievements_nonbattle, achievements_battle = self._preload_achievements(cache)

            # Создаём контекст для кеширования промежуточных вычислений
            from replays.parser.extractor import ExtractorContext
            extractor_context = ExtractorContext(cache)

            logger.debug(
                f"Предзагружено: {len(tanks_cache)} танков, "
                f"{len(achievements_nonbattle)} + {len(achievements_battle)} достижений"
            )

            # ============================================================
            # ЭТАП 3: ИЗВЛЕЧЕНИЕ ДАННЫХ (с использованием кеша)
            # ============================================================

            # Персональные данные (минимальный набор полей)
            context['personal_data'] = ExtractorV2.get_personal_data_minimal(cache)

            # Достижения
            context['achievements_nonbattle'] = achievements_nonbattle
            context['achievements_battle'] = achievements_battle

            # Мастерство
            m = int(self.object.mastery or 0)
            label_map = {
                4: "Мастер - 100%",
                3: "1 степень - 95%",
                2: "2 степень - 80%",
                1: "3 степень - 50%",
            }
            context['has_mastery'] = m > 0
            context['mastery'] = m
            context['mastery_label'] = label_map.get(m, "")
            context['mastery_image'] = f"style/images/wot/achievement/markOfMastery{m}.png" if m else ""
            context['achievements_count_in_badges'] = len(achievements_nonbattle) + (1 if m > 0 else 0)
            context['achievements_battle_count'] = len(achievements_battle)

            # Детали боя (оптимизированная версия с cache)
            context['details'] = ExtractorV2.get_details_data(cache)

            # Взаимодействия (оптимизированная версия - один проход вместо двух!)
            interaction_rows, interactions_summary = ExtractorV2.build_interactions_data(cache, tanks_cache)
            context["interaction_rows"] = interaction_rows
            context["interactions_summary"] = interactions_summary

            # Причина смерти (оптимизированная версия с cache)
            context['death_reason_text'] = ExtractorV2.get_death_text(cache)

            # Экономическая сводка (оптимизированная версия с кешированием)
            context['income'] = ExtractorV2.build_income_summary_cached(cache, extractor_context)

            # Тип боя (оптимизированная версия с cache)
            context["battle_type_label"] = ExtractorV2.get_battle_type_label(cache)

            # Результат боя (оптимизированная версия с cache)
            context["battle_outcome"] = ExtractorV2.get_battle_outcome(cache)

            # Командные результаты (оптимизированная версия с кешем танков и медалей!)
            context['team_results'] = ExtractorV2.get_team_results(cache, tanks_cache)

            # Подробный отчёт (оптимизированная версия с cache)
            context['detailed_report'] = ExtractorV2.get_detailed_report(cache)

            logger.debug(f"Контекст для реплея {self.object.id} успешно сформирован")

        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Ошибка парсинга реплея {self.object.id}: {str(e)}", exc_info=True)
            context['parse_error'] = f"Ошибка обработки данных реплея: {str(e)}"

        return context


class ReplayDownloadView(LoginRequiredMixin, View):
    """
    View для скачивания файлов реплеев World of Tanks.
    Возвращает .mtreplay файл по ID реплея с оптимизацией для больших файлов.
    Требует авторизации пользователя.
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

            Replay.objects.filter(pk=replay.pk).update(download_count=F('download_count') + 1)

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


def donate(request):
    """
    Показывает форму для доната: ввод суммы, выбор способа оплаты.
    """
    if request.method == "POST":
        # получим сумму из формы
        sum_amount = request.POST.get("sum")
        payment_type = request.POST.get("paymentType")
        # можно добавить в контекст, чтобы подставить в форму YooMoney
        context = {
            "receiver": settings.YOOMONEY_RECEIVER,
            "sum": sum_amount,
            "paymentType": payment_type,
            "label": "donation",  # или что-то динамическое
            "successURL": request.build_absolute_uri('/donate/success/'),
        }
        return render(request, "donations/redirect_to_yoomoney.html", context)
    else:
        return render(request, "donations/donate_form.html")


def donate_success(request):
    """
    Страница благодарности после доната.
    Пытается получить параметры операции из GET-параметров,
    либо из контекста (если уведомление уже обработано).
    """
    # Параметры из GET
    label = request.GET.get("label")
    operation_id = request.GET.get("operation_id")
    amount = request.GET.get("sum") or request.GET.get("amount")
    notification_type = request.GET.get("notification_type")

    context = {
        "label": label,
        "operation_id": operation_id,
        "amount": amount,
        "notification_type": notification_type,
    }
    return render(request, "donations/donate_success.html", context)
