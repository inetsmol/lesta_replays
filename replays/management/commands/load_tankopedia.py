# app/management/commands/load_tankopedia.py
import asyncio
import json
import re
from typing import Iterable, List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from playwright.async_api import async_playwright

from replays.models import Tank

TANKOPEDIA_BASE = "https://tanki.su/ru/tankopedia/"
HASH_TEMPLATE = "#mt&w_m=tanks&w_n={nation}"

NATION_SLUGS: List[str] = [
    "ussr", "germany", "usa", "china", "france", "uk", "japan",
    "czech", "sweden", "poland", "italy", "intunion",
]

HREF_ID_RE = re.compile(r"/ru/tankopedia/\d+-([A-Za-z0-9_+-]+)/?")

TYPE_NORMALIZE_MAP = {
    "lighttank": "lighttank",
    "mediumtank": "mediumtank",
    "heavytank": "heavytank",
    "at-spg": "at-spg",   # ПТ-САУ
    "spg": "spg",         # САУ
}

ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
    "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11,
}


def _roman_to_int(s: str) -> int:
    s = s.strip().upper()
    if s not in ROMAN_TO_INT:
        raise ValueError(f"Неизвестный римский уровень: {s}")
    return ROMAN_TO_INT[s]


def _normalize_type(class_value: str) -> Optional[str]:
    parts = [p for p in class_value.split() if p.startswith("ico-vehicle-type__")]
    if not parts:
        return None
    raw = parts[0].split("__", 1)[1]  # 'lighttank' или 'lighttank-prem'
    raw = raw.replace("-prem", "")
    return TYPE_NORMALIZE_MAP.get(raw)


def _nation_slug_is_valid(slug: str) -> bool:
    return slug in NATION_SLUGS


async def _scrape_nation(page, nation_slug: str, limit: Optional[int] = None) -> List[dict]:
    if not _nation_slug_is_valid(nation_slug):
        raise ValueError(f"Неизвестная нация: {nation_slug}")

    url = TANKOPEDIA_BASE + HASH_TEMPLATE.format(nation=nation_slug)
    await page.goto(url, wait_until="domcontentloaded")

    await page.wait_for_function(
        "() => document.querySelectorAll('a.table-view_row').length > 0",
        timeout=30_000
    )

    rows = await page.query_selector_all("a.table-view_row")
    items = []

    for idx, row in enumerate(rows):
        if limit is not None and idx >= limit:
            break

        href = await row.get_attribute("href")
        if not href:
            continue
        m = HREF_ID_RE.search(href)
        if not m:
            continue
        vehicle_id = m.group(1)

        name_el = await row.query_selector(".table-view_col__name .table-view_tank-name")
        name = (await name_el.inner_text()).strip() if name_el else None
        if not name:
            continue

        lvl_el = await row.query_selector(".table-view_col__lvl .table-view_text")
        lvl_text = (await lvl_el.inner_text()).strip() if lvl_el else ""
        try:
            level = _roman_to_int(lvl_text)
        except Exception:
            continue

        type_el = await row.query_selector(".table-view_col__type span")
        type_class = (await type_el.get_attribute("class")) if type_el else ""
        type_slug = _normalize_type(type_class or "")
        if not type_slug:
            continue

        inferred = _infer_nation_from_vehicle_id(vehicle_id)
        nation_out = inferred or nation_slug  # если не смогли определить — оставляем из фильтра

        items.append({
            "vehicleId": vehicle_id,
            "name": name,
            "level": level,
            "type": type_slug,
            "nation": nation_out,
        })

    return items


