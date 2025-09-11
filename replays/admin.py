# replays/admin.py
from django.contrib import admin
from .models import Tank

@admin.register(Tank)
class TankAdmin(admin.ModelAdmin):
    list_display = ("vehicleId", "name", "level", "type", "nation")
    list_display_links = ("vehicleId", "name")
    search_fields = ("vehicleId", "name")
    list_filter = ("level", "type", "nation")
    ordering = ("level", "name")
