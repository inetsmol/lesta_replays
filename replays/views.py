from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any, Dict

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.dateparse import parse_date
from django.views.generic import ListView

from .models import Replay, Tank, Nation
from .utils import extract_all_json_from_mtreplay

FILES_DIR = Path(settings.MEDIA_ROOT)
FILES_DIR.mkdir(parents=True, exist_ok=True)


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


def _extract_wot_brief_for_list(data: dict) -> dict:
    # короткий tag техники без префикса до '-'
    pv_full = data.get("playerVehicle", "")
    player_vehicle = pv_full.split("-", 1)[1] if "-" in pv_full else pv_full

    # в personal есть числовой ключ техники (у тебя это "23041")
    personal = data.get("personal", {})
    veh_keys = [k for k in personal.keys() if isinstance(k, str) and k.isdigit()]
    p = personal[veh_keys[0]] if veh_keys else {}

    # базовые поля
    mastery = p.get("markOfMastery")            # 3
    credits = p.get("credits", 0)               # 22541
    xp = p.get("xp", 0)                         # 2318
    kills = p.get("kills", 0)                   # 6
    damage = p.get("damageDealt", 0)            # 2255
    block = p.get("damageBlockedByArmor", 0)    # 0

    # ассист: суммирую явные компоненты (если нужно по-другому — скажи)
    assist = (
        p.get("damageAssistedTrack", 0)
        + p.get("damageAssistedRadio", 0)
        + p.get("damageAssistedStun", 0)
        + p.get("damageAssistedSmoke", 0)
        + p.get("damageAssistedInspire", 0)
    )

    tank = Tank.objects.only("level", "type", "nation").get(vehicleId=player_vehicle)

    return {
        "mastery": mastery,
        "level": tank.level,
        "type": tank.type,
        "nation": tank.get_nation_display(),
        "playerVehicle": player_vehicle,  # 'R174_BT-5'
        "vehicleName": tank.name,
        "date_cont": data.get("dateTime"),      # '25.08.2025 15:57:56'
        "mapName": data.get("mapName"),         # '04_himmelsdorf'
        "mapDisplayName": data.get("mapDisplayName"),  # 'Химмельсдорф'
        "credits": credits,          # 22541
        "xp": xp,                    # 2318
        "kills": kills,              # 6
        "damage": damage,            # 2255
        "assist": assist,            # 22
        "block": block,              # 0
    }


def _extract_replay_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Извлекает и нормализует данные из payload реплея"""
    p = payload

    # Извлекаем данные с fallback значениями
    """
      "regionCode": "RU",
        "playerName": "unknowns2002",
      "mapDisplayName": "Химмельсдорф",
        "mapName": "04_himmelsdorf",
        
      mastery
        level
        type
        
        "playerVehicle": "ussr-R174_BT-5",
        
        title  
                      
        date-cont

        
        credits
        xp
        kills
        damage
        assist
        block  
    
    """
    map_data = {
        'mapDisplayName': p.get('mapDisplayName'),
        'mapName': p.get('mapName') or "Unknown map"
    }

    vehicle_data = {
        'name': p.get('playerVehicle'),
        'vehicleDisplayName': p.get('vehicleDisplayName'),
        'level': p.get('level'),
        'type': p.get('vehicle', {}).get('type') or p.get('type'),
        'tier': p.get('vehicle', {}).get('tier') or p.get('vehicle', {}).get('level'),
        'premium': p.get('vehicle', {}).get('premium') or p.get('common', {}).get('premium', False)
    }

    player_data = {
        'name': p.get('player', {}).get('name') or p.get('common', {}).get('playerName') or
                p.get('user', {}).get('name') or "—"
    }

    battle_data = {
        'mode': p.get('battle', {}).get('mode') or p.get('mode') or p.get('common', {}).get('mode'),
        'title': p.get('title')
    }

    stats_data = {
        'credits': p.get('player', {}).get('credits') or p.get('stats', {}).get('credits') or p.get('credits') or 0,
        'xp': p.get('player', {}).get('xp') or p.get('stats', {}).get('xp') or p.get('xp') or 0,
        'kills': p.get('player', {}).get('frags') or p.get('stats', {}).get('kills') or p.get('frags') or 0,
        'damage': p.get('player', {}).get('damage') or p.get('stats', {}).get('damage') or p.get('damage') or 0,
        'assist': p.get('stats', {}).get('assist') or p.get('assist') or 0,
        'block': p.get('stats', {}).get('blocked') or p.get('blocked') or p.get('block') or 0
    }

    return {
        'map': map_data,
        'vehicle': vehicle_data,
        'player': player_data,
        'battle': battle_data,
        'stats': stats_data,
    }


def list_page(request: HttpRequest) -> HttpResponse:
    """
    Одна страница: GET — показывает список, POST — принимает загрузку реплеев.
    """
    if request.method == "POST":
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            messages.error(request, "Выберите файл(ы) .mtreplay")
            return redirect("replays_list")

        success, skipped, failed = 0, 0, 0
        for up in files:
            file_name = Path(up.name).name
            dest = FILES_DIR / file_name

            # если имя занято — пропускаем
            if dest.exists() or Replay.objects.filter(file_name=file_name).exists():
                skipped += 1
                continue

            # сохраняем файл
            with open(dest, "wb") as f:
                for chunk in up.chunks():
                    f.write(chunk)

            try:
                extracted_str = extract_all_json_from_mtreplay(str(dest))
                payload = json.loads(extracted_str) if extracted_str.strip() else {}
            except Exception:
                failed += 1
                with contextlib.suppress(Exception):
                    dest.unlink(missing_ok=True)
                continue

            with transaction.atomic():
                Replay.objects.create(file_name=file_name, payload=payload)
                success += 1

        if success:
            messages.success(request, f"Загружено: {success}")
        if skipped:
            messages.info(request, f"Пропущено (уже есть): {skipped}")
        if failed:
            messages.error(request, f"Ошибок: {failed}")

        return redirect("replays_list")

    # GET — последние 60 реплеев с подготовленными данными
    items = Replay.objects.order_by("-id")[:60]

    # Подготавливаем данные для шаблона
    processed_items = []
    for item in items:
        replay_data = {
            'id': item.id,
            'file_name': item.file_name,
            'created_at': item.created_at,
            'data': _extract_wot_brief_for_list(item.payload)
        }
        processed_items.append(replay_data)
        print(processed_items)

    return render(request, "replays/list.html", {"items": processed_items, "tiers": range(1, 12)})


# --- пример, как быстро превратить заглушку в настоящую детальную страницу ---
def replay_detail(request, pk: int):
    """
    Реальная детальная страница (пример).
    """
    replay = get_object_or_404(Replay, pk=pk)
    # Можно переиспользовать краткий экстрактор:
    # data = _extract_wot_brief_for_list(replay.payload)
    return render(request, "replays/detail.html", {"replay": replay})