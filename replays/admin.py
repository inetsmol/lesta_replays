# replays/admin.py
from django.contrib import admin
from django.utils import timezone

from .models import (
    Tank, Player, Replay, Map, UserProfile, Achievement, AchievementOption, MarksOnGun, APIUsageLog,
    SubscriptionPlan, UserSubscription, DailyUsage, ReplayVideoLink, ReplayStatBattle, ReplayStatPlayer,
)


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


class AchievementOptionInline(admin.TabularInline):
    model = AchievementOption
    extra = 0
    fields = ("rank", "name", "image_small", "image_big")
    ordering = ("rank",)


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("achievement_id", "name", "section", "outdated")
    list_display_links = ("achievement_id", "name")
    search_fields = ("name", "token", "description")
    list_filter = ("section", "outdated")
    ordering = ("section_order", "order", "name")
    readonly_fields = ("achievement_id",)
    inlines = (AchievementOptionInline,)


@admin.register(MarksOnGun)
class MarksOnGunAdmin(admin.ModelAdmin):
    list_display = ("marks_count", "name", "is_active", "updated_at")
    list_display_links = ("marks_count", "name")
    search_fields = ("name", "description")
    list_filter = ("is_active",)
    ordering = ("marks_count",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(APIUsageLog)
class APIUsageLogAdmin(admin.ModelAdmin):
    list_display = ("user", "endpoint", "call_count", "last_called_at")
    list_filter = ("endpoint",)
    search_fields = ("user__username",)
    ordering = ("-call_count",)
    readonly_fields = ("user", "endpoint", "call_count", "last_called_at")


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price_monthly", "price_yearly", "daily_upload_limit",
                    "daily_download_limit", "max_video_links", "is_active")
    list_editable = ("price_monthly", "price_yearly", "is_active")
    list_display_links = ("name",)


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "started_at", "expires_at", "is_active",
                    "activated_by", "subscription_status")
    list_filter = ("plan", "is_active", "activated_by")
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user",)
    list_editable = ("is_active",)
    actions = ["extend_30_days", "extend_90_days", "deactivate"]

    @admin.display(description="Статус")
    def subscription_status(self, obj):
        if not obj.is_active:
            return "Отключена"
        if obj.is_expired:
            return "Истекла"
        return "Активна"

    @admin.action(description="Продлить на 30 дней")
    def extend_30_days(self, request, queryset):
        import datetime
        now = timezone.now()
        for sub in queryset:
            base = sub.expires_at if sub.expires_at and sub.expires_at > now else now
            sub.expires_at = base + datetime.timedelta(days=30)
            sub.is_active = True
            sub.save()
        self.message_user(request, f"Продлено {queryset.count()} подписок на 30 дней.")

    @admin.action(description="Продлить на 90 дней")
    def extend_90_days(self, request, queryset):
        import datetime
        now = timezone.now()
        for sub in queryset:
            base = sub.expires_at if sub.expires_at and sub.expires_at > now else now
            sub.expires_at = base + datetime.timedelta(days=90)
            sub.is_active = True
            sub.save()
        self.message_user(request, f"Продлено {queryset.count()} подписок на 90 дней.")

    @admin.action(description="Деактивировать подписки")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"Деактивировано {queryset.count()} подписок.")


@admin.register(DailyUsage)
class DailyUsageAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "uploads", "downloads")
    list_filter = ("date",)
    search_fields = ("user__username",)
    readonly_fields = ("user", "date", "uploads", "downloads")


@admin.register(ReplayVideoLink)
class ReplayVideoLinkAdmin(admin.ModelAdmin):
    list_display = ("replay", "platform", "url", "added_by", "created_at")
    list_filter = ("platform",)
    search_fields = ("url", "added_by__username")
    raw_id_fields = ("replay", "added_by")


@admin.register(ReplayStatBattle)
class ReplayStatBattleAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "battle_date", "outcome", "map_display_name",
        "arena_unique_id", "battle_signature",
    )
    list_filter = ("outcome", "battle_date")
    search_fields = ("user__username", "map_display_name", "map_name", "battle_signature")
    raw_id_fields = ("user",)


@admin.register(ReplayStatPlayer)
class ReplayStatPlayerAdmin(admin.ModelAdmin):
    list_display = (
        "id", "battle", "player_name", "player_account_id",
        "tank_name", "damage", "xp", "kills",
    )
    list_filter = ("battle__battle_date",)
    search_fields = ("player_name", "tank_name", "battle__user__username")
    raw_id_fields = ("battle", "tank")
