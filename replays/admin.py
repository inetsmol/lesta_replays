# replays/admin.py
from django.contrib import admin
from .models import Tank, Player, Replay


@admin.register(Tank)
class TankAdmin(admin.ModelAdmin):
    list_display = ("vehicleId", "name", "level", "type", "nation")
    list_display_links = ("vehicleId", "name")
    search_fields = ("vehicleId", "name")
    list_filter = ("level", "type", "nation")
    ordering = ("level", "name")

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("real_name", "name", "clan_tag")
    search_fields = ("real_name", "name", "clan_tag")

@admin.register(Replay)
class ReplayAdmin(admin.ModelAdmin):
    list_display = ("file_name", "tank", "battle_date", "damage", "xp")
    list_filter = ("tank", "battle_date", "game_version", "battle_type")
    search_fields = ("file_name", "map_display_name", "map_name")
    filter_horizontal = ("participants",)  # удобный M2M виджет
