from __future__ import annotations

import shutil
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

from django.conf import settings
from django.test import SimpleTestCase
from PIL import Image

from replays.management.commands.sync_tanks_from_client import (
    IMAGE_PREFIX,
    PACKAGE_RELATIVE_PATHS,
    sync_tank_images_from_client,
)


def make_png_bytes(color: tuple[int, int, int, int]) -> bytes:
    buffer = BytesIO()
    image = Image.new("RGBA", (8, 8), color)
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class SyncTanksFromClientTests(SimpleTestCase):
    def test_sync_copies_missing_pngs_to_static_dir_and_creates_webp(self):
        workspace_tmp = Path(settings.BASE_DIR) / "tmp" / "test_sync_tanks_from_client"
        workspace_tmp.mkdir(parents=True, exist_ok=True)
        root = workspace_tmp / "case"
        if root.exists():
            shutil.rmtree(root)

        try:
            root.mkdir(parents=True, exist_ok=True)
            client_root = root / "client"
            temp_root = root / "temp"
            output_dir = root / "static" / "style" / "images" / "wot" / "shop" / "vehicles" / "180x135"
            output_dir.mkdir(parents=True, exist_ok=True)

            existing_png = output_dir / "R01_IS.png"
            existing_png_bytes = make_png_bytes((255, 0, 0, 255))
            existing_png.write_bytes(existing_png_bytes)

            self._write_package(
                client_root / PACKAGE_RELATIVE_PATHS[0],
                {
                    f"{IMAGE_PREFIX}R01_IS.png": make_png_bytes((0, 255, 0, 255)),
                },
            )
            self._write_package(
                client_root / PACKAGE_RELATIVE_PATHS[1],
                {
                    f"{IMAGE_PREFIX}G04_PzVI_Tiger_I.png": make_png_bytes((0, 0, 255, 255)),
                },
            )

            stdout = StringIO()
            result = sync_tank_images_from_client(
                stdout=stdout,
                client_root=client_root,
                temp_root=temp_root,
                output_dir=output_dir,
            )

            self.assertEqual(existing_png.read_bytes(), existing_png_bytes)
            self.assertTrue((output_dir / "G04_PzVI_Tiger_I.png").exists())
            self.assertTrue((output_dir / "R01_IS.webp").exists())
            self.assertTrue((output_dir / "G04_PzVI_Tiger_I.webp").exists())
            self.assertEqual(result.images_dir, output_dir)
            self.assertEqual(result.stats.matched, 2)
            self.assertEqual(result.stats.png_created, 1)
            self.assertEqual(result.stats.png_existing, 1)
            self.assertEqual(result.stats.webp_created, 2)
            self.assertEqual(result.stats.webp_failed, 0)
            self.assertIn("Каталог изображений", stdout.getvalue())
        finally:
            if root.exists():
                shutil.rmtree(root)

    @staticmethod
    def _write_package(package_path: Path, files: dict[str, bytes]) -> None:
        package_path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(package_path, "w") as archive:
            for filename, content in files.items():
                archive.writestr(filename, content)
