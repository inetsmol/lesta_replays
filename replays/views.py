# replays/views.py
from __future__ import annotations

import logging
import mimetypes
import os
import urllib.parse
import zipfile
from collections import OrderedDict
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, F, Count, OuterRef, Subquery, IntegerField, CharField, Value, FloatField, Exists, BooleanField, Prefetch, Avg, Sum
from django.db.models.functions import Coalesce, Cast
from django.http import JsonResponse, Http404, HttpResponse, StreamingHttpResponse, HttpRequest
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.encoding import escape_uri_path
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from django_comments.models import Comment

from .error_handlers import ReplayErrorHandler
from .forms import VideoLinkForm, AvatarUploadForm, UsernameChangeForm
from .models import (
    Replay, Tank, Nation, Achievement, MarksOnGun, Map,
    APIUsageLog, SubscriptionPlan, ReplayVideoLink,
    ReplayStatBattle, ReplayStatPlayer,
)
from .parser.extractor import ExtractorV2
from .parser.parser import ParseError
from .services import ReplayProcessingService, ReplayStatsProcessingService, SubscriptionService, UsageLimitService, VideoLinkService
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

        # Проверка лимита загрузок по подписке
        if user and not UsageLimitService.can_upload(user):
            if self._is_ajax_request(request):
                return JsonResponse({
                    "success": False,
                    "limit_reached": "upload",
                    "error": "Вы достигли дневного лимита загрузок.",
                }, status=429)
            return self._error_response(
                request,
                "Вы достигли дневного лимита загрузок. "
                "Оформите подписку для неограниченных загрузок."
            )

        # Валидация пакета файлов
        is_premium = SubscriptionService.is_premium(user)
        if batch_error := BatchUploadValidator.validate_batch(files, is_premium=is_premium):
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

            # Записываем факт загрузки для лимитов
            if user:
                UsageLimitService.record_upload(user)

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

    # Допустимые значения для количества элементов на странице
    ALLOWED_PAGE_SIZES = [10, 25, 50, 100]

    def get_paginate_by(self, queryset=None):
        """
        Возвращает количество элементов на странице из GET параметра 'per_page'.
        По умолчанию - 10 элементов.
        """
        try:
            per_page = int(self.request.GET.get('per_page', 10))
            if per_page in self.ALLOWED_PAGE_SIZES:
                return per_page
        except (TypeError, ValueError):
            pass
        return self.paginate_by

    @staticmethod
    def _get_news():
        from news.models import News
        return News.objects.filter(is_active=True)[:5]

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
            prefetches = ['participants', 'video_links']
            # Если фильтр по достижениям активен — prefetch боевых ачивок для значков на карточке
            if self.request.GET.getlist("achievement"):
                prefetches.append(
                    Prefetch(
                        'achievements',
                        queryset=Achievement.objects.filter(
                            section__in=('battle', 'epic', 'class')
                        ).exclude(achievement_id=79),
                        to_attr='battle_achievements',
                    )
                )
            qs = (Replay.objects
                  .select_related('tank', 'owner', 'user', 'user__subscription__plan', 'user__profile')
                  .prefetch_related(*prefetches)
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
                ),
            )

            # Аннотация: лайкнул ли текущий пользователь
            if self.request.user.is_authenticated:
                from vote.models import Vote
                replay_ct = ContentType.objects.get_for_model(Replay)
                qs = qs.annotate(
                    user_liked=Exists(
                        Vote.objects.filter(
                            content_type=replay_ct,
                            object_id=OuterRef('pk'),
                            user_id=self.request.user.id,
                        )
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
            # map search (text)
            if map_search := self.request.GET.get("map_search"):
                queryset = queryset.filter(map__map_display_name__icontains=map_search)
                logger.debug(f"Фильтр по карте (текст): {map_search}")

            # maps (multi - checkbox)
            # Support both ID (legacy) and Name (new)
            map_values = _getlist("map")
            if map_values:
                map_ids = set()
                map_names = set()
                for v in map_values:
                    # If it looks like ID (digit), treat as ID, otherwise assume name
                    # Note: map names are strings, IDs are ints
                    if v.isdigit():
                        map_ids.add(int(v))
                    else:
                        map_names.add(v)
                
                q_maps = Q()
                if map_ids:
                    q_maps |= Q(map_id__in=map_ids)
                if map_names:
                    q_maps |= Q(map__map_display_name__in=map_names)
                
                queryset = queryset.filter(q_maps)
                logger.debug(f"Фильтр по картам: IDs={map_ids}, Names={map_names}")

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

            # === Премиум-фильтры ===
            plan = SubscriptionService.get_user_plan(self.request.user)

            bt = set(_getlist("battle_type"))
            if bt:
                queryset = queryset.filter(battle_type__in=bt)

            gp = set(_getlist("gameplay"))
            if gp and 'all' not in gp:
                queryset = queryset.filter(gameplay_id__in=gp)
            elif not gp and not bt:
                # Для премиум-пользователей по умолчанию показываем только
                # случайный бой + стандартный бой (battle_type IN (1,19) AND gameplay_id='ctf')
                if plan.can_use_advanced_filters:
                    queryset = queryset.filter(
                        battle_type__in=['1', '19'],
                        gameplay_id='ctf',
                    )

            # Выжил / Уничтожен (премиум)
            if plan.can_use_advanced_filters:
                survived = self.request.GET.get("survived", "").strip()
                if survived == "alive":
                    queryset = queryset.filter(is_alive=True)
                elif survived == "dead":
                    queryset = queryset.filter(is_alive=False)

                # Продолжительность боя (премиум, ввод в минутах → фильтр в секундах)
                dur_min = self.request.GET.get("duration_min")
                dur_max = self.request.GET.get("duration_max")
                if dur_min:
                    try:
                        queryset = queryset.filter(battle_duration__gte=int(dur_min) * 60)
                    except (TypeError, ValueError):
                        pass
                if dur_max:
                    try:
                        queryset = queryset.filter(battle_duration__lte=int(dur_max) * 60)
                    except (TypeError, ValueError):
                        pass

                # Соло / Взвод (премиум)
                platoon = self.request.GET.get("platoon", "").strip()
                if platoon == "solo":
                    queryset = queryset.filter(is_platoon=False)
                elif platoon == "platoon":
                    queryset = queryset.filter(is_platoon=True)

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
            if plan.can_use_pro_filters:
                # Фильтр по конкретному достижению (multi, OR-логика)
                ach_ids = _to_int_set(_getlist("achievement"))
                if ach_ids:
                    queryset = queryset.filter(achievements__achievement_id__in=ach_ids)
                    m2m_used = True

                # Фильтр по минимальному кол-ву достижений
                ach_min = self.request.GET.get("achievement_count_min")
                if ach_min:
                    try:
                        queryset = queryset.filter(achievement_count__gte=int(ach_min))
                    except (TypeError, ValueError):
                        pass

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
            ctx["news_list"] = self._get_news()

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

            # Получаем текущее значение per_page
            current_per_page = self.get_paginate_by(None)

            # Создаем QueryDict без параметров page и per_page для ссылок
            q_without_page = self.request.GET.copy()
            q_without_page.pop("page", None)
            q_without_page.pop("per_page", None)
            base_qs_without_per_page = q_without_page.urlencode()

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
                "news_list": self._get_news(),

                # Параметры пагинации
                "allowed_page_sizes": self.ALLOWED_PAGE_SIZES,
                "current_per_page": current_per_page,
                "base_qs_without_per_page": base_qs_without_per_page,

            })

            # Премиум-фильтры
            plan = SubscriptionService.get_user_plan(self.request.user)
            can_advanced = plan.can_use_advanced_filters
            can_pro = plan.can_use_pro_filters
            ctx["can_use_advanced_filters"] = can_advanced
            ctx["can_use_pro_filters"] = can_pro
            ctx["default_gameplay_applied"] = (
                can_advanced
                and not self.request.GET.getlist("gameplay")
                and not self.request.GET.getlist("battle_type")
            )
            # Показывать значки достижений на карточках, если фильтр по ачивкам активен
            show_ach = bool(can_pro and self.request.GET.getlist("achievement"))
            ctx["show_achievements_on_cards"] = show_ach

            # Подставить правильные пути к картинкам для медалей со степенями
            if show_ach:
                self._resolve_achievement_images(ctx.get("object_list") or ctx.get("page_obj"))

            logger.debug(f"Context подготовлен успешно")
            return ctx

        except Exception as e:
            logger.exception(f"Ошибка в get_context_data: {e}")
            raise


    # Медали со степенями: ID -> базовое имя файла (из AchievementWithRank)
    RANKED_MEDALS = {
        41: 'medalKay', 42: 'medalSamokhin', 43: 'medalGudz',
        44: 'medalPoppel', 45: 'medalAbrams', 46: 'medalLeClerc',
        47: 'medalLavrinenko', 48: 'medalEkins',
        538: 'readyForBattleLT', 539: 'readyForBattleMT',
        540: 'readyForBattleHT', 541: 'readyForBattleSPG',
        542: 'readyForBattleATSPG',
        1215: 'readyForBattleAllianceUSSR', 1216: 'readyForBattleAllianceGermany',
        1217: 'readyForBattleAllianceUSA', 1218: 'readyForBattleAllianceFrance',
    }
    # ID, для которых степень 1 тоже значима
    ALWAYS_RANKED_IDS = {538, 539, 540, 541, 542, 1215, 1216, 1217, 1218}

    def _resolve_achievement_images(self, page):
        """Подставляет правильные пути к картинкам для медалей со степенями."""
        if not page:
            return
        from replays.parser.replay_cache import ReplayDataCache
        for replay in page:
            if not hasattr(replay, 'battle_achievements') or not replay.battle_achievements:
                continue
            # Проверяем есть ли медали со степенями
            ranked_ids = {a.achievement_id for a in replay.battle_achievements} & set(self.RANKED_MEDALS)
            # Достаём степени из payload если есть медали со степенями
            awv = {}
            if ranked_ids:
                try:
                    cache = ReplayDataCache(replay.payload)
                    awv = cache.get_achievements_with_values()
                except Exception:
                    pass
            for ach in replay.battle_achievements:
                # По умолчанию — обычный путь
                ach.resolved_image = ach.image_big
                if ach.achievement_id not in ranked_ids:
                    continue
                value = awv.get(ach.achievement_id)
                if not isinstance(value, int):
                    continue
                if ach.achievement_id in self.ALWAYS_RANKED_IDS:
                    rank = value if value >= 1 else None
                else:
                    rank = value if value > 1 else None
                if rank is not None:
                    base_name = self.RANKED_MEDALS[ach.achievement_id]
                    if base_name in ach.image_big:
                        ach.resolved_image = ach.image_big.replace(
                            f'{base_name}.png', f'{base_name}{rank}.png'
                        )


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


