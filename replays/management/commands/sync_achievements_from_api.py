import json
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from replays.models import Achievement, AchievementOption

API_URL = "https://api.tanki.su/wot/encyclopedia/achievements/"
DEFAULT_RECORDS_PATH = "tools/achievements/records.py"


def normalize_achievement_image(path_or_url: Optional[str]) -> str:
    """
    Преобразует URL/путь к локальному относительному пути static в каталоге big.

    Всегда возвращает путь вида:
    style/images/wot/achievement/big/<filename>
    """
    if not path_or_url:
        return ""

    parsed = urlparse(path_or_url)
    path = parsed.path or path_or_url
    filename = Path(path).name
    if not filename:
        return ""
    return f"style/images/wot/achievement/big/{filename}"


def load_record_db_ids(records_path: Path) -> Dict[Tuple[str, str], int]:
    """
    Загружает RECORD_DB_IDS из tools/achievements/records.py без запуска хвоста со скриптом.
    """
    if not records_path.exists():
        raise CommandError(f"Файл с ID достижений не найден: {records_path}")

    code = records_path.read_text(encoding="utf-8")
    sentinel = "\nimport json\nfrom collections import Counter, defaultdict\n"
    if sentinel in code:
        code = code.split(sentinel, 1)[0]

    namespace = {}
    exec(code, namespace)
    record_db_ids = namespace.get("RECORD_DB_IDS")
    if not isinstance(record_db_ids, dict):
        raise CommandError("Не удалось получить RECORD_DB_IDS из файла records.py")
    return record_db_ids


