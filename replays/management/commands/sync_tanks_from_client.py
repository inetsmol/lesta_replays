from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


IMAGE_PREFIX = "gui/maps/shop/vehicles/180x135/"
DEFAULT_CLIENT_ROOT = Path(r"C:\Games\Tanki_PT")
DEFAULT_TEMP_ROOT = Path(settings.BASE_DIR) / "tmp" / "tank_client_sync"
DEFAULT_OUTPUT_DIR = (
    Path(settings.BASE_DIR)
    / "static"
    / "style"
    / "images"
    / "wot"
    / "shop"
    / "vehicles"
    / "180x135"
)
DEFAULT_WEBP_QUALITY = 80
PACKAGE_RELATIVE_PATHS = (
    Path("res/packages/gui-part1.pkg"),
    Path("res/packages/gui-part2.pkg"),
)
WEBP_SOURCE_SUFFIXES = {".png", ".jpg", ".jpeg"}


@dataclass
class ImageSyncStats:
    matched: int = 0
    png_created: int = 0
    png_existing: int = 0
    webp_created: int = 0
    webp_existing: int = 0
    webp_failed: int = 0
    unsafe_skipped: int = 0


@dataclass
class ClientSyncResult:
    copied: int
    reused: int
    stats: ImageSyncStats
    temp_root: Path
    images_dir: Path


def _copy_packages(
    *,
    stdout: Any,
    source_packages: Iterable[Path],
    target_dir: Path,
    dry_run: bool,
) -> tuple[int, int]:
    copied = 0
    reused = 0

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    for src in source_packages:
        dst = target_dir / src.name
        src_stat = src.stat()

        if dst.exists():
            dst_stat = dst.stat()
            if (
                dst_stat.st_size == src_stat.st_size
                and dst_stat.st_mtime >= src_stat.st_mtime
            ):
                reused += 1
                continue

        copied += 1
        if dry_run:
            continue

        stdout.write(f"Копирую {src} -> {dst}")
        shutil.copy2(src, dst)

    return copied, reused


def _can_create_webp(image_path: Path) -> bool:
    return image_path.suffix.lower() in WEBP_SOURCE_SUFFIXES


def _create_webp(image_path: Path, quality: int) -> bool:
    webp_path = image_path.with_suffix(".webp")
    try:
        with Image.open(image_path) as img:
            if img.mode == "P":
                img = img.convert("RGBA")
            elif img.mode not in ("RGB", "RGBA", "LA"):
                img = img.convert("RGB")

            img.save(webp_path, "WEBP", quality=quality, method=6)
        return True
    except Exception:
        if webp_path.exists():
            webp_path.unlink()
        return False


def _extract_images(
    package_path: Path,
    out_dir: Path,
    dry_run: bool,
    webp_quality: int,
) -> ImageSyncStats:
    if not package_path.exists():
        raise CommandError(f"Файл пакета не найден: {package_path}")

    stats = ImageSyncStats()
    with zipfile.ZipFile(package_path, "r") as archive:
        for info in archive.infolist():
            filename = info.filename.replace("\\", "/").lstrip("/")

            if info.is_dir() or not filename.startswith(IMAGE_PREFIX):
                continue

            relative_name = filename[len(IMAGE_PREFIX):]
            if not relative_name:
                continue

            rel_path = Path(relative_name)
            if rel_path.is_absolute() or ".." in rel_path.parts:
                stats.unsafe_skipped += 1
                continue

            stats.matched += 1
            target_path = out_dir / rel_path

            if target_path.exists():
                stats.png_existing += 1
            else:
                stats.png_created += 1
                if not dry_run:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as src_file, open(target_path, "wb") as dst_file:
                        shutil.copyfileobj(src_file, dst_file)

            if not _can_create_webp(target_path):
                continue

            webp_path = target_path.with_suffix(".webp")
            if webp_path.exists():
                stats.webp_existing += 1
                continue

            if dry_run:
                stats.webp_created += 1
                continue

            if _create_webp(target_path, quality=webp_quality):
                stats.webp_created += 1
            else:
                stats.webp_failed += 1

    return stats


