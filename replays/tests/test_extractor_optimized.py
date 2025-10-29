"""
Unit-тесты для оптимизированных методов ExtractorV2.

Проверяет корректность работы оптимизированных методов экстракции данных.
"""

from django.test import TestCase
from replays.parser.extractor import ExtractorV2, ExtractorContext
from replays.parser.replay_cache import ReplayDataCache
from replays.models import Tank


class TestExtractorV2Optimized(TestCase):
    """Тесты для оптимизированных методов ExtractorV2"""

    def setUp(self):
        """Создаёт тестовые данные перед каждым тестом"""
        # Создаём тестовые танки в БД
        self.tank_is = Tank.objects.create(
            vehicleId="R01_IS",
            name="ИС",
            level=7,
            type="heavyTank",
            nation="ussr"
        )
        self.tank_tiger = Tank.objects.create(
            vehicleId="G04_PzVI_Tiger_I",
            name="Tiger I",
            level=7,
            type="heavyTank",
            nation="germany"
        )

        # Создаём тестовый payload
        self.sample_payload = [
            {
                "playerID": 12345,
                "playerName": "TestPlayer",
                "playerVehicle": "ussr:R01_IS",
                "gameplayID": "ctf",
                "battleType": 1,
                "mapName": "map_name",
            },
            [
                {
                    "common": {
                        "winnerTeam": 1,
                        "finishReason": 1,
                        "duration": 360,
                        "bonusType": 1,
                    },
                    "personal": {
                        "12345": {
                            "accountDBID": 12345,
                            "xp": 1000,
                            "xpPenalty": 0,
                            "credits": 50000,
                            "creditsPenalty": 0,
                            "damageDealt": 2000,
                            "kills": 2,
                            "deathReason": 0,
                            "killerID": 0,
                            "shots": 10,
                            "hits": 7,
                            "he_hits": 2,
                            "pierced": 5,
                            "damageReceived": 1500,
                            "damageAssistedTrack": 300,
                            "damageAssistedRadio": 200,
                            "achievements": [521, 39],
                            "details": {}
                        }
                    },
                    "players": {
                        "12345": {
                            "name": "TestPlayer",
                            "realName": "TestPlayer",
                            "team": 1,
                            "clanAbbrev": "TEST"
                        }
                    },
                    "vehicles": {
                        "12345": [
                            {
                                "typeCompDescr": 12345,
                                "accountDBID": 12345
                            }
                        ]
                    }
                },
                {
                    "12345": {
                        "vehicleType": "ussr:R01_IS",
                        "team": 1
                    }
                }
            ]
        ]

        self.cache = ReplayDataCache(self.sample_payload)

    def test_get_personal_data_minimal(self):
        """Тест получения минимального набора персональных данных"""
        result = ExtractorV2.get_personal_data_minimal(self.cache)

        self.assertIsInstance(result, dict)
        # Проверяем наличие ключевых полей (только те, что метод возвращает)
        self.assertIn("xp", result)
        self.assertIn("credits", result)
        self.assertIn("crystal", result)

        # Проверяем значения
        self.assertEqual(result["xp"], 1000)
        self.assertEqual(result["credits"], 50000)
        self.assertEqual(result["crystal"], 0)

    def test_get_details_data(self):
        """Тест получения данных деталей боя"""
        result = ExtractorV2.get_details_data(self.cache)

        self.assertIsInstance(result, dict)
        # Проверяем наличие ключевых полей
        self.assertIn("playerName", result)
        self.assertIn("battleModeLabel", result)

        # Проверяем значения
        self.assertEqual(result["playerName"], "TestPlayer")
        self.assertEqual(result["battleModeLabel"], "Случайный бой")  # battleType/bonusType = 1

    def test_get_battle_type_label(self):
        """Тест получения метки типа игры (по gameplayID)"""
        result = ExtractorV2.get_battle_type_label(self.cache)

        self.assertIsInstance(result, str)
        # gameplayID = "ctf" должен распознаваться как "Стандартный бой"
        self.assertEqual(result, "Стандартный бой")

    def test_get_battle_mode_label(self):
        """Тест получения метки режима боя (по battleType/bonusType)"""
        result = ExtractorV2.get_battle_mode_label(self.cache)

        self.assertIsInstance(result, str)
        # battleType/bonusType = 1 должен распознаваться как "Случайный бой"
        self.assertEqual(result, "Случайный бой")

    def test_get_battle_outcome(self):
        """Тест определения результата боя"""
        result = ExtractorV2.get_battle_outcome(self.cache)

        self.assertIsInstance(result, dict)
        self.assertIn("outcome", result)
        self.assertIn("text", result)

        # team=1, winnerTeam=1 => Победа
        self.assertEqual(result["outcome"], "win")
        self.assertEqual(result["text"], "Победа")

    def test_get_death_text(self):
        """Тест получения текста причины смерти"""
        result = ExtractorV2.get_death_text(self.cache)

        self.assertIsInstance(result, str)
        # deathReason=0, killerID=0 => Выжил
        self.assertEqual(result, "Выжил")

    def test_get_killer_name(self):
        """Тест получения имени убийцы"""
        result = ExtractorV2.get_killer_name(self.cache)

        # killerID=0 => нет убийцы
        self.assertEqual(result, "")

    def test_extractor_context_initialization(self):
        """Тест создания контекста экстрактора"""
        context = ExtractorContext(self.cache)

        self.assertIsInstance(context, ExtractorContext)
        self.assertIs(context.cache, self.cache)

    def test_extractor_context_net_income_caching(self):
        """Тест кеширования чистого дохода в контексте"""
        context = ExtractorContext(self.cache)

        # Первый вызов должен вычислить значение
        income1 = context.get_net_income()
        # Второй вызов должен вернуть закешированное значение
        income2 = context.get_net_income()

        self.assertEqual(income1, income2)
        # Проверяем, что значение было закешировано
        self.assertIsNotNone(context._net_income_cache)

    def test_build_interactions_data_structure(self):
        """Тест структуры данных взаимодействий"""
        tanks_cache = {
            "R01_IS": self.tank_is,
            "G04_PzVI_Tiger_I": self.tank_tiger
        }

        rows, summary = ExtractorV2.build_interactions_data(self.cache, tanks_cache)

        # Проверяем, что возвращается кортеж из двух элементов
        self.assertIsInstance(rows, list)
        self.assertIsInstance(summary, dict)

    def test_get_detailed_report_structure(self):
        """Тест структуры детального отчета"""
        result = ExtractorV2.get_detailed_report(self.cache)

        self.assertIsInstance(result, dict)
        # Проверяем основные секции
        self.assertIn("damage", result)
        self.assertIn("survival", result)
        self.assertIn("assistance", result)

    def test_death_reason_to_text_caching(self):
        """Тест кеширования преобразования причины смерти"""
        # Вызываем метод несколько раз с одним и тем же кодом
        text1 = ExtractorV2._death_reason_to_text(0)
        text2 = ExtractorV2._death_reason_to_text(0)
        text3 = ExtractorV2._death_reason_to_text(1)

        self.assertEqual(text1, "выстрелом")
        self.assertEqual(text2, "выстрелом")
        self.assertEqual(text3, "тараном")

        # Проверяем, что кеширование работает (результаты идентичны)
        self.assertEqual(text1, text2)

    def test_get_battle_type_by_gameplay_id_caching(self):
        """Тест кеширования определения типа боя по gameplay ID"""
        # Вызываем метод несколько раз
        type1 = ExtractorV2._get_battle_type_by_gameplay_id("ctf")
        type2 = ExtractorV2._get_battle_type_by_gameplay_id("ctf")
        type3 = ExtractorV2._get_battle_type_by_gameplay_id("domination")

        self.assertEqual(type1, "Стандартный бой")
        self.assertEqual(type2, "Стандартный бой")
        self.assertEqual(type3, "Господство")

        # Проверяем идентичность результатов (кеширование)
        self.assertEqual(type1, type2)

    def test_cache_usage_no_repeated_json_parsing(self):
        """Тест, что cache используется и нет повторного парсинга JSON"""
        # Создаём cache
        cache = ReplayDataCache(self.sample_payload)

        # Вызываем несколько методов
        ExtractorV2.get_personal_data_minimal(cache)
        ExtractorV2.get_details_data(cache)
        ExtractorV2.get_battle_outcome(cache)

        # Проверяем, что personal загружен только один раз
        self.assertIsNotNone(cache._personal)
        # При повторном обращении должен вернуться закешированный объект
        personal1 = cache.personal
        personal2 = cache.personal
        self.assertIs(personal1, personal2)