class ReplayBulkDeleteView(LoginRequiredMixin, View):
    """
    Массовое удаление реплеев.
    Принимает JSON с массивом ID реплеев. Удаляет только принадлежащие текущему пользователю.
    """
    def post(self, request):
        import json

        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'success': False, 'error': 'Некорректные данные'}, status=400)

        if not ids or not isinstance(ids, list):
            return JsonResponse({'success': False, 'error': 'Не выбраны реплеи'}, status=400)

        # Ограничиваем количество за раз
        ids = ids[:100]

        # Получаем только реплеи текущего пользователя
        replays = Replay.objects.filter(pk__in=ids, user=request.user)
        count = replays.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'Нет реплеев для удаления'}, status=404)

        # Удаляем файлы с диска
        for replay in replays:
            if replay.file_name:
                file_path = os.path.join(settings.MEDIA_ROOT, replay.file_name)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError as e:
                        logger.warning(f"Не удалось удалить файл {file_path}: {e}")

        # Удаляем записи из БД
        replays.delete()
        logger.info(f"Пользователь {request.user.id} массово удалил {count} реплеев")

        return JsonResponse({'success': True, 'deleted': count})


class ReplayFiltersView(TemplateView):
    """
    Страница с формой фильтрации. Сабмитит GET на список.
    """
    template_name = "replays/filters.html"

    @staticmethod
    def _get_battle_types():
        """Возвращает список кортежей (код, название) для типов боёв."""
        codes = (Replay.objects.values_list("battle_type", flat=True)
                 .exclude(battle_type__isnull=True).exclude(battle_type__exact="")
                 .distinct().order_by("battle_type"))
        result = []
        helper = Replay()
        for code in codes:
            helper.battle_type = code
            label = helper.get_battle_type_display() or f"Тип {code}"
            result.append((code, label))
        return result

    @staticmethod
    def _get_gameplay_modes():
        """Возвращает список кортежей (gameplay_id, название) для режимов игры."""
        codes = (Replay.objects.values_list("gameplay_id", flat=True)
                 .exclude(gameplay_id__isnull=True).exclude(gameplay_id__exact="")
                 .distinct().order_by("gameplay_id"))
        result = []
        helper = Replay()
        for code in codes:
            helper.gameplay_id = code
            label = helper.get_gameplay_display() or code
            result.append((code, label))
        return result

    def get_context_data(self, **kwargs):
        from django.urls import reverse
        ctx = super().get_context_data(**kwargs)
        tank_types = Tank.objects.values_list("type", flat=True).distinct().order_by("type")

        # Получаем все версии и сортируем их в Python
        # Deduplicate using set + strip to avoid duplicates like "1.26.0.0" vs "1.26.0.0 "
        raw_versions_qs = (Replay.objects.values_list("game_version", flat=True)
                          .exclude(game_version__isnull=True)
                          .exclude(game_version__exact=""))
        
        raw_versions = set(v.strip() for v in raw_versions_qs if v and v.strip())

        def version_key(v):
            try:
                # Преобразуем "1.26.0.0" -> [1, 26, 0, 0] для корректной сортировки
                return [int(p) for p in v.split('.')]
            except ValueError:
                return [0]

        game_versions = sorted(raw_versions, key=version_key)

        current_filters = dict(self.request.GET.lists())

        ctx.update({
            "filter_data": {
                "tanks": Tank.objects.order_by("level", "name"),
                "maps": Map.objects.exclude(map_display_name="").values_list("map_display_name", flat=True).distinct().order_by("map_display_name"),
                "nations": Nation.choices,
                "tank_types": tank_types,
                "levels": Tank.objects.order_by('level').values_list('level', flat=True).distinct(),
                "mastery_choices": [(i, f"Знак {i}") for i in range(5)],
                "game_versions": game_versions,
                "battle_types": self._get_battle_types(),
                "gameplay_modes": self._get_gameplay_modes(),
                "achievements": (Achievement.objects
                                 .filter(replays__isnull=False)
                                 .annotate(replay_count=Count('replays'))
                                 .order_by('replay_count', 'name')),
            },
            "current_filters": current_filters,
            "list_url": reverse("replay_list"),
            "can_use_advanced_filters": SubscriptionService.get_user_plan(
                self.request.user
            ).can_use_advanced_filters if self.request.user.is_authenticated else False,
            "can_use_pro_filters": SubscriptionService.get_user_plan(
                self.request.user
            ).can_use_pro_filters if self.request.user.is_authenticated else False,
        })
        return ctx


