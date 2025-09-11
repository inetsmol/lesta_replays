# app/management/commands/load_tankopedia.py
import asyncio
import re
from typing import Iterable, List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
# Используем async-версию Playwright для надёжного ожидания рендеринга JS
from playwright.async_api import async_playwright

from replays.models import Tank

TANKOPEDIA_BASE = "https://tanki.su/ru/tankopedia/"
# Хэш с параметрами, который сразу открывает список техники конкретной нации в режиме таблицы
# Пример: https://tanki.su/ru/tankopedia/#mt&w_m=tanks&w_n=ussr
HASH_TEMPLATE = "#mt&w_m=tanks&w_n={nation}"

# Полный список наций (slug-ов) с сайта Танковедения
# ВАЖНО: 'czech' и новая 'intunion'
NATION_SLUGS: List[str] = [
    "ussr", "germany", "usa", "china", "france", "uk", "japan",
    "czech", "sweden", "poland", "italy", "intunion",
]

# Регулярка для извлечения vehicleId из href строки строки таблицы.
# Примеры href: "/ru/tankopedia/3329-R11_MS-1/", "/ru/tankopedia/1025-R08_BT-2/"
HREF_ID_RE = re.compile(r"/ru/tankopedia/\d+-([A-Za-z0-9_+-]+)/?")

# Соответствия классов типа техники → хранимый slug
# На странице встречается класс вида: "ico-vehicle-type__lighttank" или "ico-vehicle-type__lighttank-prem"
# Мы берём часть после "__" и отбрасываем суффикс "-prem".
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
    """Преобразует римскую цифру уровня (I–XI) в int."""
    s = s.strip().upper()
    if s not in ROMAN_TO_INT:
        raise ValueError(f"Неизвестный римский уровень: {s}")
    return ROMAN_TO_INT[s]


def _normalize_type(class_value: str) -> Optional[str]:
    """
    Превращает css-класс вида 'ico-vehicle-type__lighttank' или 'ico-vehicle-type__lighttank-prem'
    в чистый slug типа ('lighttank', 'mediumtank', 'heavytank', 'at-spg', 'spg').
    """
    # пример: 'ico-vehicle-type ico-vehicle-type__lighttank'
    parts = [p for p in class_value.split() if p.startswith("ico-vehicle-type__")]
    if not parts:
        return None
    raw = parts[0].split("__", 1)[1]  # 'lighttank' или 'lighttank-prem'
    raw = raw.replace("-prem", "")
    return TYPE_NORMALIZE_MAP.get(raw)


def _nation_slug_is_valid(slug: str) -> bool:
    """Проверяем, что slug входит в список поддерживаемых наций."""
    return slug in NATION_SLUGS


async def _scrape_nation(page, nation_slug: str, limit: Optional[int] = None) -> List[dict]:
    """
    Загружает страницу Танковедения с фильтром по нации и вытаскивает список техники.

    Возвращает список словарей: {vehicleId, name, level, type, nation}
    """
    if not _nation_slug_is_valid(nation_slug):
        raise ValueError(f"Неизвестная нация: {nation_slug}")

    url = TANKOPEDIA_BASE + HASH_TEMPLATE.format(nation=nation_slug)
    await page.goto(url, wait_until="domcontentloaded")

    # ВАЖНО: данные дорисовываются JS — ждём появления строк таблицы.
    # Иногда список может грузиться дольше — увеличим таймаут и проверку через evaluate.
    await page.wait_for_function(
        """() => document.querySelectorAll('a.table-view_row').length > 0""",
        timeout=30_000
    )

    # Собираем элементы
    rows = await page.query_selector_all("a.table-view_row")
    items = []

    for idx, row in enumerate(rows):
        if limit is not None and idx >= limit:
            break

        href = await row.get_attribute("href")  # напр.: "/ru/tankopedia/3329-R11_MS-1/"
        if not href:
            continue
        m = HREF_ID_RE.search(href)
        if not m:
            # если формат изменится — пропустим
            continue
        vehicle_id = m.group(1)

        # Имя техники
        name_el = await row.query_selector(".table-view_col__name .table-view_tank-name")
        name = (await name_el.inner_text()).strip() if name_el else None
        if not name:
            continue

        # Уровень (римская цифра)
        lvl_el = await row.query_selector(".table-view_col__lvl .table-view_text")
        lvl_text = (await lvl_el.inner_text()).strip() if lvl_el else ""
        try:
            level = _roman_to_int(lvl_text)
        except Exception:
            # Если не распознали — пропускаем запись
            continue

        # Тип
        type_el = await row.query_selector(".table-view_col__type span")
        type_class = (await type_el.get_attribute("class")) if type_el else ""
        type_slug = _normalize_type(type_class or "")
        if not type_slug:
            # на всякий случай — если не нашли класс
            continue

        items.append({
            "vehicleId": vehicle_id,
            "name": name,
            "level": level,
            "type": type_slug,
            "nation": nation_slug,
        })

    return items


async def _scrape_all(nations: Iterable[str], limit: Optional[int]) -> List[dict]:
    """
    Общий проход по нациям. Возвращает суповой список объектов танков.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="ru-RU",
            user_agent=(
                # Чуть более «живой» UA, чтобы сайт не грустил
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        all_items: List[dict] = []
        for slug in nations:
            try:
                items = await _scrape_nation(page, slug, limit=limit)
                all_items.extend(items)
            except Exception as e:
                # Логируем и идём дальше, чтобы не падать из-за одной нации
                print(f"[WARN] Не удалось получить список для нации {slug}: {e}")

        await context.close()
        await browser.close()

        return all_items


class Command(BaseCommand):
    help = (
        "Загрузка списка техники из Танковедения (tanki.su) без использования API. "
        "Рендерится JS, поэтому требуются playwright + chromium."
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

    def handle(self, *args, **options):
        nations: List[str] = options["nations"] or NATION_SLUGS
        limit: Optional[int] = options.get("limit")
        dry_run: bool = options.get("dry_run", False)

        # Валидация slug-ов наций
        invalid = [s for s in nations if not _nation_slug_is_valid(s)]
        if invalid:
            raise CommandError(f"Неизвестные нации: {', '.join(invalid)}")

        # Основной проход — выполняем event loop
        items = asyncio.run(_scrape_all(nations, limit))

        if not items:
            raise CommandError("Не удалось найти список техники на странице (проверьте доступность сайта).")

        self.stdout.write(self.style.SUCCESS(f"Найдено записей: {len(items)}"))
        if dry_run:
            # Покажем первые 10 строк для контроля
            for row in items[:10]:
                self.stdout.write(f"[DRY] {row}")
            self.stdout.write(self.style.WARNING("DRY-RUN: записи не сохранялись."))
            return

        # Сохранение (upsert по vehicleId). Для простоты — update_or_create по одной записи.
        # Если данных очень много — можно оптимизировать через предварительную выборку и bulk_update.
        saved = 0
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

        self.stdout.write(self.style.SUCCESS(f"Сохранено/обновлено записей: {saved}"))
