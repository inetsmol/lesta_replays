# replays/management/commands/load_tanks_from_api.py
import os

import requests
from django.core.management.base import BaseCommand, CommandError

from replays.models import Tank

API_URL = "https://api.tanki.su/wot/encyclopedia/vehicles/"

# Опционально: привести типы к человекочитаемым
TYPE_MAP = {
    "lightTank": "LT",
    "mediumTank": "MT",
    "heavyTank": "HT",
    "AT-SPG": "TD",
    "SPG": "SPG",
}

class Command(BaseCommand):
    help = "Загружает справочник танков из API tanki.su в модель Tank."

    def add_arguments(self, parser):
        parser.add_argument(
            "--app-id",
            dest="app_id",
            default=os.getenv("LESTA_APP_ID", ""),
            help="application_id для API (по умолчанию из переменной окружения LESTA_APP_ID)",
        )
        parser.add_argument(
            "--lang",
            dest="lang",
            default="ru",
            help="Язык названий (ru/en/...). По умолчанию ru.",
        )

    def handle(self, *args, **opts):
        app_id = opts["app_id"]
        lang = opts["lang"]
        if not app_id:
            raise CommandError(
                "Не задан application_id. Передайте --app-id или установите переменную окружения LESTA_APP_ID."
            )

        params = {
            "application_id": app_id,
            "language": lang,
            # Запросим только нужные поля, чтобы ответ был компактным
            "fields": "tag,name,short_name_i18n,tier,type",
            # Можно пагинацию, но у WoT список помещается в один ответ
            "page_no": 1,
        }

        self.stdout.write("Запрашиваю список техники из API...")
        try:
            r = requests.get(API_URL, params=params, timeout=30)
            r.raise_for_status()
        except Exception as e:
            raise CommandError(f"HTTP ошибка при обращении к API: {e}")

        data = r.json()
        if data.get("status") != "ok":
            raise CommandError(f"API вернуло ошибку: {data}")

        vehicles = data.get("data") or {}
        if not isinstance(vehicles, dict) or not vehicles:
            raise CommandError("В ответе нет данных по технике.")

        created, updated, skipped = 0, 0, 0

        for _, v in vehicles.items():
            # Некоторые поля могут отсутствовать → аккуратно достаём
            tag = v.get("tag")  # ожидаем строку вида R174_BT-5
            tier = v.get("tier")
            vtype_raw = v.get("type")
            name = v.get("short_name_i18n") or v.get("name")

            if not tag or tier is None or not vtype_raw or not name:
                skipped += 1
                continue

            vtype = TYPE_MAP.get(vtype_raw, vtype_raw)

            obj, is_created = Tank.objects.update_or_create(
                vehicleId=tag,
                defaults={
                    "name": name,
                    "level": tier,
                    "type": vtype,
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Готово: создано {created}, обновлено {updated}, пропущено {skipped}."
        ))