class ReplayUpdateDescriptionView(LoginRequiredMixin, View):
    """
    AJAX-обновление поля short_description.
    """
    def post(self, request, pk):
        replay = get_object_or_404(Replay, pk=pk)

        if replay.user != request.user:
            return JsonResponse({"success": False, "error": "Вы не можете редактировать этот реплей."}, status=403)

        try:
            import json
            data = json.loads(request.body)
            new_desc = data.get("short_description", "").strip()
            # Обрезаем до 60 символов как в модели
            new_desc = new_desc[:60]
            
            replay.short_description = new_desc
            replay.save(update_fields=['short_description'])
            
            return JsonResponse({"success": True, "short_description": replay.short_description})
        except Exception as e:
            logger.exception(f"Ошибка при обновлении описания: {e}")
            return JsonResponse({"success": False, "error": "Ошибка при сохранении"}, status=400)


class ReplayDetailView(DetailView):
    """
    Детальная страница реплея с полным анализом данных боя.
    """
    model = Replay
    template_name = 'replays/detail.html'
    context_object_name = 'replay'

    def get(self, request, *args, **kwargs):
        from django.core.cache import cache
        import time

        self.object = self.get_object()
        
        # Anti-abuse logic
        user_id = request.user.pk if request.user.is_authenticated else request.session.session_key
        if not user_id:
             request.session.save()
             user_id = request.session.session_key

        cache_key = f"replay_view_timestamps_{self.object.pk}_{user_id}"
        timestamps = cache.get(cache_key, [])
        now = time.time()
        
        # Filter timestamps within last 5 minutes (300 seconds)
        timestamps = [t for t in timestamps if now - t < 300]
        
        show_anti_abuse_banner = False
        
        if len(timestamps) >= 6:
            show_anti_abuse_banner = True
        else:
            timestamps.append(now)
            cache.set(cache_key, timestamps, 300)
            
            # Increment view count
            Replay.objects.filter(pk=self.object.pk).update(view_count=F('view_count') + 1)
            self.object.view_count = (self.object.view_count or 0) + 1

        context = self.get_context_data(object=self.object)
        context['show_anti_abuse_banner'] = show_anti_abuse_banner
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

        # Танки из extended_vehicle_info (содержит ВСЕ команды!)
        for avatar_id, vehicle_data in cache.extended_vehicle_info.items():
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

    def _preload_achievements(self, cache) -> dict:
        """
        Предзагружает достижения текущего игрока и данные об отметках на стволе.

        Args:
            cache: ReplayDataCache с данными реплея

        Returns:
            Словарь с ключами:
            - 'achievements_nonbattle': список небоевых достижений
            - 'achievements_battle': список боевых достижений
            - 'marks_on_gun': количество отметок на стволе (0-3)
            - 'damage_rating': процентиль урона (0-100)
        """
        # Получаем достижения с их значениями (степенями)
        achievements_with_values = cache.get_achievements_with_values()
        # print(f"Предзагрузка достижений: {achievements_with_values}")

        if not achievements_with_values:
            empty = Achievement.objects.none()
            return {
                'achievements_nonbattle': empty,
                'achievements_battle': empty,
                'marks_on_gun': cache.get_marks_on_gun(),
                'damage_rating': cache.get_damage_rating(),
            }

        # Получаем ID достижений
        ids = list(achievements_with_values.keys())

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

        # Создаём словарь achievement_id -> Achievement для быстрого доступа
        achievements_dict = {a.achievement_id: a for a in achievements}

        # Класс-обёртка для Achievement с дополнительными атрибутами
        class AchievementWithRank:
            """Обёртка для Achievement с поддержкой степени медали."""
            def __init__(self, achievement, rank=None):
                self.achievement = achievement
                self.rank = rank if isinstance(rank, int) and rank > 0 else None
                # Словарь для перевода римских цифр
                self._roman_numerals = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V'}

            def __getattr__(self, name):
                # Проксируем все атрибуты на базовый Achievement
                # Исключаем name, чтобы обработать его отдельно
                if name == 'name':
                    return self.name_with_rank
                return getattr(self.achievement, name)

            @property
            def name_with_rank(self):
                """Возвращает название медали с подставленной степенью."""
                base_name = self.achievement.name
                if self.rank is not None and '%(rank)s' in base_name:
                    # Преобразуем число в римскую цифру
                    roman = self._roman_numerals.get(self.rank, str(self.rank))
                    # Заменяем %(rank)s на "римская_цифра степени"
                    return base_name.replace('%(rank)s', f'{roman} степени')
                return base_name

            @property
            def image_big_with_rank(self):
                """Возвращает путь к изображению с учётом степени медали."""
                if self.rank is None:
                    return self.achievement.image_big

                # Словарь медалей со степенями: ID -> базовое имя файла
                RANKED_MEDALS = {
                    41: 'medalKay',      # Медаль Кея
                    42: 'medalSamokhin', # Медаль Самохина
                    43: 'medalGudz',     # Медаль Гудзя
                    44: 'medalPoppel',   # Медаль Попеля
                    45: 'medalAbrams',   # Медаль Абрамса
                    46: 'medalLeClerc',  # Медаль Леклерка
                    47: 'medalLavrinenko', # Медаль Лавриненко
                    48: 'medalEkins',    # Медаль Экинса
                    538: 'readyForBattleLT',             # Образцовое выполнение: ЛТ
                    539: 'readyForBattleMT',             # Образцовое выполнение: СТ
                    540: 'readyForBattleHT',             # Образцовое выполнение: ТТ
                    541: 'readyForBattleSPG',            # Образцовое выполнение: САУ
                    542: 'readyForBattleATSPG',          # Образцовое выполнение: ПТ-САУ
                    1215: 'readyForBattleAllianceUSSR',  # Образцовое выполнение: Союз
                    1216: 'readyForBattleAllianceGermany',  # Образцовое выполнение: Блок
                    1217: 'readyForBattleAllianceUSA',   # Образцовое выполнение: Альянс
                    1218: 'readyForBattleAllianceFrance', # Образцовое выполнение: Коалиция
                }

                medal_id = self.achievement.achievement_id
                if medal_id in RANKED_MEDALS:
                    base_name = RANKED_MEDALS[medal_id]
                    base_path = self.achievement.image_big
                    # Заменяем базовое имя на имя со степенью
                    # medalKay.png -> medalKay4.png
                    # readyForBattleHT.png -> readyForBattleHT3.png
                    if base_name in base_path:
                        return base_path.replace(f'{base_name}.png', f'{base_name}{self.rank}.png')

                return self.achievement.image_big

        # Знак классности (ID 79) добавляется отдельно в шаблоне, исключаем его из списков
        MASTERY_BADGE_ID = 79

        # ID медалей, у которых степень 1 тоже имеет значение (отдельный файл картинки)
        # Для остальных value=1 означает просто "получено", а не степень
        ALWAYS_RANKED_IDS = {
            538, 539, 540, 541, 542,           # readyForBattle (ЛТ, СТ, ТТ, САУ, ПТ-САУ)
            1215, 1216, 1217, 1218,            # readyForBattle Alliance
        }

        # Создаём обёрнутые достижения (исключая знак классности)
        wrapped_achievements = []
        for aid, value in achievements_with_values.items():
            if aid in achievements_dict and aid != MASTERY_BADGE_ID:
                ach = achievements_dict[aid]
                # Для readyForBattle степень >= 1 значима (отдельные файлы для каждой степени)
                # Для остальных медалей степень значима только если > 1
                if isinstance(value, int) and aid in ALWAYS_RANKED_IDS:
                    rank = value if value >= 1 else None
                else:
                    rank = value if isinstance(value, int) and value > 1 else None
                wrapped_achievements.append(AchievementWithRank(ach, rank))

        # Разделяем на battle и nonbattle
        # Медали с section='class' отображаются вместе с боевыми
        battle_sections = ('battle', 'epic', 'class')
        ach_battle = [a for a in wrapped_achievements if a.section in battle_sections]
        ach_nonbattle = [a for a in wrapped_achievements if a.section not in battle_sections]

        # Сортируем по Order (Active achievements)
        # Если order is None, ставим в конец (9999)
        ach_battle.sort(key=lambda a: (getattr(a, 'order', 9999) or 9999, getattr(a, 'weight', 0.0), a.name))
        ach_nonbattle.sort(key=lambda a: (getattr(a, 'order', 9999) or 9999, getattr(a, 'weight', 0.0), a.name))

        # Получаем данные об отметках на стволе
        marks_on_gun = cache.get_marks_on_gun()
        damage_rating = cache.get_damage_rating()

        logger.debug(
            f"Предзагружено достижений: {len(ach_nonbattle)} небоевых, {len(ach_battle)} боевых, "
            f"отметок на стволе: {marks_on_gun}, damageRating: {damage_rating}%"
        )

        return {
            'achievements_nonbattle': ach_nonbattle,
            'achievements_battle': ach_battle,
            'marks_on_gun': marks_on_gun,
            'damage_rating': damage_rating,
        }

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
            achievements_data = self._preload_achievements(cache)

            # Распаковываем данные достижений и отметок
            achievements_nonbattle = achievements_data['achievements_nonbattle']
            achievements_battle = achievements_data['achievements_battle']
            marks_on_gun = achievements_data['marks_on_gun']
            damage_rating = achievements_data['damage_rating']

            # Создаём контекст для кеширования промежуточных вычислений
            from replays.parser.extractor import ExtractorContext
            extractor_context = ExtractorContext(cache)

            # ============================================================
            # ЭТАП 3: ИЗВЛЕЧЕНИЕ ДАННЫХ (с использованием кеша)
            # ============================================================

            # Персональные данные (минимальный набор полей)
            context['personal_data'] = ExtractorV2.get_personal_data_minimal(cache)

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

            # Отметки на стволе
            context['marks_on_gun'] = marks_on_gun
            context['damage_rating'] = damage_rating
            context['has_marks_on_gun'] = marks_on_gun > 0

            # ЛОГИКА ОГРАНИЧЕНИЙ
            # Максимум 7 элементов: мастерство (0-1) + отметки на стволе (0-1) + обычные награды
            limit_left = 7 - int(context['has_mastery']) - int(context['has_marks_on_gun'])
            context['achievements_nonbattle'] = achievements_nonbattle[:limit_left]

            # Справа показываем строго 6 наград
            context['achievements_battle'] = achievements_battle[:6]

            # Подсчет значков (достижения + мастерство + отметки)
            context['achievements_count_in_badges'] = (
                len(achievements_nonbattle) +
                (1 if m > 0 else 0) +
                (1 if marks_on_gun > 0 else 0)
            )
            # Кол-во боевых (справа)
            context['achievements_battle_count'] = len(achievements_battle)

            # Получить данные об отметках из БД (если есть)
            marks_data = None
            marks_image_url = ''
            if marks_on_gun > 0:
                try:
                    marks_data = MarksOnGun.objects.get(marks_count=marks_on_gun)
                    # Получить нацию танка для правильного изображения
                    tank_nation = self.object.tank.nation if self.object.tank else None
                    if tank_nation and marks_data:
                        marks_image_url = marks_data.get_image_for_nation(tank_nation)
                except MarksOnGun.DoesNotExist:
                    pass

            context['marks_data'] = marks_data
            context['marks_image_url'] = marks_image_url

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

        # Добавляем информацию о лайках
        context['likes_count'] = self.object.votes.count()
        context['user_has_liked'] = False
        if self.request.user.is_authenticated:
            context['user_has_liked'] = self.object.votes.exists(self.request.user.id)

        # Видео-ссылки
        context['video_links'] = VideoLinkService.get_video_links(self.object)
        context['can_add_video'] = (
            self.request.user.is_authenticated
            and self.object.user == self.request.user
            and VideoLinkService.can_add_video(self.request.user, self.object)
        )
        context['video_form'] = VideoLinkForm()

        # Бейдж подписчика загрузившего
        uploader_plan = None
        if self.object.user:
            uploader_plan = SubscriptionService.get_user_plan(self.object.user)
        context['uploader_plan'] = uploader_plan

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
        # Проверка лимита скачиваний по подписке
        if not UsageLimitService.can_download(request.user):
            return JsonResponse({
                "success": False,
                "limit_reached": "download",
                "error": "Вы достигли дневного лимита скачиваний.",
            }, status=429)

        try:
            # Получаем объект реплея
            replay = self._get_replay_object(pk)

            # Формируем путь к файлу
            file_path = self._get_file_path(replay.file_name)

            # Валидация безопасности и существования
            self._validate_file_security(file_path)
            self._validate_file_exists(file_path)

            # Записываем факт скачивания для лимитов
            UsageLimitService.record_download(request.user)

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


