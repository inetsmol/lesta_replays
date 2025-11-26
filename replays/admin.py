# replays/admin.py
from django.contrib import admin
from .models import Tank, Player, Replay, Map, UserProfile, Achievement, MarksOnGun


@admin.register(Tank)
class TankAdmin(admin.ModelAdmin):
    list_display = ("id", "vehicleId", "name", "level", "type", "nation")
    list_display_links = ("vehicleId", "name")
    search_fields = ("vehicleId", "name")
    list_filter = ("level", "type", "nation")
    ordering = ("level", "name")

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("id", "accountDBID", "real_name", "fake_name", "clan_tag")
    search_fields = ("real_name", "fake_name", "clan_tag")
    list_filter = ("clan_tag",)

@admin.register(Replay)
class ReplayAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "tank", "battle_date", "damage", "xp")
    list_filter = ("id", "tank", "battle_date", "game_version", "battle_type")
    search_fields = ("id", "file_name", "map_display_name", "map_name")
    filter_horizontal = ("participants",)  # удобный M2M виджет

@admin.register(Map)
class MapAdmin(admin.ModelAdmin):
    list_display = ("id", "map_name", "map_display_name")
    search_fields = ("id", "map_name", "map_display_name")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "lesta_account_id", "created_at")
    search_fields = ("user__username", "lesta_account_id")
    list_filter = ("created_at",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("achievement_id", "name", "achievement_type", "section", "outdated")
    list_display_links = ("achievement_id", "name")
    search_fields = ("name", "token", "description")
    list_filter = ("achievement_type", "section", "outdated")
    ordering = ("section_order", "order", "name")
    readonly_fields = ("achievement_id",)


@admin.register(MarksOnGun)
class MarksOnGunAdmin(admin.ModelAdmin):
    list_display = ("marks_count", "name", "is_active", "updated_at")
    list_display_links = ("marks_count", "name")
    search_fields = ("name", "description")
    list_filter = ("is_active",)
    ordering = ("marks_count",)
    readonly_fields = ("created_at", "updated_at")
