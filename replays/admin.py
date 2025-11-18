# replays/admin.py
from django.contrib import admin
from .models import Tank, Player, Replay, Map, UserProfile


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