class ReplayVoteView(LoginRequiredMixin, View):
    """
    API endpoint для лайков реплеев.
    Переключает лайк пользователя (добавить/убрать).
    """
    def post(self, request, pk):
        replay = get_object_or_404(Replay, pk=pk)

        # Проверяем, есть ли уже лайк от этого пользователя
        if replay.votes.exists(request.user.id):
            # Если лайк есть - удаляем (снимаем лайк)
            replay.votes.delete(request.user.id)
            liked = False
        else:
            # Если лайка нет - добавляем
            replay.votes.up(request.user.id)
            liked = True

        # Возвращаем JSON с обновленными данными
        return JsonResponse({
            'liked': liked,
            'likes_count': replay.votes.count()
        })
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_replay_info(request):
    """
    API endpoint that returns replay information by URL.
    Expects 'url' query parameter.
    """
    obj, created = APIUsageLog.objects.get_or_create(
        user=request.user, endpoint='api_replay_info',
    )
    if not created:
        APIUsageLog.objects.filter(pk=obj.pk).update(call_count=F('call_count') + 1)
    else:
        APIUsageLog.objects.filter(pk=obj.pk).update(call_count=1)

    url = request.GET.get('url')
    if not url:
        return Response({"error": "URL parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

    video_id = None
    # Attempt to parse ID from URL like https://lesta-replays.ru/replays/13941/
    try:
        if '/replays/' in url:
            parts = url.strip('/').split('/')
            for part in reversed(parts):
                if part.isdigit():
                    video_id = int(part)
                    break
    except Exception:
        pass

    if not video_id:
        return Response({"error": "Could not parse Replay ID from URL"}, status=status.HTTP_400_BAD_REQUEST)

    replay = get_object_or_404(Replay, pk=video_id)

    map_name = replay.map_display_name
    if not map_name and replay.map:
        map_name = replay.map.map_display_name

    data = {
        "id": replay.id,
        "damage": replay.damage,
        "kills": replay.kills,
        "xp": replay.xp,
        "credits": replay.credits,
        "player_name": replay.owner.real_name if replay.owner else "Unknown",
        "player_id": replay.owner.accountDBID if replay.owner else None,
        "vehicle": replay.tank.name if replay.tank else "Unknown",
        "map": map_name,
        "battle_date": replay.battle_date,
    }
    return Response(data)


class SubscriptionInfoView(TemplateView):
    """Страница с описанием тарифных планов."""
    template_name = 'replays/subscription.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['plans'] = SubscriptionPlan.objects.filter(is_active=True).order_by('price_monthly')
        return context


class AddVideoLinkView(LoginRequiredMixin, View):
    """Добавление видео-ссылки к реплею."""

    def post(self, request, pk):
        replay = get_object_or_404(Replay, pk=pk)

        # Проверяем, что пользователь — владелец реплея (загрузивший)
        if replay.user != request.user:
            return JsonResponse({'success': False, 'error': 'Только загрузивший реплей может добавлять видео.'}, status=403)

        # Проверяем лимит по подписке
        if not VideoLinkService.can_add_video(request.user, replay):
            return JsonResponse({
                'success': False,
                'error': 'Вы достигли лимита видео-ссылок для вашего плана подписки.',
            }, status=403)

        form = VideoLinkForm(request.POST)
        if form.is_valid():
            link = VideoLinkService.add_video_link(
                user=request.user,
                replay=replay,
                platform=form.cleaned_data['platform'],
                url=form.cleaned_data['url'],
            )
            return JsonResponse({
                'success': True,
                'link': {
                    'id': link.id,
                    'platform': link.get_platform_display(),
                    'url': link.url,
                    'icon_class': link.icon_class,
                    'color_class': link.color_class,
                },
            })

        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


class RemoveVideoLinkView(LoginRequiredMixin, View):
    """Удаление видео-ссылки."""

    def post(self, request, pk):
        link = get_object_or_404(ReplayVideoLink, pk=pk)

        if link.added_by != request.user:
            return JsonResponse({'success': False, 'error': 'Нет прав на удаление.'}, status=403)

        link.delete()
        return JsonResponse({'success': True})


class UploadAvatarView(LoginRequiredMixin, View):
    """Загрузка аватара пользователя."""

    def post(self, request):
        plan = SubscriptionService.get_user_plan(request.user)
        if not plan.can_upload_avatar:
            return JsonResponse({
                'success': False,
                'error': 'Загрузка аватара доступна только для подписчиков.',
            }, status=403)

        form = AvatarUploadForm(request.POST, request.FILES)
        if form.is_valid():
            profile = request.user.profile
            # Удаляем старый аватар если есть
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = form.cleaned_data['avatar']
            profile.save()
            return JsonResponse({
                'success': True,
                'avatar_url': profile.avatar.url,
            })

        # Собираем ошибки валидации в читаемую строку
        error_messages = []
        for field_errors in form.errors.values():
            error_messages.extend(field_errors)
        return JsonResponse({
            'success': False,
            'error': ' '.join(error_messages) or 'Ошибка загрузки файла.',
        }, status=400)


class DeleteAvatarView(LoginRequiredMixin, View):
    """Удаление аватара пользователя."""

    def post(self, request):
        profile = request.user.profile
        if profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = None
            profile.save()
        return JsonResponse({'success': True})


# ==================== ПРОФИЛЬ ====================

class ProfileReplaysView(MyReplaysView):
    """Вкладка 'Мои реплеи' в профиле."""
    template_name = 'replays/profile_replays.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'replays'
        context['profile'] = getattr(self.request.user, 'profile', None)
        return context


class ProfileStatsView(LoginRequiredMixin, ListView):
    """Вкладка 'Статистика' в профиле пользователя."""

    model = ReplayStatBattle
    template_name = 'replays/profile_stats.html'
    context_object_name = 'items'
    paginate_by = 25

    ALLOWED_PAGE_SIZES = [25, 50, 100]
    SORTABLE_FIELDS = {
        'battle_date',
        'map_display_name',
        'outcome',
        'players_count',
        'avg_damage',
        'total_damage',
    }

    def _can_use_stats(self) -> bool:
        return SubscriptionService.is_pro(self.request.user)

    def get_paginate_by(self, queryset=None):
        try:
            per_page = int(self.request.GET.get('per_page', self.paginate_by))
            if per_page in self.ALLOWED_PAGE_SIZES:
                return per_page
        except (TypeError, ValueError):
            pass
        return self.paginate_by

    def get_queryset(self):
        if not self._can_use_stats():
            return ReplayStatBattle.objects.none()

        raw_qs = ReplayStatBattle.objects.filter(user=self.request.user)

        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            parsed = parse_date(date_from)
            if parsed:
                raw_qs = raw_qs.filter(battle_date__date__gte=parsed)
        if date_to:
            parsed = parse_date(date_to)
            if parsed:
                raw_qs = raw_qs.filter(battle_date__date__lte=parsed)

        qs = (
            raw_qs
            .values('battle_signature', 'battle_date', 'map_name', 'map_display_name', 'outcome')
            .annotate(
                players_count=Count('players', distinct=True),
                avg_damage=Coalesce(
                    Cast(Avg('players__damage'), output_field=IntegerField()),
                    Value(0),
                    output_field=IntegerField(),
                ),
                total_damage=Coalesce(
                    Cast(Sum('players__damage'), output_field=IntegerField()),
                    Value(0),
                    output_field=IntegerField(),
                ),
            )
        )

        sort = (self.request.GET.get('sort') or '').strip()
        direction = (self.request.GET.get('dir') or 'desc').lower()
        if sort in self.SORTABLE_FIELDS:
            order = sort if direction == 'asc' else f'-{sort}'
            qs = qs.order_by(order, '-battle_date', '-battle_signature')
        else:
            qs = qs.order_by('-battle_date', '-battle_signature')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'stats'
        context['profile'] = getattr(self.request.user, 'profile', None)
        context['can_use_stats'] = self._can_use_stats()

        q = self.request.GET.copy()
        q.pop('page', None)
        page_qs = q.urlencode()
        context['page_qs'] = page_qs
        context['page_qs_prefix'] = f'{page_qs}&' if page_qs else ''

        current_sort = (self.request.GET.get('sort') or '').strip()
        current_dir = (self.request.GET.get('dir') or 'desc').lower()
        next_dir = {}
        for field in self.SORTABLE_FIELDS:
            if current_sort == field and current_dir == 'desc':
                next_dir[field] = 'asc'
            else:
                next_dir[field] = 'desc'

        q_without_page = self.request.GET.copy()
        q_without_page.pop('page', None)
        q_without_page.pop('per_page', None)
        context['base_qs_without_per_page'] = q_without_page.urlencode()
        context['allowed_page_sizes'] = self.ALLOWED_PAGE_SIZES
        context['current_per_page'] = self.get_paginate_by(None)
        context['current_sort'] = current_sort
        context['current_dir'] = current_dir
        context['next_dir'] = next_dir
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')

        export_q = self.request.GET.copy()
        for key in ('page', 'per_page', 'sort', 'dir'):
            export_q.pop(key, None)
        export_qs = export_q.urlencode()
        context['export_url'] = reverse('profile_stats_export')
        if export_qs:
            context['export_url'] += f'?{export_qs}'

        return context


class ReplayStatsExportView(LoginRequiredMixin, View):
    """Экспорт статистики в XLSX в формате матрицы Игрок x Бой."""

    OUTCOME_LABELS = {
        ReplayStatBattle.OUTCOME_WIN: "Победа",
        ReplayStatBattle.OUTCOME_LOSS: "Поражение",
        ReplayStatBattle.OUTCOME_DRAW: "Ничья",
    }
    HEADER_STYLE_DEFAULT = 1
    HEADER_STYLE_WIN = 2
    HEADER_STYLE_LOSS = 3
    HEADER_STYLE_DRAW = 4

    @staticmethod
    def _pro_required_response(request: HttpRequest):
        messages.error(request, "Статистика доступна только для подписчиков ПРО.")
        return redirect('subscription_info')

    @staticmethod
    def _column_name(index: int) -> str:
        """1 -> A, 26 -> Z, 27 -> AA."""
        chars = []
        while index > 0:
            index, rem = divmod(index - 1, 26)
            chars.append(chr(65 + rem))
        return ''.join(reversed(chars))

    @staticmethod
    def _xml_cell(ref: str, value: Any, style_idx: int | None = None) -> str:
        if value is None or value == "":
            return ""
        style_attr = f' s="{style_idx}"' if style_idx is not None else ""
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
        text = escape(str(value))
        return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{text}</t></is></c>'

    @staticmethod
    def _format_outcome_label(outcome: str) -> str:
        return ReplayStatsExportView.OUTCOME_LABELS.get(outcome, "Результат")

    @staticmethod
    def _format_battle_column_title(battle_date, map_display_name: str, map_name: str, outcome: str) -> str:
        dt_value = battle_date
        if battle_date is not None and timezone.is_aware(battle_date):
            dt_value = timezone.localtime(battle_date)
        dt_label = dt_value.strftime("%d.%m.%Y %H:%M") if dt_value else "Без даты"
        map_label = map_display_name or map_name or "Карта неизвестна"
        outcome_label = ReplayStatsExportView._format_outcome_label(outcome)
        return f"{dt_label}\n{map_label}\n{outcome_label}"

    @classmethod
    def _header_style_for_outcome(cls, outcome: str | None) -> int:
        if outcome == ReplayStatBattle.OUTCOME_WIN:
            return cls.HEADER_STYLE_WIN
        if outcome == ReplayStatBattle.OUTCOME_LOSS:
            return cls.HEADER_STYLE_LOSS
        if outcome == ReplayStatBattle.OUTCOME_DRAW:
            return cls.HEADER_STYLE_DRAW
        return cls.HEADER_STYLE_DEFAULT

    @staticmethod
    def _estimate_column_widths(table: List[List[Any]]) -> List[float]:
        if not table:
            return []

        column_count = max(len(row) for row in table)
        widths: List[float] = []
        for col_idx in range(column_count):
            max_len = 0
            for row in table:
                if col_idx >= len(row):
                    continue
                value = row[col_idx]
                if value is None:
                    continue
                text = str(value)
                lines = text.splitlines() or [text]
                line_len = max(len(line) for line in lines) if lines else 0
                if line_len > max_len:
                    max_len = line_len

            # Приближение ширины колонки Excel.
            width = min(80.0, max(10.0, float(max_len + 2)))
            widths.append(width)
        return widths

    def _build_export_table(self, request) -> tuple[List[List[Any]], List[str | None]]:
        qs = ReplayStatPlayer.objects.filter(battle__user=request.user).order_by(
            'battle__battle_date', 'battle__battle_signature', 'player_name', 'id'
        )

        selected_battle_signatures = [
            value.strip()
            for value in request.GET.getlist('battle_signature')
            if value and value.strip()
        ]
        if selected_battle_signatures:
            qs = qs.filter(battle__battle_signature__in=selected_battle_signatures)

        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        if date_from:
            parsed = parse_date(date_from)
            if parsed:
                qs = qs.filter(battle__battle_date__date__gte=parsed)
        if date_to:
            parsed = parse_date(date_to)
            if parsed:
                qs = qs.filter(battle__battle_date__date__lte=parsed)

        entries = qs.values(
            'battle__battle_signature',
            'battle__battle_date',
            'battle__map_display_name',
            'battle__map_name',
            'battle__outcome',
            'player_account_id',
            'player_name',
            'damage',
        )

        rows = list(entries)
        if not rows:
            table = [
                ["", "Бой\nКарта\nРезультат", "Средний урон"],
                ["Нет данных", "", 0],
                ["Итог: побед 0 из 0 боев", "", ""],
            ]
            header_outcomes = [None, None, None]
            return table, header_outcomes

        battles: "OrderedDict[str, Dict[str, str]]" = OrderedDict()
        for row in rows:
            signature = row['battle__battle_signature']
            if signature not in battles:
                battles[signature] = {
                    "title": self._format_battle_column_title(
                        battle_date=row.get('battle__battle_date'),
                        map_display_name=row.get('battle__map_display_name') or "",
                        map_name=row.get('battle__map_name') or "",
                        outcome=row.get('battle__outcome') or "",
                    ),
                    "outcome": row.get('battle__outcome') or "",
                }

        players: "OrderedDict[tuple[int, str], Dict[str, int]]" = OrderedDict()
        for row in rows:
            key = (row['player_account_id'], row['player_name'])
            if key not in players:
                players[key] = {}
            players[key][row['battle__battle_signature']] = int(row['damage'] or 0)

        header = [""] + [item["title"] for item in battles.values()] + ["Средний урон"]
        table: List[List[Any]] = [header]
        battle_keys = list(battles.keys())

        for (_, player_name), damage_map in players.items():
            row_values = [damage_map.get(signature, "") for signature in battle_keys]
            present_values = [value for value in row_values if value != ""]
            avg_damage = round(sum(present_values) / len(present_values)) if present_values else 0
            table.append([player_name] + row_values + [avg_damage])

        wins_count = sum(
            1
            for item in battles.values()
            if item.get("outcome") == ReplayStatBattle.OUTCOME_WIN
        )
        battles_count = len(battles)
        table.append([f"Итог: побед {wins_count} из {battles_count} боев"] + [""] * battles_count + [""])

        header_outcomes = [None] + [item.get("outcome") for item in battles.values()] + [None]
        return table, header_outcomes

    def _build_xlsx_bytes(self, table: List[List[Any]], header_outcomes: List[str | None] | None = None) -> bytes:
        column_widths = self._estimate_column_widths(table)
        cols_xml = "".join(
            f'<col min="{idx}" max="{idx}" width="{width:.2f}" customWidth="1"/>'
            for idx, width in enumerate(column_widths, start=1)
        )
        cols_block = f"<cols>{cols_xml}</cols>" if cols_xml else ""

        # Формируем sheet XML
        rows_xml = []
        for row_idx, row in enumerate(table, start=1):
            cells = []
            row_attrs = f' r="{row_idx}"'
            if row_idx == 1:
                row_attrs += ' ht="48" customHeight="1"'
            for col_idx, value in enumerate(row, start=1):
                ref = f"{self._column_name(col_idx)}{row_idx}"
                style_idx = None
                if row_idx == 1:
                    outcome = None
                    if header_outcomes and col_idx - 1 < len(header_outcomes):
                        outcome = header_outcomes[col_idx - 1]
                    style_idx = self._header_style_for_outcome(outcome)
                cell_xml = self._xml_cell(ref, value, style_idx=style_idx)
                if cell_xml:
                    cells.append(cell_xml)
            rows_xml.append(f'<row{row_attrs}>{"".join(cells)}</row>')

        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'{cols_block}'
            '<sheetData>'
            f'{"".join(rows_xml)}'
            '</sheetData>'
            '</worksheet>'
        )

        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )

        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            '</Relationships>'
        )

        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Статистика" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        )

        workbook_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
            '</Relationships>'
        )

        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2">'
            '<font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/></font>'
            '<font><b/><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/></font>'
            '</fonts>'
            '<fills count="6">'
            '<fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/><bgColor indexed="64"/></patternFill></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/><bgColor indexed="64"/></patternFill></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFE2E8F0"/><bgColor indexed="64"/></patternFill></fill>'
            '</fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="5">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="5" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="center" horizontal="center"/>'
            '</xf>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="center" horizontal="center"/>'
            '</xf>'
            '<xf numFmtId="0" fontId="1" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="center" horizontal="center"/>'
            '</xf>'
            '<xf numFmtId="0" fontId="1" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
            '<alignment wrapText="1" vertical="center" horizontal="center"/>'
            '</xf>'
            '</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )

        output = BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('[Content_Types].xml', content_types_xml)
            archive.writestr('_rels/.rels', rels_xml)
            archive.writestr('xl/workbook.xml', workbook_xml)
            archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels_xml)
            archive.writestr('xl/styles.xml', styles_xml)
            archive.writestr('xl/worksheets/sheet1.xml', sheet_xml)

        return output.getvalue()

    def get(self, request):
        if not SubscriptionService.is_pro(request.user):
            return self._pro_required_response(request)

        table, header_outcomes = self._build_export_table(request)
        file_bytes = self._build_xlsx_bytes(table, header_outcomes=header_outcomes)
        filename = f"replay_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        response = HttpResponse(
            file_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ReplayStatsBatchUploadView(LoginRequiredMixin, View):
    """Загрузка реплеев для сбора статистики без сохранения файла/payload."""

    MAX_FILES_PER_REQUEST = 20

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stats_service = ReplayStatsProcessingService()

    def handle_no_permission(self):
        request = getattr(self, 'request', None)
        if request and self._is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': 'Для загрузки статистики необходимо авторизоваться.',
                'redirect_url': f"{settings.LOGIN_URL}?next={request.path}",
            }, status=403)
        return super().handle_no_permission()

    @staticmethod
    def _is_ajax_request(request: HttpRequest) -> bool:
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def post(self, request: HttpRequest):
        if not SubscriptionService.is_pro(request.user):
            return self._pro_required_response(request)

        files = request.FILES.getlist('files') or []
        if not files:
            return self._error_response(request, "Файлы не выбраны.")

        if len(files) > self.MAX_FILES_PER_REQUEST:
            return self._error_response(
                request,
                f"За один запрос можно загрузить не более {self.MAX_FILES_PER_REQUEST} файлов.",
            )

        results: List[Dict[str, Any]] = []
        for file in files:
            file_result = {'file': file.name}

            validation_error = ReplayFileValidator.validate(file)
            if validation_error:
                file_result.update({
                    'ok': False,
                    'status': 'error',
                    'error': validation_error,
                })
                results.append(file_result)
                continue

            try:
                process_result = self.stats_service.process_replay(file, request.user)
                created_rows = process_result.get('created_rows', 0)
                duplicate_rows = process_result.get('duplicate_rows', 0)
                total_rows = process_result.get('total_rows', 0)

                if created_rows > 0:
                    file_result.update({
                        'ok': True,
                        'status': 'created',
                        'rows_created': created_rows,
                        'rows_duplicates': duplicate_rows,
                        'rows_total': total_rows,
                    })
                else:
                    file_result.update({
                        'ok': True,
                        'status': 'duplicate',
                        'rows_created': created_rows,
                        'rows_duplicates': duplicate_rows,
                        'rows_total': total_rows,
                    })
            except ParseError as e:
                file_result.update({
                    'ok': False,
                    'status': 'error',
                    'error': str(e),
                })
            except ValidationError as e:
                message = "; ".join(e.messages) if getattr(e, 'messages', None) else str(e)
                file_result.update({
                    'ok': False,
                    'status': 'error',
                    'error': message,
                })
            except Exception as e:
                logger.exception(f"[STATS-UPLOAD] Ошибка обработки файла {file.name}: {e}")
                file_result.update({
                    'ok': False,
                    'status': 'error',
                    'error': 'Не удалось обработать файл.',
                })

            results.append(file_result)

        created_count = sum(1 for row in results if row.get('status') == 'created')
        duplicate_count = sum(1 for row in results if row.get('status') == 'duplicate')
        error_count = sum(1 for row in results if row.get('status') == 'error')
        summary = {
            'processed': len(files),
            'created': created_count,
            'duplicates': duplicate_count,
            'errors': error_count,
        }

        if self._is_ajax_request(request):
            return JsonResponse({
                'success': True,
                'summary': summary,
                'results': results,
                'redirect_url': reverse('profile_stats'),
            })

        if created_count:
            messages.success(request, f"Добавлено статистических записей: {created_count}")
        if duplicate_count:
            messages.info(request, f"Дубликатов пропущено: {duplicate_count}")
        if error_count:
            messages.error(request, f"Ошибок обработки: {error_count}")

        return redirect('profile_stats')

    def _error_response(self, request: HttpRequest, message: str):
        if self._is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': message,
                'redirect_url': reverse('profile_stats'),
            }, status=400)

        messages.error(request, message)
        return redirect('profile_stats')

    def _pro_required_response(self, request: HttpRequest):
        message = "Статистика доступна только для подписчиков ПРО."
        if self._is_ajax_request(request):
            return JsonResponse({
                'success': False,
                'error': message,
                'redirect_url': reverse('subscription_info'),
            }, status=403)

        messages.error(request, message)
        return redirect('subscription_info')