class Command(BaseCommand):
    help = (
        "Синхронизирует таблицу достижений из API tanki.su. "
        "Поддерживает обычные достижения и достижения со степенями (options)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--application-id",
            dest="application_id",
            default=getattr(settings, "LESTA_APPLICATION_ID", ""),
            help="Application ID для API tanki.su. По умолчанию берётся из настроек проекта.",
        )
        parser.add_argument(
            "--api-url",
            dest="api_url",
            default=API_URL,
            help=f"URL API достижений. По умолчанию: {API_URL}",
        )
        parser.add_argument(
            "--records-path",
            dest="records_path",
            default=DEFAULT_RECORDS_PATH,
            help=f"Путь к файлу records.py с RECORD_DB_IDS. По умолчанию: {DEFAULT_RECORDS_PATH}",
        )
        parser.add_argument(
            "--keep-missing-active",
            action="store_true",
            help="Не деактивировать достижения, которых нет в текущем API ответе.",
        )
        parser.add_argument(
            "--exclude-mastery",
            action="store_true",
            help="Не импортировать markOfMastery (ID 79), если обрабатывается отдельно.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать статистику без записи в БД.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="Таймаут HTTP-запроса в секундах (по умолчанию 30).",
        )

    def handle(self, *args, **options):
        application_id = (options.get("application_id") or "").strip()
        api_url = (options.get("api_url") or "").strip()
        records_path = Path(options.get("records_path") or DEFAULT_RECORDS_PATH)
        keep_missing_active = bool(options.get("keep_missing_active"))
        exclude_mastery = bool(options.get("exclude_mastery"))
        dry_run = bool(options.get("dry_run"))
        timeout = max(int(options.get("timeout") or 30), 1)

        if not application_id:
            raise CommandError("Не задан application_id. Передайте --application-id или заполните LESTA_APPLICATION_ID.")

        self.stdout.write(f"Загрузка словаря ID: {records_path}")
        record_db_ids = load_record_db_ids(records_path)

        self.stdout.write(f"Запрос API: {api_url}")
        try:
            resp = requests.get(
                api_url,
                params={"application_id": application_id},
                timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise CommandError(f"Ошибка запроса к API: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"API вернул невалидный JSON: {exc}") from exc

        if payload.get("status") != "ok":
            raise CommandError(f"API вернул ошибку: {payload}")

        api_data = payload.get("data") or {}
        if not isinstance(api_data, dict):
            raise CommandError("Некорректный формат поля data в ответе API.")

        # Сопоставление token -> id через RECORD_DB_IDS с приоритетами категорий.
        by_name: Dict[str, list[Tuple[str, int]]] = {}
        for (category, name), value in record_db_ids.items():
            if not name:
                continue
            by_name.setdefault(name, []).append((category, int(value)))
        category_priority = [
            "achievements",
            "singleAchievements",
            "epicBattleAchievements",
            "maxComp7Season4",
            "steamAchievements",
            "achievements7x7",
            "fortAchievements",
            "falloutAchievements",
            "racing2019Achievements",
        ]
        type_to_category = {
            "repeatable": "achievements",
            "series": "achievements",
            "class": "achievements",
            "custom": "achievements",
            "single": "singleAchievements",
        }

        def resolve_id(token: str, api_type: str) -> Optional[int]:
            rows = by_name.get(token) or []
            if not rows:
                return None
            preferred = type_to_category.get(api_type, "achievements")
            order = [preferred] + [c for c in category_priority if c != preferred]
            for category in order:
                for row_category, value in rows:
                    if row_category == category:
                        return value
            return rows[0][1]

        created = 0
        updated = 0
        options_created = 0
        options_updated = 0
        unresolved_tokens = []
        active_ids = set()

        def sync_item(token: str, item: dict):
            nonlocal created, updated, options_created, options_updated

            api_type = (item.get("type") or "").strip()
            achievement_id = resolve_id(token, api_type)
            if achievement_id is None:
                unresolved_tokens.append(token)
                return
            if exclude_mastery and token == "markOfMastery":
                return

            # section берём напрямую из API и всегда перезаписываем в БД
            section = item.get("section") or ""
            defaults = {
                "token": token,
                "name": item.get("name_i18n") or token,
                "description": item.get("description") or "",
                "condition": item.get("condition") or "",
                "section": section,
                "api_type": api_type,
                "hero_info": item.get("hero_info") or "",
                "outdated": bool(item.get("outdated")),
                "order": item.get("order"),
                "section_order": item.get("section_order"),
                # В проекте используем только big-иконки.
                "image_small": "",
                "image_big": normalize_achievement_image(item.get("image_big")),
                "is_active": True,
            }
            achievement, is_created = Achievement.objects.update_or_create(
                achievement_id=achievement_id,
                defaults=defaults,
            )
            active_ids.add(achievement_id)
            if is_created:
                created += 1
            else:
                updated += 1

            option_rows = item.get("options") or []
            valid_ranks = set()
            for idx, opt in enumerate(option_rows, start=1):
                valid_ranks.add(idx)
                option_defaults = {
                    "name": opt.get("name_i18n") or "",
                    "description": opt.get("description") or "",
                    # В проекте используем только big-иконки.
                    "image_small": "",
                    "image_big": normalize_achievement_image(opt.get("image_big")),
                    "nation_images": opt.get("nation_images") or {},
                }
                _, option_created = AchievementOption.objects.update_or_create(
                    achievement=achievement,
                    rank=idx,
                    defaults=option_defaults,
                )
                if option_created:
                    options_created += 1
                else:
                    options_updated += 1

            achievement.options.exclude(rank__in=valid_ranks).delete()

        if dry_run:
            for token, item in api_data.items():
                api_type = (item.get("type") or "").strip()
                achievement_id = resolve_id(token, api_type)
                if achievement_id is None:
                    unresolved_tokens.append(token)
                    continue
                if exclude_mastery and token == "markOfMastery":
                    continue
                active_ids.add(achievement_id)
            total_existing = Achievement.objects.count()
            to_disable = 0 if keep_missing_active else max(total_existing - len(active_ids), 0)
            self.stdout.write(self.style.WARNING("DRY-RUN: данные в БД не изменены."))
            self.stdout.write(
                f"API записей: {len(api_data)} | сопоставлено по ID: {len(active_ids)} | "
                f"без ID: {len(unresolved_tokens)} | будет деактивировано: {to_disable}"
            )
            if unresolved_tokens:
                sample = ", ".join(sorted(unresolved_tokens)[:20])
                self.stdout.write(f"Примеры token без ID: {sample}")
            return

        with transaction.atomic():
            for token, item in api_data.items():
                sync_item(token, item)

            disabled = 0
            if not keep_missing_active:
                disabled = Achievement.objects.exclude(achievement_id__in=active_ids).update(is_active=False)

        self.stdout.write(self.style.SUCCESS("Синхронизация достижений завершена."))
        self.stdout.write(f"Обновлено: {updated}, создано: {created}")
        self.stdout.write(f"Опции степеней: обновлено {options_updated}, создано {options_created}")
        self.stdout.write(f"Сопоставлено token->id: {len(active_ids)} из {len(api_data)}")
        if not keep_missing_active:
            self.stdout.write(f"Деактивировано отсутствующих в API: {disabled}")
        if unresolved_tokens:
            sample = ", ".join(sorted(unresolved_tokens)[:30])
            self.stdout.write(self.style.WARNING(f"Не удалось сопоставить ID для {len(unresolved_tokens)} token: {sample}"))
