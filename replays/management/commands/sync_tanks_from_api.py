from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from replays.management.commands.sync_tanks_from_client import (
    DEFAULT_CLIENT_ROOT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TEMP_ROOT,
    DEFAULT_WEBP_QUALITY,
    sync_tank_images_from_client,
)
from replays.models import Nation, Tank, Type


API_URL = "https://api.tanki.su/wot/encyclopedia/vehicles/"
DEFAULT_FIELDS = "tag,name,short_name,tier,type,nation"
MAX_API_PAGE_SIZE = 100
VALID_TANK_TYPES = {value for value, _ in Type.choices}
VALID_NATIONS = {value for value, _ in Nation.choices}


@dataclass
class SyncStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


class Command(BaseCommand):
    help = (
        "Синхронизирует технику одной командой: обновляет таблицу Tank из API tanki.su "
        "и затем запускает загрузку изображений из клиента игры."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--application-id",
            "--app-id",
            dest="application_id",
            default=getattr(settings, "LESTA_APPLICATION_ID", "") or os.getenv("LESTA_APP_ID", ""),
            help="Application ID для API tanki.su. По умолчанию берётся из настроек проекта.",
        )
        parser.add_argument(
            "--api-url",
            dest="api_url",
            default=API_URL,
            help=f"URL API техники. По умолчанию: {API_URL}",
        )
        parser.add_argument(
            "--language",
            "--lang",
            default="ru",
            help='Язык локализации API. По умолчанию: "ru".',
        )
        parser.add_argument(
            "--page-size",
            type=int,
            default=MAX_API_PAGE_SIZE,
            help="Размер страницы API (1-100). По умолчанию: 100.",
        )
        parser.add_argument(
            "--max-records",
            type=int,
            default=None,
            help="Ограничить общее число записей для синхронизации (удобно для отладки).",
        )
        parser.add_argument(
            "--nation",
            nargs="*",
            default=None,
            help="Фильтр по нациям API, например: --nation ussr germany",
        )
        parser.add_argument(
            "--tier",
            nargs="*",
            type=int,
            default=None,
            help="Фильтр по уровням API, например: --tier 8 9 10",
        )
        parser.add_argument(
            "--type",
            dest="tank_type",
            nargs="*",
            default=None,
            choices=sorted(VALID_TANK_TYPES),
            help="Фильтр по типам техники API.",
        )
        parser.add_argument(
            "--tank-id",
            dest="tank_id",
            nargs="*",
            type=int,
            default=None,
            help="Фильтр по числовым tank_id API.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="Таймаут HTTP-запроса в секундах. По умолчанию: 30.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать статистику синхронизации без записи в базу и без извлечения файлов.",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Не запускать второй шаг с загрузкой изображений из клиента.",
        )
        parser.add_argument(
            "--require-images",
            action="store_true",
            help="Считать загрузку изображений обязательной и завершать команду ошибкой при сбое.",
        )
        parser.add_argument(
            "--client-root",
            default=str(DEFAULT_CLIENT_ROOT),
            help="Путь к корню клиента игры для загрузки изображений.",
        )
        parser.add_argument(
            "--temp-root",
            default=str(DEFAULT_TEMP_ROOT),
            help="Временная папка для копий .pkg и извлечённых картинок.",
        )
        parser.add_argument(
            "--output-dir",
            default=str(DEFAULT_OUTPUT_DIR),
            help="Каталог, куда складываются PNG и WebP изображения танков.",
        )
        parser.add_argument(
            "--webp-quality",
            type=int,
            default=DEFAULT_WEBP_QUALITY,
            help=f"Качество WebP (1-100, по умолчанию {DEFAULT_WEBP_QUALITY}).",
        )
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Очистить временную папку с изображениями перед запуском второго шага.",
        )

    def handle(self, *args, **options):
        application_id = (options.get("application_id") or "").strip()
        api_url = (options.get("api_url") or "").strip()
        language = (options.get("language") or "ru").strip()
        page_size = min(max(int(options.get("page_size") or MAX_API_PAGE_SIZE), 1), MAX_API_PAGE_SIZE)
        max_records = options.get("max_records")
        timeout = max(int(options.get("timeout") or 30), 1)
        dry_run = bool(options.get("dry_run"))

        if not application_id:
            raise CommandError(
                "Не задан application_id. Передайте --application-id или заполните LESTA_APPLICATION_ID."
            )
        if not api_url:
            raise CommandError("Не задан URL API.")

        self.stdout.write("Шаг 1/2: синхронизация техники из API.")
        filters = {
            "nation": self._join_values(options.get("nation")),
            "tier": self._join_values(options.get("tier")),
            "type": self._join_values(options.get("tank_type")),
            "tank_id": self._join_values(options.get("tank_id")),
        }

        raw_vehicles = self._fetch_all_vehicles(
            api_url=api_url,
            application_id=application_id,
            language=language,
            page_size=page_size,
            max_records=max_records,
            timeout=timeout,
            filters=filters,
        )

        if not raw_vehicles:
            raise CommandError("API не вернуло ни одной записи по технике.")

        normalized_rows, skipped = self._normalize_rows(raw_vehicles)
        if not normalized_rows:
            raise CommandError("После нормализации не осталось корректных записей для синхронизации.")

        stats = SyncStats(skipped=skipped)
        existing = Tank.objects.in_bulk(normalized_rows.keys(), field_name="vehicleId")
        to_create: list[Tank] = []
        to_update: list[Tank] = []

        for vehicle_id, row in normalized_rows.items():
            tank = existing.get(vehicle_id)
            if tank is None:
                to_create.append(Tank(**row))
                stats.created += 1
                continue

            changed = False
            for field_name in ("name", "level", "type", "nation"):
                new_value = row[field_name]
                if getattr(tank, field_name) != new_value:
                    setattr(tank, field_name, new_value)
                    changed = True

            if changed:
                to_update.append(tank)
                stats.updated += 1
            else:
                stats.unchanged += 1

        untouched_existing = Tank.objects.exclude(vehicleId__in=normalized_rows.keys()).count()

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN: изменения в базу не записывались."))
            self._print_summary(
                fetched=len(raw_vehicles),
                normalized=len(normalized_rows),
                untouched_existing=untouched_existing,
                stats=stats,
            )
        else:
            with transaction.atomic():
                if to_create:
                    Tank.objects.bulk_create(to_create, batch_size=500)
                if to_update:
                    Tank.objects.bulk_update(to_update, ["name", "level", "type", "nation"], batch_size=500)

            self.stdout.write(self.style.SUCCESS("Синхронизация техники завершена."))
            self._print_summary(
                fetched=len(raw_vehicles),
                normalized=len(normalized_rows),
                untouched_existing=untouched_existing,
                stats=stats,
            )

        self._run_image_sync(
            skip_images=bool(options.get("skip_images")),
            require_images=bool(options.get("require_images")),
            client_root=Path(options["client_root"]).expanduser().resolve(),
            temp_root=Path(options["temp_root"]).expanduser().resolve(),
            output_dir=Path(options["output_dir"]).expanduser().resolve(),
            webp_quality=int(options.get("webp_quality") or DEFAULT_WEBP_QUALITY),
            clean=bool(options.get("clean")),
            dry_run=dry_run,
        )

    def _run_image_sync(
        self,
        *,
        skip_images: bool,
        require_images: bool,
        client_root: Path,
        temp_root: Path,
        output_dir: Path,
        webp_quality: int,
        clean: bool,
        dry_run: bool,
    ) -> None:
        if skip_images:
            self.stdout.write("Шаг 2/2: загрузка изображений пропущена по флагу --skip-images.")
            return

        self.stdout.write("Шаг 2/2: загрузка изображений из клиента.")
        try:
            sync_tank_images_from_client(
                stdout=self.stdout,
                client_root=client_root,
                temp_root=temp_root,
                output_dir=output_dir,
                dry_run=dry_run,
                clean=clean,
                webp_quality=webp_quality,
            )
        except CommandError as exc:
            if require_images:
                raise
            self.stdout.write(
                self.style.WARNING(
                    f"Синхронизация изображений пропущена: {exc}"
                )
            )

    def _fetch_all_vehicles(
        self,
        *,
        api_url: str,
        application_id: str,
        language: str,
        page_size: int,
        max_records: int | None,
        timeout: int,
        filters: dict[str, str | None],
    ) -> list[dict[str, Any]]:
        page_no = 1
        page_total = None
        collected: list[dict[str, Any]] = []

        while page_total is None or page_no <= page_total:
            params: dict[str, Any] = {
                "application_id": application_id,
                "language": language,
                "fields": DEFAULT_FIELDS,
                "limit": page_size,
                "page_no": page_no,
            }
            for key, value in filters.items():
                if value:
                    params[key] = value

            try:
                response = requests.get(api_url, params=params, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                raise CommandError(f"Ошибка запроса к API на странице {page_no}: {exc}") from exc
            except ValueError as exc:
                raise CommandError(f"API вернуло невалидный JSON на странице {page_no}: {exc}") from exc

            if payload.get("status") != "ok":
                raise CommandError(f"API вернуло ошибку на странице {page_no}: {payload}")

            meta = payload.get("meta") or {}
            if page_total is None:
                page_total = int(meta.get("page_total") or 1)

            page_data = payload.get("data") or {}
            if not isinstance(page_data, dict):
                raise CommandError(f"Некорректный формат поля data на странице {page_no}.")

            page_rows = list(page_data.values())
            if not page_rows:
                break

            collected.extend(page_rows)
            self.stdout.write(
                f"Страница {page_no}/{page_total}: получено {len(page_rows)} записей, всего накоплено {len(collected)}."
            )

            if max_records is not None and max_records > 0 and len(collected) >= max_records:
                return collected[:max_records]

            page_no += 1

        return collected

    def _normalize_rows(self, raw_vehicles: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], int]:
        normalized: dict[str, dict[str, Any]] = {}
        skipped = 0

        for vehicle in raw_vehicles:
            vehicle_id = (vehicle.get("tag") or "").strip()
            tank_name = (vehicle.get("short_name") or vehicle.get("name") or "").strip()
            level = vehicle.get("tier")
            tank_type = (vehicle.get("type") or "").strip()
            nation = vehicle.get("nation")

            if not vehicle_id or not tank_name or level is None or not tank_type:
                skipped += 1
                continue

            if tank_type not in VALID_TANK_TYPES:
                skipped += 1
                continue

            if nation is not None:
                nation = str(nation).strip() or None
            if nation and nation not in VALID_NATIONS:
                skipped += 1
                continue

            try:
                level = int(level)
            except (TypeError, ValueError):
                skipped += 1
                continue

            normalized[vehicle_id] = {
                "vehicleId": vehicle_id,
                "name": tank_name,
                "level": level,
                "type": tank_type,
                "nation": nation,
            }

        return normalized, skipped

    def _print_summary(
        self,
        *,
        fetched: int,
        normalized: int,
        untouched_existing: int,
        stats: SyncStats,
    ) -> None:
        self.stdout.write(
            f"Получено из API: {fetched} | корректных после нормализации: {normalized} | пропущено: {stats.skipped}"
        )
        self.stdout.write(
            f"Создано: {stats.created} | обновлено: {stats.updated} | без изменений: {stats.unchanged}"
        )
        if untouched_existing:
            self.stdout.write(
                f"Не затронуто существующих записей вне ответа API: {untouched_existing}"
            )

    @staticmethod
    def _join_values(values: list[Any] | None) -> str | None:
        if not values:
            return None
        return ",".join(str(value) for value in values)