class ProfileSubscriptionView(LoginRequiredMixin, TemplateView):
    """Вкладка 'Подписка' в профиле."""
    template_name = 'replays/profile_subscription.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'subscription'
        context['plans'] = SubscriptionPlan.objects.filter(is_active=True).order_by('price_monthly')
        context['profile'] = getattr(self.request.user, 'profile', None)
        return context


class ProfileSettingsView(LoginRequiredMixin, TemplateView):
    """Вкладка 'Настройки профиля'."""
    template_name = 'replays/profile_settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'settings'
        context['profile'] = getattr(self.request.user, 'profile', None)
        context['username_form'] = context.get('username_form', UsernameChangeForm(user=self.request.user))
        context['can_upload_avatar'] = SubscriptionService.get_user_plan(self.request.user).can_upload_avatar
        try:
            from allauth.socialaccount.models import SocialAccount
            context['social_accounts'] = SocialAccount.objects.filter(user=self.request.user)
        except ImportError:
            context['social_accounts'] = []
        return context

    def post(self, request, *args, **kwargs):
        form = UsernameChangeForm(request.POST, user=request.user)
        if form.is_valid():
            request.user.username = form.cleaned_data['username']
            request.user.save(update_fields=['username'])
            messages.success(request, 'Никнейм успешно изменён.')
            return redirect('profile_settings')
        context = self.get_context_data(username_form=form)
        return self.render_to_response(context)


