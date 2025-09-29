# replays/models.py
from django.db import models


class Replay(models.Model):
    """
    Модель для хранения реплеев МИР ТАНКОВ с подробной статистикой боя.
    """
    # НОВОЕ ПОЛЕ — короткое описание
    short_description = models.CharField(
        max_length=60,
        blank=True,
        default='',
        help_text="Короткое описание боя (до 200 символов)"
    )

    # Базовые поля файла
    file_name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Имя файла в папке ./files"
    )
    payload = models.JSONField(help_text="Извлечённый JSON из реплея")
    created_at = models.DateTimeField(auto_now_add=True)

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

    battle_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="Режим боя (например: Стандартный бой, Штурм)"
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

    class Meta:
        verbose_name = "Реплей"
        verbose_name_plural = "Реплеи"
        ordering = ["-battle_date", "-created_at"]
        indexes = [
            models.Index(fields=["battle_date", "damage"]),
            models.Index(fields=["tank", "battle_date"]),
        ]

    def __str__(self) -> str:
        if self.tank and self.battle_date:
            return f"{self.tank.name} - {self.battle_date.strftime('%d.%m.%Y %H:%M')}"
        return self.file_name


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

    def __str__(self) -> str:
        return f"{self.name} (lvl {self.level}, {self.type}, {self.nation or '?'})"


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
    """
    name = models.CharField(
        "Логин",
        max_length=50,
        unique=True,
        help_text="Игровой логин (уникален в рамках сервера)"
    )
    real_name = models.CharField(
        "Ник",
        max_length=50,
        db_index=True,
        default="",
        help_text="Игровой ник"
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
            models.Index(fields=["real_name"]),
            models.Index(fields=["clan_tag"]),
        ]

    def __str__(self) -> str:
        return f"[{self.clan_tag}] {self.name}" if self.clan_tag else self.name


class Map(models.Model):
    map_name = models.CharField(
        "Ник",
        max_length=50,
        unique=True,
        help_text="Уникальный ключ"
    )

    map_display_name = models.CharField(
        "Ник",
        max_length=50,
        db_index=True,
        help_text="Русское название карты"
    )

    image = models.CharField(max_length=500, blank=True, verbose_name="Изображение")