def sync_tank_images_from_client(
    *,
    stdout: Any,
    client_root: Path,
    temp_root: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    dry_run: bool = False,
    clean: bool = False,
    webp_quality: int = DEFAULT_WEBP_QUALITY,
) -> ClientSyncResult:
    source_packages = [client_root / rel for rel in PACKAGE_RELATIVE_PATHS]
    missing = [str(p) for p in source_packages if not p.exists()]
    if missing:
        raise CommandError(
            "Не найдены файлы пакетов клиента:\n- " + "\n- ".join(missing)
        )

    if not 1 <= int(webp_quality) <= 100:
        raise CommandError("Параметр webp_quality должен быть в диапазоне 1-100.")

    if clean and temp_root.exists() and not dry_run:
        stdout.write(f"Очищаю временную папку: {temp_root}")
        shutil.rmtree(temp_root)

    packages_temp_dir = temp_root / "packages"

    copied, reused = _copy_packages(
        stdout=stdout,
        source_packages=source_packages,
        target_dir=packages_temp_dir,
        dry_run=dry_run,
    )

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    total_stats = ImageSyncStats()
    for pkg_name in (p.name for p in source_packages):
        package_path = packages_temp_dir / pkg_name
        if dry_run:
            package_path = client_root / "res" / "packages" / pkg_name
        stats = _extract_images(
            package_path,
            output_dir,
            dry_run=dry_run,
            webp_quality=webp_quality,
        )
        total_stats.matched += stats.matched
        total_stats.png_created += stats.png_created
        total_stats.png_existing += stats.png_existing
        total_stats.webp_created += stats.webp_created
        total_stats.webp_existing += stats.webp_existing
        total_stats.webp_failed += stats.webp_failed
        total_stats.unsafe_skipped += stats.unsafe_skipped
        stdout.write(
            f"{pkg_name}: найдено {stats.matched}, "
            f"новых PNG {stats.png_created}, существующих PNG {stats.png_existing}, "
            f"создано WebP {stats.webp_created}, уже было WebP {stats.webp_existing}"
        )

    mode_prefix = "[DRY-RUN] " if dry_run else ""
    stdout.write(f"{mode_prefix}Копирование пакетов: новых {copied}, переиспользовано {reused}")
    stdout.write(
        f"{mode_prefix}PNG: найдено {total_stats.matched}, "
        f"добавлено {total_stats.png_created}, уже существовало {total_stats.png_existing}"
    )
    stdout.write(
        f"{mode_prefix}WebP: создано {total_stats.webp_created}, "
        f"уже существовало {total_stats.webp_existing}, ошибок {total_stats.webp_failed}"
    )
    if total_stats.unsafe_skipped:
        stdout.write(
            f"{mode_prefix}Пропущено небезопасных путей: {total_stats.unsafe_skipped}"
        )
    stdout.write(f"{mode_prefix}Временная папка: {temp_root}")
    stdout.write(f"{mode_prefix}Каталог изображений: {output_dir}")

    return ClientSyncResult(
        copied=copied,
        reused=reused,
        stats=total_stats,
        temp_root=temp_root,
        images_dir=output_dir,
    )


class Command(BaseCommand):
    help = (
        "Синхронизирует изображения танков из клиента игры: копирует gui-part*.pkg во "
        "временную папку проекта, докладывает недостающие PNG в static/style/images/wot/shop/vehicles/180x135/ "
        "и создаёт рядом .webp версии."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-root",
            default=str(DEFAULT_CLIENT_ROOT),
            help="Путь к корню клиента игры (по умолчанию: C:\\Games\\Tanki_PT).",
        )
        parser.add_argument(
            "--temp-root",
            default=str(DEFAULT_TEMP_ROOT),
            help="Временная папка проекта для копий .pkg.",
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
            help="Очистить временную папку с пакетами перед запуском.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только проверить и посчитать файлы без копирования и извлечения.",
        )

    def handle(self, *args, **options):
        sync_tank_images_from_client(
            stdout=self.stdout,
            client_root=Path(options["client_root"]).expanduser().resolve(),
            temp_root=Path(options["temp_root"]).expanduser().resolve(),
            output_dir=Path(options["output_dir"]).expanduser().resolve(),
            dry_run=bool(options.get("dry_run")),
            clean=bool(options.get("clean")),
            webp_quality=int(options.get("webp_quality") or DEFAULT_WEBP_QUALITY),
        )
