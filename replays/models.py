# replays/models.py
from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse

User = get_user_model()


class Replay(models.Model):
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


