# replays/services.py
from typing import Dict, Any, List

from django.db import transaction


from .models import Player, Replay


def _normalize_nickname(raw: str | None) -> str:
    return (raw or "").strip()


def _normalize_clan(raw: str | None) -> str:
    # в реплеях бывает "[TAG]" или "tag" — приведём к "TAG"
    return (raw or "").strip("[] ").upper()


@transaction.atomic
def upsert_players_from_payload(payload: Dict[str, Any]) -> List[Player]:
    """
    Создаёт/обновляет игроков по данным из payload и возвращает список объектов Player.

    Логика:
    - Ищем по уникальному nickname (он уникален в модели Player).
    - Если нашли и в payload есть клан, а у нас он пуст или отличается — обновляем.
    """
    from wotreplay.helper.extractor import Extractor
    players_info = Extractor.parse_players_payload(payload)
    players: List[Player] = []

    for nickname, clan_tag in players_info:
        obj, created = Player.objects.get_or_create(
            nickname=nickname,
            defaults={"clan_tag": clan_tag},
        )
        # при необходимости обновим клан
        if clan_tag and obj.clan_tag != clan_tag:
            obj.clan_tag = clan_tag
            obj.save(update_fields=["clan_tag"])
        players.append(obj)

    return players


def attach_players_to_replay(replay: Replay, payload: Dict[str, Any]) -> None:
    """
    Утилита для импортера:
      - создаёт/обновляет игроков,
      - вешает их на реплей (M2M).
    """
    player_objs = upsert_players_from_payload(payload)
    if player_objs:
        replay.participants.add(*player_objs)
