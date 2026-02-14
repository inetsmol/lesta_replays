# replays/models.py
from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from vote.models import VoteModel

User = get_user_model()


class Replay(VoteModel, models.Model):
    """
    Модель для хранения реплеев МИР ТАНКОВ с подробной статистикой боя.
    """
    # Ссылка на пользователя, который загрузил реплей
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replays',
        help_text="Пользователь, загрузивший реплей"
    )

    # НОВОЕ ПОЛЕ — короткое описание
    short_description = models.CharField(
        max_length=60,
        blank=True,
        default='',
        help_text="Короткое описание боя (до 60 символов)"
    )

    # Базовые поля файла
    file_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Имя файла в папке ./files"
    )
    payload = models.JSONField(help_text="Извлечённый JSON из реплея")
    created_at = models.DateTimeField(auto_now_add=True)
    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Количество просмотров реплея"
    )
    download_count = models.PositiveIntegerField(
        default=0,
        help_text="Количество скачиваний реплея"
    )

    # Связь с танком
    tank = models.ForeignKey(
        'Tank',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replays',
        help_text="Танк, на котором играл"
    )

    # Характеристики боя (уникальные для реплея)
    mastery = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Знак мастерства (0-4)"
    )

    # Информация о бою
    battle_date = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Дата и время боя"
    )
    map_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Внутреннее имя карты"
    )
    map_display_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Отображаемое название карты"
    )

    # Связь с картой
    map = models.ForeignKey(
        'Map',
        on_delete=models.PROTECT,          # карту нельзя удалить, если есть реплеи
        null=True,                         # временно допускаем NULL, пока не мигрируем
        blank=True,
        related_name='replays',
        help_text="Карта боя"
    )

    gameplay_id = models.CharField(
        max_length=100,
        default="ctf",
        null=True,
        blank=True,
        help_text="Режим игры"
    )

    battle_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="Режим боя (например: Стандартный бой, Штурм)"
    )

    # Статистика боя
    credits = models.IntegerField(
        default=0,
        help_text="Заработанные кредиты"
    )

    xp = models.PositiveIntegerField(
        default=0,
        help_text="Полученный опыт"
    )
    kills = models.PositiveSmallIntegerField(
        default=0,
        help_text="Количество уничтоженных танков"
    )
    damage = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Нанесённый урон"
    )
    assist = models.PositiveIntegerField(
        default=0,
        help_text="Помощь в уроне (все виды ассиста)"
    )
    block = models.PositiveIntegerField(
        default=0,
        help_text="Заблокированный бронёй урон"
    )

    game_version = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="Версия клиента игры (например: 1.26.0.3_13)"
    )

    # ИСПРАВЛЕНО: Связь с владельцем реплея
    owner = models.ForeignKey(
        'Player',
        on_delete=models.PROTECT,
        related_name='owned_replays',
        help_text="Игрок, который записал этот реплей"
    )

    # ИСПРАВЛЕНО: Все участники боя
    participants = models.ManyToManyField(
        'Player',
        related_name='participated_replays',
        blank=True,
        help_text="Все участники этого боя"
    )

    def get_absolute_url(self):
        # если детальная страница по pk:
        return reverse("replay_detail", kwargs={"pk": self.pk})

    def get_gameplay_display(self) -> str:
        """
        Возвращает читаемое название режима игры на основе gameplay_id.

        Returns:
            str: Название режима игры или пустую строку, если не определено
        """
        if not self.gameplay_id:
            return ""

        gameplay_map = {
            "assault": "Штурм",
            "ctf": "Стандартный бой",
            "ctf2": "Завоевание",
            "ctf30x30": "Генеральное сражение",
            "comp7": "Натиск",
            "comp7_1": "Натиск (Защита баз)",
            "comp7_2": "Натиск (Атака)",
            "domination": "Встречный бой",
            "domination3": "Столкновение",
            "domination30x30": "Генеральное сражение",
            "epic": "Линия фронта",
            "escort": "Эскорт",
            "fallout": "«Стальная охота»",
            "fallout1": "«Стальная охота»",
            "fallout2": "«Стальная охота»",
            "fallout3": "«Стальная охота»",
            "fallout4": "«Превосходство»",
            "fallout5": "«Превосходство»",
            "fallout6": "«Превосходство»",
            "maps_training": "Топография",
            "nations": "Противостояние",
            "rts": "Искусство стратегии",
            "rts_bootcamp": "Искусство стратегии",
            "winback": "Разминка"
        }

        return gameplay_map.get(self.gameplay_id, "")

    def get_battle_type_display(self) -> str:
        """
        Возвращает читаемое название типа боя на основе battle_type.

        Returns:
            str: Название типа боя или пустую строку, если не определено
        """
        if not self.battle_type:
            return ""

        try:
            code = int(self.battle_type)
        except (ValueError, TypeError):
            return ""

        code_map = {
            0: "Специальный бой",
            1: "Случайный бой",
            2: "Тренировочный бой",
            4: "Боевое обучение",
            5: "Командный бой",
            6: "Исторический бой",
            7: "Специальный игровой режим",
            8: "Вылазки",
            9: "Бой с кланом",
            10: "Командный бой: игра в Ладдере",
            11: "Учебный бой",
            12: "Учебный бой",
            13: "«Превосходство»",
            14: "«Стальная охота»",
            15: "Вылазка",
            16: "Наступление",
            17: "Ранговый бой",
            18: "«Превосходство»",
            19: "Случайный бой",
            20: "Тренировочный бой",
            21: "Линия фронта",
            22: "Линия фронта",
            23: "Стальной охотник",
            24: "Разведка боем",
            25: "Обучение на картах",
            26: "Искусство стратегии",
            27: "Линия фронта",
            28: "Основы стратегии",
            29: "«Стальной охотник»",
            30: "Натиск",
            31: "Разминка",
            32: "«Битва блогеров»",
            33: "Натиск",
            37: "«Разведка боем»",
            38: "«Топография»",
            42: "Полевые испытания",
            43: "Натиск",
            44: "Разминка",
            50: "Полигон",
            61: "Разлом",
            31000: "Полигон",
        }

        return code_map.get(code, "")

    class Meta:
        verbose_name = "Реплей"
        verbose_name_plural = "Реплеи"
        ordering = ["-battle_date", "-created_at"]
        indexes = [
            models.Index(fields=["battle_date", "damage"]),
            models.Index(fields=["tank", "battle_date"]),
            models.Index(fields=["map", "battle_date"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=['owner', 'battle_date', 'tank'], name='unique_replay_owner_battle_tank')
        ]


class Nation(models.TextChoices):
    """
    Список наций в соответствии с Танковедением tanki.su (RU-регион).
    """
    USSR = "ussr", "СССР"
    GERMANY = "germany", "Германия"
    USA = "usa", "США"
    CHINA = "china", "Китай"
    FRANCE = "france", "Франция"
    UK = "uk", "Великобритания"
    JAPAN = "japan", "Япония"
    CZECH = "czech", "Чехословакия"
    SWEDEN = "sweden", "Швеция"
    POLAND = "poland", "Польша"
    ITALY = "italy", "Италия"
    INTUNION = "intunion", "Сборная наций"


class Type(models.TextChoices):
    """
    храним slug типа: lightTank/mediumTank/heavyTank/AT-SPG/SPG
    """
    LIGHTTANK = "lightTank", "ЛТ"
    MEDIUMTANK = "mediumTank", "СТ"
    HEAVYTANK = "heavyTank", "ТТ"
    AT_SPG = "AT-SPG", "ПТ-САУ"
    SPG = "SPG", "САУ"


class Tank(models.Model):
    """
    Минимальный набор полей для списка техники.
    """
    vehicleId = models.CharField(max_length=64, unique=True, help_text="Напр.: R174_BT-5")
    name = models.CharField(max_length=128)
    level = models.PositiveSmallIntegerField()
    type = models.CharField(
        max_length=64,
        choices=Type.choices,
    )
    nation = models.CharField(
        max_length=32,
        choices=Nation.choices,
        db_index=True,
        null=True,
        help_text="Страна/нация (slug из Танкопедии)"
    )


class Achievement(models.Model):
    """Модель для хранения информации о достижениях"""
    achievement_id = models.IntegerField(unique=True, primary_key=True)  # числовой ID из клиента/реплея
    token = models.CharField(max_length=100, unique=True, null=True, blank=True)  # текстовый ключ из API: shootToKill

    # Основное
    name = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    condition = models.TextField(blank=True, verbose_name="Условия получения")

    # Доп. сведения из API
    section = models.CharField(max_length=50, blank=True, verbose_name="Секция")          # e.g. achievements, singleAchievements
    api_type = models.CharField(max_length=50, blank=True, verbose_name="Тип из API")     # чтобы не пересекаться с choices
    hero_info = models.TextField(blank=True, verbose_name="Ист. справка")
    outdated = models.BooleanField(default=False, verbose_name="Снято из получения")
    order = models.IntegerField(null=True, blank=True, verbose_name="Порядок в секции")
    section_order = models.IntegerField(null=True, blank=True, verbose_name="Порядок секции")

    # Пути к ЛОКАЛЬНЫМ изображениям
    image_big = models.CharField(max_length=500, blank=True, verbose_name="Большое изображение")
    image_small = models.CharField(max_length=500, blank=True, verbose_name="Маленькое изображение")

    # Тип для ваших отображений/фильтров
    achievement_type = models.CharField(max_length=50, choices=[
        ('battle', 'Боевое'),
        ('mastery', 'Мастерство'),
        ('epic', 'Эпическое'),
        ('special', 'Специальное'),
    ], default='battle')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Достижение"
        verbose_name_plural = "Достижения"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (ID: {self.achievement_id}, section: {self.section})"


class MarksOnGun(models.Model):
    """
    Модель для хранения информации об отметках на стволе.

    Отметки на стволе (Marks of Excellence) - это особое достижение,
    которое имеет 3 уровня (1, 2, 3 отметки) и зависит от нации танка.
    """
    # Уровень отметок (1, 2 или 3)
    marks_count = models.PositiveSmallIntegerField(
        unique=True,
        verbose_name="Количество отметок",
        help_text="1, 2 или 3 отметки"
    )

    # Основная информация
    name = models.CharField(
        max_length=200,
        verbose_name="Название",
        help_text="Например: '1 отличительная отметка'"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание",
        help_text="Условия получения данного уровня отметок"
    )

    # Общая информация (одинаковая для всех уровней)
    general_condition = models.TextField(
        blank=True,
        verbose_name="Общие условия",
        help_text="Общие правила получения отметок (из поля condition API)"
    )
    general_description = models.TextField(
        blank=True,
        verbose_name="Общее описание",
        help_text="Общее описание системы отметок"
    )

    # JSON с изображениями по нациям
    # Формат: {"usa": "url", "ussr": "url", "germany": "url", ...}
    nation_images = models.JSONField(
        default=dict,
        verbose_name="Изображения по нациям",
        help_text="Словарь URL изображений для каждой нации"
    )

    # Метаданные
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Отметка на стволе"
        verbose_name_plural = "Отметки на стволе"
        ordering = ['marks_count']

    def __str__(self):
        return f"{self.marks_count} отметка(и): {self.name}"

    def get_image_for_nation(self, nation: str) -> str:
        """
        Получить URL изображения для указанной нации.

        Args:
            nation: код нации (usa, ussr, germany, france, etc.)

        Returns:
            URL изображения или пустая строка, если не найдено
        """
        return self.nation_images.get(nation, '')


class Player(models.Model):
    """
    Игрок World of Tanks.

    ВАЖНО: Уникальность игрока определяется по accountDBID - постоянному ID игрока в БД.

    Поля имен:
    - accountDBID: Уникальный ID игрока из базы данных Lesta/WG (ключевое поле!)
    - real_name: Настоящее игровое имя (из players[accountDBID]['realName'])
    - fake_name: Имя, отображавшееся в бою (из players[accountDBID]['name'])

    Связь с секциями battle_result.json:
    - accountDBID - ключ в payload[1][0]['players']
    - real_name = players[accountDBID]['realName']
    - fake_name = players[accountDBID]['name']

    Примеры:
    1. Игрок БЕЗ анонимизации: real_name = fake_name = "PlayerName"
    2. Игрок С анонимизацией: real_name = "RealPlayer", fake_name = "Anon_12345"
    """
    accountDBID = models.BigIntegerField(
        "ID игрока",
        unique=True,
        db_index=True,
        null=True,  # Временно для миграции, потом удалим
        help_text="Уникальный ID игрока из базы данных Lesta/WG"
    )
    real_name = models.CharField(
        "Настоящее имя",
        max_length=50,
        db_index=True,
        help_text="Настоящее игровое имя (players.realName)"
    )
    fake_name = models.CharField(
        "Имя в бою",
        max_length=50,
        db_index=True,
        default="",  # Временно для миграции
        help_text="Имя, отображавшееся в бою (players.name, анонимное если скрыто)"
    )
    clan_tag = models.CharField(
        "Клан",
        max_length=10,
        blank=True,
        default="",
        help_text="Тег клана без скобок, например: RED"
    )

    class Meta:
        verbose_name = "Игрок"
        verbose_name_plural = "Игроки"
        ordering = ["real_name"]
        indexes = [
            models.Index(fields=["accountDBID"]),
            models.Index(fields=["real_name"]),
            models.Index(fields=["fake_name"]),
            models.Index(fields=["clan_tag"]),
        ]

    def __str__(self) -> str:
        # Отображаем реальное имя игрока
        return f"[{self.clan_tag}] {self.real_name}" if self.clan_tag else self.real_name


class Map(models.Model):
    map_name = models.CharField(
        "Уникальный ключ",
        max_length=50,
        unique=True,
        help_text="Уникальный ключ"
    )

    map_display_name = models.CharField(
        "Русское название карты",
        max_length=50,
        db_index=True,
        help_text="Русское название карты"
    )


class UserProfile(models.Model):
    """
    Расширение модели User для хранения дополнительной информации.

    Связь один-к-одному с Django User.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        help_text="Связь с пользователем Django"
    )

    lesta_account_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Account ID из Lesta Games API"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self):
        return f"Профиль {self.user.username}"


class APIUsageLog(models.Model):
    """
    Счётчик вызовов API endpoint'ов по пользователям.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='api_usage_logs',
        verbose_name="Пользователь",
    )
    endpoint = models.CharField(
        "Endpoint",
        max_length=100,
        db_index=True,
        help_text="Имя API endpoint'а (например, api_replay_info)",
    )
    call_count = models.PositiveIntegerField(
        "Количество вызовов",
        default=0,
    )
    last_called_at = models.DateTimeField(
        "Последний вызов",
        auto_now=True,
    )

    class Meta:
        unique_together = ('user', 'endpoint')
        verbose_name = "Статистика API"
        verbose_name_plural = "Статистика API"

    def __str__(self):
        return f"{self.user.username} — {self.endpoint}: {self.call_count}"
