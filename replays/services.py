# replays/services.py
from __future__ import annotations

from typing import Dict, Any, List, Iterable, Tuple
from django.db import transaction

from .models import Player, Replay


def _norm_str(raw: str | None) -> str:
    return (raw or "").strip()


def _norm_clan(raw: str | None) -> str:
    # В реплеях бывает "[TAG]" или "tag" — приводим к "TAG"
    return (raw or "").strip("[] ").upper()


def _extract_triplet(item: Any) -> Tuple[str, str, str]:
    """
    Унифицируем результат парсера игроков.
    Возвращает (login_name, real_name, clan_tag).
    Поддерживает:
      - dict с ключами 'name' / 'login', 'realName', 'clanAbbrev'
      - tuple длиной 3: (name, real_name, clan_tag)
      - tuple длиной 2: (name, clan_tag)  -> real_name = name
      - строку: 'name'                    -> real_name = name, clan=''
    """
    if isinstance(item, dict):
        login = _norm_str(item.get("name") or item.get("login"))
        real = _norm_str(item.get("realName"))
        clan = _norm_clan(item.get("clanAbbrev"))
        if not login and real:
            # иногда realName = отображаемый ник, используем его как логин если login пуст
            login = real
        return login, real or login, clan

    if isinstance(item, (list, tuple)):
        if len(item) == 3:
            login, real, clan = item
            return _norm_str(login), _norm_str(real) or _norm_str(login), _norm_clan(clan)
        if len(item) == 2:
            login, clan = item
            login = _norm_str(login)
            return login, login, _norm_clan(clan)

    # последний случай — строка
    login = _norm_str(str(item) if item is not None else "")
    return login, login, ""


@transaction.atomic
def upsert_players_from_payload(payload: Dict[str, Any]) -> List[Player]:
    """
    Создаёт/обновляет игроков по данным из payload и возвращает список объектов Player.

    Поиск ведётся по уникальному Player.name (логин).
    При нахождении записи обновляются real_name и clan_tag, если пришли непустые и отличаются.
    """
    from wotreplay.helper.extractor import Extractor

    # Ожидаем, что парсер вернёт коллекцию игроков (dicts/tuples/strings)
    raw_players: Iterable[Any] = Extractor.parse_players_payload(payload) or []
    players: List[Player] = []

    for raw in raw_players:
        login, real_name, clan_tag = _extract_triplet(raw)
        if not login:
            # пропускаем мусор без логина — иначе упрёмся в UNIQUE(name)
            continue

        obj, created = Player.objects.get_or_create(
            name=login,
            defaults={"real_name": real_name, "clan_tag": clan_tag},
        )

        to_update = []
        if not created:
            # мягкие обновления (только если пришло непустое и отличается)
            if real_name and obj.real_name != real_name:
                obj.real_name = real_name
                to_update.append("real_name")
            if clan_tag and obj.clan_tag != clan_tag:
                obj.clan_tag = clan_tag
                to_update.append("clan_tag")
            if to_update:
                obj.save(update_fields=to_update)

        players.append(obj)

    return players


def attach_players_to_replay(replay: Replay, payload: Dict[str, Any]) -> None:
    """
    Создаёт/обновляет игроков и прикрепляет их к реплею (M2M).
    """
    player_objs = upsert_players_from_payload(payload)
    if player_objs:
        replay.participants.add(*player_objs)
