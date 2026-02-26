from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


IMAGE_PREFIX = "gui/maps/shop/vehicles/180x135/"
DEFAULT_CLIENT_ROOT = Path(r"C:\Games\Tanki_PT")
PACKAGE_RELATIVE_PATHS = (
    Path("res/packages/gui-part1.pkg"),
    Path("res/packages/gui-part2.pkg"),
)


@dataclass
class ExtractStats:
    matched: int = 0
    extracted: int = 0
    overwritten: int = 0
    unsafe_skipped: int = 0


class Command(BaseCommand):
    help = (
        "Синхронизирует изображения танков из клиента игры: копирует gui-part*.pkg во "
        "временную папку проекта и извлекает gui/maps/shop/vehicles/180x135/ в один каталог."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-root",
            default=str(DEFAULT_CLIENT_ROOT),
            help="Путь к корню клиента игры (по умолчанию: C:\\Games\\Tanki_PT).",
        )
        parser.add_argument(
            "--temp-root",
            default=str(Path(settings.BASE_DIR) / "tmp" / "tank_client_sync"),
            help="Временная папка проекта для копий .pkg и извлечённых картинок.",
        )
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Очистить временную папку перед запуском.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только проверить и посчитать файлы без копирования и извлечения.",
        )

    def handle(self, *args, **options):
        client_root = Path(options["client_root"]).expanduser().resolve()
        temp_root = Path(options["temp_root"]).expanduser().resolve()
        dry_run = bool(options.get("dry_run"))
        clean = bool(options.get("clean"))

        source_packages = [client_root / rel for rel in PACKAGE_RELATIVE_PATHS]
        missing = [str(p) for p in source_packages if not p.exists()]
        if missing:
            raise CommandError(
                "Не найдены файлы пакетов клиента:\n- " + "\n- ".join(missing)
            )

        if clean and temp_root.exists() and not dry_run:
            self.stdout.write(f"Очищаю временную папку: {temp_root}")
            shutil.rmtree(temp_root)

        packages_temp_dir = temp_root / "packages"
        images_temp_dir = temp_root / "images" / "180x135"

        copied, reused = self._copy_packages(
            source_packages=source_packages,
            target_dir=packages_temp_dir,
            dry_run=dry_run,
        )

        if not dry_run:
            images_temp_dir.mkdir(parents=True, exist_ok=True)

        total_stats = ExtractStats()
        for pkg_name in (p.name for p in source_packages):
            package_path = packages_temp_dir / pkg_name
            if dry_run:
                package_path = client_root / "res" / "packages" / pkg_name
            stats = self._extract_images(package_path, images_temp_dir, dry_run=dry_run)
            total_stats.matched += stats.matched
            total_stats.extracted += stats.extracted
            total_stats.overwritten += stats.overwritten
            total_stats.unsafe_skipped += stats.unsafe_skipped
            self.stdout.write(
                f"{pkg_name}: найдено {stats.matched}, "
                f"извлечено {stats.extracted}, перезаписано {stats.overwritten}"
            )

        mode_prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode_prefix}Копирование пакетов: новых {copied}, переиспользовано {reused}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode_prefix}Изображения: найдено {total_stats.matched}, "
                f"извлечено {total_stats.extracted}, перезаписано {total_stats.overwritten}"
            )
        )
        if total_stats.unsafe_skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"{mode_prefix}Пропущено небезопасных путей: {total_stats.unsafe_skipped}"
                )
            )
        self.stdout.write(self.style.SUCCESS(f"{mode_prefix}Временная папка: {temp_root}"))
        self.stdout.write(self.style.SUCCESS(f"{mode_prefix}Картинки: {images_temp_dir}"))

    def _copy_packages(
        self,
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

            self.stdout.write(f"Копирую {src} -> {dst}")
            shutil.copy2(src, dst)

        return copied, reused

    def _extract_images(self, package_path: Path, out_dir: Path, dry_run: bool) -> ExtractStats:
        if not package_path.exists():
            raise CommandError(f"Файл пакета не найден: {package_path}")

        stats = ExtractStats()
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
                    stats.overwritten += 1

                if dry_run:
                    stats.extracted += 1
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as src_file, open(target_path, "wb") as dst_file:
                    shutil.copyfileobj(src_file, dst_file)
                stats.extracted += 1

        return stats