class TestExtractorV2Performance(TestCase):
    """Тесты производительности оптимизированных методов"""

    def setUp(self):
        """Создаёт большой тестовый payload с множеством игроков"""
        # Создаём 30 танков в БД
        self.tanks = {}
        for i in range(30):
            tank = Tank.objects.create(
                vehicleId=f"TEST_TANK_{i}",
                name=f"Test Tank {i}",
                level=7,
                type="mediumTank",
                nation="ussr"
            )
            self.tanks[f"TEST_TANK_{i}"] = tank

        # Создаём payload с 30 игроками
        players = {}
        avatars = {}
        vehicles = {}

        for i in range(30):
            player_id = str(10000 + i)
            players[player_id] = {
                "name": f"Player{i}",
                "realName": f"Player{i}",
                "team": 1 if i < 15 else 2
            }
            avatars[player_id] = {
                "vehicleType": f"ussr:TEST_TANK_{i}",
                "team": 1 if i < 15 else 2
            }
            vehicles[player_id] = [{
                "typeCompDescr": 10000 + i,
                "accountDBID": 10000 + i
            }]

        self.large_payload = [
            {
                "playerID": 10000,
                "playerName": "Player0",
                "playerVehicle": "ussr:TEST_TANK_0",
                "gameplayID": "ctf",
            },
            [
                {
                    "common": {"winnerTeam": 1, "finishReason": 1},
                    "personal": {
                        "10000": {
                            "accountDBID": 10000,
                            "xp": 1000,
                            "credits": 50000,
                            "achievements": []
                        }
                    },
                    "players": players,
                    "vehicles": vehicles
                },
                avatars
            ]
        ]

        self.cache = ReplayDataCache(self.large_payload)

    def test_build_interactions_data_with_many_players(self):
        """Тест обработки взаимодействий с большим количеством игроков"""
        import time

        tanks_cache = self.tanks

        start = time.perf_counter()
        rows, summary = ExtractorV2.build_interactions_data(self.cache, tanks_cache)
        elapsed = time.perf_counter() - start

        # Проверяем, что обработка быстрая (< 50ms)
        self.assertLess(elapsed, 0.05, f"Обработка заняла {elapsed*1000:.2f}ms, ожидалось < 50ms")

        # Проверяем корректность результата
        self.assertIsInstance(rows, list)
        self.assertIsInstance(summary, dict)

    def test_cache_efficiency_with_multiple_calls(self):
        """Тест эффективности кеша при множественных вызовах"""
        import time

        # Засекаем время первого вызова (с инициализацией кеша)
        start1 = time.perf_counter()
        result1 = ExtractorV2.get_personal_data_minimal(self.cache)
        elapsed1 = time.perf_counter() - start1

        # Засекаем время повторных вызовов (с использованием кеша)
        start2 = time.perf_counter()
        for _ in range(10):
            ExtractorV2.get_personal_data_minimal(self.cache)
        elapsed2 = time.perf_counter() - start2

        # Повторные вызовы должны быть быстрее (кеш работает)
        avg_cached = elapsed2 / 10
        self.assertLess(avg_cached, elapsed1,
                       f"Закешированные вызовы ({avg_cached*1000:.2f}ms) "
                       f"не быстрее первого ({elapsed1*1000:.2f}ms)")