async def _scrape_all(nations: Iterable[str], limit: Optional[int]) -> List[dict]:
    """
    На каждую нацию открываем отдельную страницу, чтобы избежать залипания состояния SPA.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        all_items: List[dict] = []
        for slug in nations:
            page = await context.new_page()
            try:
                items = await _scrape_nation(page, slug, limit=limit)
                all_items.extend(items)
            except Exception as e:
                print(f"[WARN] Не удалось получить список для нации {slug}: {e}")
            finally:
                await page.close()

        await context.close()
        await browser.close()
        return all_items


def _print_items(items: List[dict], mode: str, write_fn):
    """
    Печать результатов:
      - mode == 'lines' — построчно компактно
      - mode == 'json' — единый JSON
      - mode == 'none' — ничего
    """
    if mode == "none":
        return
    if mode == "json":
        write_fn(json.dumps(items, ensure_ascii=False, indent=2))
        return
    # lines (по умолчанию)
    for row in items:
        write_fn(f"[{row['nation']}] {row['name']} | tier={row['level']} | type={row['type']} | id={row['vehicleId']}")


def _infer_nation_from_vehicle_id(veh_id: str) -> Optional[str]:
    """
    Пытаемся определить нацию по префиксу vehicleId.
    Примеры: S10_... -> sweden, Pl14_... -> poland, It02_... -> italy, GB01_... -> uk и т.п.
    Сначала проверяем длинные префиксы, потом короткие.
    """
    prefix_map = {
        "Un": "intunion",
        "GB": "uk",
        "Ch": "china",
        "Cz": "czech",
        "Pl": "poland",
        "It": "italy",
        "S": "sweden",
        "J": "japan",
        "F": "france",
        "G": "germany",
        "R": "ussr",
        "A": "usa",
    }
    # нормализуем id к безопасному виду
    v = (veh_id or "").strip()
    # длинные префиксы
    for p in ("Un", "GB", "Ch", "Cz", "Pl", "It"):
        if v.startswith(p + "_") or v.startswith(p):
            return prefix_map[p]
    # короткие префиксы
    for p in ("S", "J", "F", "G", "R", "A"):
        if v.startswith(p + "_") or v.startswith(p):
            return prefix_map[p]
    return None


class Command(BaseCommand):
    help = (
        "Загрузка списка техники из Танковедения (tanki.su) без использования API. "
        "Рендерится JS, поэтому требуются playwright + chromium. "
        "Теперь умеет печатать результаты в консоль."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--nations",
            nargs="*",
            type=str,
            default=NATION_SLUGS,
            help="Ограничить список наций (slug). По умолчанию — все.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Ограничить количество записей на нацию (для отладки).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, что будет сохранено; в БД не писать.",
        )
        parser.add_argument(
            "--print-mode",
            choices=("lines", "json", "none"),
            default="lines",
            help="Формат вывода в консоль: lines (по умолчанию), json или none.",
        )

    def handle(self, *args, **options):
        nations: List[str] = options["nations"] or NATION_SLUGS
        limit: Optional[int] = options.get("limit")
        dry_run: bool = options.get("dry_run", False)
        print_mode: str = options.get("print_mode") or "lines"

        invalid = [s for s in nations if not _nation_slug_is_valid(s)]
        if invalid:
            raise CommandError(f"Неизвестные нации: {', '.join(invalid)}")

        items = asyncio.run(_scrape_all(nations, limit))

        if not items:
            raise CommandError("Не удалось найти список техники на странице (проверьте доступность сайта).")

        self.stdout.write(self.style.SUCCESS(f"Найдено записей: {len(items)}"))

        if dry_run:
            # Печатаем всё, что нашли, согласно выбранному режиму
            _print_items(items, print_mode, self.stdout.write)
            self.stdout.write(self.style.WARNING("DRY-RUN: записи не сохранялись."))
            return

        saved = 0
        printed_any = False
        with transaction.atomic():
            for row in items:
                Tank.objects.update_or_create(
                    vehicleId=row["vehicleId"],
                    defaults={
                        "name": row["name"],
                        "level": row["level"],
                        "type": row["type"],
                        "nation": row["nation"],
                    },
                )
                saved += 1
            # После успешного сохранения — печатаем, если нужно
            _print_items(items, print_mode, self.stdout.write)
            printed_any = print_mode != "none"

        self.stdout.write(self.style.SUCCESS(f"Сохранено/обновлено записей: {saved}"))
        if printed_any:
            self.stdout.write(self.style.SUCCESS("Вывод в консоль завершён."))