class PlayerStatsAPIView(View):
    """API endpoint для получения статистики игрока с Lesta API."""

    LESTA_API_BASE = "https://api.tanki.su/wot"
    CACHE_TIMEOUT = 600  # 10 минут

    def get(self, request, account_id):
        from django.core.cache import cache
        import requests
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if account_id <= 0:
            return JsonResponse({"error": "Некорректный ID игрока"}, status=400)

        cache_key = f"player_stats_{account_id}"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse(cached)

        app_id = settings.LESTA_APPLICATION_ID
        if not app_id:
            return JsonResponse({"error": "Lesta API не настроен"}, status=500)

        endpoints = {
            "info": f"{self.LESTA_API_BASE}/account/info/?application_id={app_id}&account_id={account_id}&extra=statistics.random",
            "tanks": f"{self.LESTA_API_BASE}/account/tanks/?application_id={app_id}&account_id={account_id}",
            "achievements": f"{self.LESTA_API_BASE}/account/achievements/?application_id={app_id}&account_id={account_id}",
        }

        results = {}

        def fetch(key, url):
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "ok":
                    return key, data["data"].get(str(account_id))
            except Exception as e:
                logger.warning(f"Lesta API error ({key}): {e}")
            return key, None

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(fetch, k, v) for k, v in endpoints.items()]
            for future in as_completed(futures):
                key, data = future.result()
                results[key] = data

        if not results.get("info"):
            return JsonResponse({"error": "Игрок не найден"}, status=404)

        # Загрузка данных клана (если есть)
        clan_data = None
        clan_id = results["info"].get("clan_id")
        if clan_id:
            try:
                clan_url = f"{self.LESTA_API_BASE}/clans/info/?application_id={app_id}&clan_id={clan_id}&fields=tag,name,color,emblems,clan_id,members"
                resp = requests.get(clan_url, timeout=5)
                resp.raise_for_status()
                cdata = resp.json()
                if cdata.get("status") == "ok":
                    clan_info = cdata["data"].get(str(clan_id))
                    if clan_info:
                        # Извлекаем данные участника (роль, дата вступления)
                        member_info = None
                        for m in clan_info.get("members", []):
                            if m.get("account_id") == account_id:
                                member_info = m
                                break
                        clan_info.pop("members", None)
                        clan_data = clan_info
                        if member_info:
                            clan_data["member"] = member_info
            except Exception as e:
                logger.warning(f"Lesta Clans API error: {e}")

        # Обогащаем достижения данными из БД (иконки, названия, описания)
        raw_achievements = results.get("achievements") or {}
        ach_counts = raw_achievements.get("achievements") or {}
        if ach_counts:
            from replays.models import Achievement as AchModel
            db_achs = AchModel.objects.filter(token__in=ach_counts.keys()).values(
                'token', 'name', 'description', 'image_small', 'image_big', 'section', 'order'
            )
            db_map = {a['token']: a for a in db_achs}
            enriched = []
            for token, count in ach_counts.items():
                if count and count > 0 and token in db_map:
                    a = db_map[token]
                    enriched.append({
                        'token': token,
                        'count': count,
                        'name': a['name'],
                        'description': a['description'],
                        'image_small': a['image_small'],
                        'image_big': a['image_big'],
                        'section': a['section'],
                        'order': a['order'] or 0,
                    })
            enriched.sort(key=lambda x: x['order'])
        else:
            enriched = []

        response_data = {
            "info": results["info"],
            "tanks": results.get("tanks"),
            "achievements": enriched,
            "clan": clan_data,
        }

        cache.set(cache_key, response_data, self.CACHE_TIMEOUT)
        return JsonResponse(response_data)


class VehicleEncyclopediaAPIView(View):
    """API endpoint для справочника танков (кешируется на 24 часа)."""

    CACHE_TIMEOUT = 86400  # 24 часа

    def get(self, request):
        from django.core.cache import cache
        import requests

        cache_key = "vehicle_encyclopedia"
        cached = cache.get(cache_key)
        if cached:
            return JsonResponse(cached, safe=False)

        app_id = settings.LESTA_APPLICATION_ID
        if not app_id:
            return JsonResponse({"error": "Lesta API не настроен"}, status=500)

        url = (
            f"https://api.tanki.su/wot/encyclopedia/vehicles/"
            f"?application_id={app_id}&fields=tank_id,name,tier,type,nation&limit=1000"
        )

        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "ok":
                result = data["data"]
                cache.set(cache_key, result, self.CACHE_TIMEOUT)
                return JsonResponse(result)
        except Exception as e:
            logger.warning(f"Lesta encyclopedia API error: {e}")

        return JsonResponse({"error": "Не удалось загрузить справочник"}, status=502)
