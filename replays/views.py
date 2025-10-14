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
from django.db.models import Q, F, Count, OuterRef, Subquery, IntegerField, CharField, Value
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


class ReplayBatchUploadView(View):
    """
    Пакетная загрузка .mtreplay файлов.
    Принимает несколько файлов, валидирует и создаёт Replay по каждому.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.replay_service = ReplayProcessingService()
        self.error_handler = ReplayErrorHandler()

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
    def _is_ajax_request(request: HttpRequest) -> bool:
        """Проверяет, является ли запрос AJAX."""
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

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
    template_name = 'replays/my_replays.html'

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Мои реплеи"
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

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
            # Парсим данные реплея
            replay_data = self.object.payload

            # === Персональные данные ===
            personal_data = ExtractorV2.get_personal_data(replay_data)
            context['personal_data'] = personal_data

            # === ДОСТИЖЕНИЯ ===
            achievements_ids = ExtractorV2.get_achievements(replay_data)
            # print(f"achievements_ids: {achievements_ids}")
            if achievements_ids:
                ach_nonbattle, ach_battle = ExtractorV2.split_achievements_by_section(achievements_ids)

                context['achievements_nonbattle'] = ach_nonbattle
                context['achievements_battle'] = ach_battle

                # мастерство — как и было
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

                # сколько значков показать в «бейджах»
                context['achievements_count_in_badges'] = ach_nonbattle.count() + (1 if m > 0 else 0)
                context['achievements_battle_count'] = ach_battle.count()

            else:
                context['achievements_nonbattle'] = Achievement.objects.none()
                context['achievements_battle'] = Achievement.objects.none()
                context['achievements_count_in_badges'] = 0

            details = ExtractorV2.get_details_data(replay_data)
            context['details'] = details

            interactions = ExtractorV2.get_player_interactions(replay_data)
            # print(f"interactions: {interactions}")
            context["interactions"] = interactions


            interaction_rows = ExtractorV2.build_interaction_rows(replay_data)
            # print(f"interaction_rows: {interaction_rows}")
            context["interaction_rows"] = interaction_rows

            interactions_summary = ExtractorV2.build_interactions_summary(interaction_rows)
            # print(f"interactions_summary: {interactions_summary}")
            context["interactions_summary"] = interactions_summary

            context['death_reason_text'] = ExtractorV2.get_death_text(replay_data)

            context['income'] = ExtractorV2.build_income_summary(replay_data)

            context["battle_type_label"] = ExtractorV2.get_battle_type_label(replay_data)

            context["battle_outcome"] = ExtractorV2.get_battle_outcome(replay_data)

            context['team_results'] = ExtractorV2.get_team_results(replay_data)

            context['detailed_report'] = ExtractorV2.get_detailed_report(replay_data)

        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Ошибка парсинга реплея {self.object.id}: {str(e)}")
            context['parse_error'] = f"Ошибка обработки данных реплея: {str(e)}"

        return context

    # def _get_result_class(self, result: str) -> str:
    #     """Возвращает CSS класс для результата боя"""
    #     return {
    #         'victory': 'victory',
    #         'defeat': 'defeat',
    #         'draw': 'draw'
    #     }.get(result, 'unknown')
    #
    # def _get_survival_status(self, death_reason: int) -> dict:
    #     """Определяет статус выживания"""
    #     if death_reason == -1:
    #         return {'status': 'survived', 'text': 'Выжил', 'class': 'survived'}
    #     else:
    #         return {'status': 'died', 'text': 'Погиб', 'class': 'died'}
    #
    # def _calculate_hit_efficiency(self, data: dict) -> dict:
    #     """Вычисляет эффективность стрельбы"""
    #     shots = data.get('shots', 0)
    #     hits = data.get('direct_hits', 0)
    #     piercings = data.get('piercings', 0)
    #
    #     return {
    #         'hit_rate': data.get('hit_rate', 0),
    #         'penetration_rate': round((piercings / hits * 100), 2) if hits > 0 else 0,
    #         'shots_per_hit': round(shots / hits, 2) if hits > 0 else 0,
    #     }
    #
    # def _calculate_damage_efficiency(self, data: dict) -> dict:
    #     """Вычисляет эффективность урона"""
    #     damage = data.get('damage_dealt', 0)
    #     shots = data.get('shots', 0)
    #     max_hp = data.get('max_health', 1)
    #
    #     return {
    #         'damage_per_shot': round(damage / shots, 1) if shots > 0 else 0,
    #         'damage_ratio': data['battle_performance']['damage_ratio'],
    #         'assist_ratio': round(data.get('total_assist', 0) / damage * 100, 1) if damage > 0 else 0,
    #     }
    #
    # def _calculate_armor_efficiency(self, data: dict) -> dict:
    #     """Вычисляет эффективность брони"""
    #     potential = data.get('potential_damage_received', 0)
    #     received = data.get('damage_received', 0)
    #     blocked = data.get('total_blocked_damage', 0)
    #
    #     return {
    #         'damage_blocked': blocked,
    #         'armor_use_ratio': round(blocked / potential * 100, 1) if potential > 0 else 0,
    #         'ricochets': data.get('ricochets_received', 0),
    #         'bounces': data.get('bounces_received', 0),
    #     }
    #
    # def _prepare_enemy_list(self, enemy_stats: dict) -> list:
    #     """Подготавливает список противников для отображения"""
    #     enemies = []
    #     for enemy_id, stats in enemy_stats.items():
    #         if stats['damage_dealt'] > 0 or stats['target_kills'] > 0:
    #             enemy_info = stats.get('enemy_vehicle_info', {})
    #             enemies.append({
    #                 'id': enemy_id,
    #                 'damage': stats['damage_dealt'],
    #                 'hits': stats['direct_hits'],
    #                 'piercings': stats['piercings'],
    #                 'kills': stats['target_kills'],
    #                 'crits': stats['crits_total'],
    #                 'is_killed': enemy_info.get('is_dead', False) if enemy_info else False,
    #                 'max_hp': enemy_info.get('max_health', 0) if enemy_info else 0,
    #             })
    #     return sorted(enemies, key=lambda x: x['damage'], reverse=True)
    #
    # def _calculate_performance_rating(self, data: dict) -> dict:
    #     """Вычисляет общую оценку эффективности с готовыми процентами"""
    #     damage_rating = min(data.get('damage_dealt', 0) / 1000, 5.0)
    #     survival_rating = 1.0 if data.get('survival_status') == -1 else 0.0)
    #     assist_rating = min(data.get('total_assist', 0) / 500, 2.0)
    #     armor_rating = min(data.get('total_blocked_damage', 0) / 1000, 2.0)
    #
    #     total_rating = damage_rating + survival_rating + assist_rating + armor_rating
    #
    #     return {
    #         'total': round(total_rating, 1),
    #         'max': 10.0,
    #         'percentage': round(total_rating / 10.0 * 100, 1),
    #         'components': {
    #             'damage': {
    #                 'value': round(damage_rating, 1),
    #                 'max': 5.0,
    #                 'percentage': round(damage_rating / 5.0 * 100, 1),
    #             },
    #             'survival': {
    #                 'value': round(survival_rating, 1),
    #                 'max': 1.0,
    #                 'percentage': round(survival_rating * 100, 1),
    #             },
    #             'assist': {
    #                 'value': round(assist_rating, 1),
    #                 'max': 2.0,
    #                 'percentage': round(assist_rating / 2.0 * 100, 1),
    #             },
    #             'armor': {
    #                 'value': round(armor_rating, 1),
    #                 'max': 2.0,
    #                 'percentage': round(armor_rating / 2.0 * 100, 1),
    #             },
    #         }
    #     }


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
