from django.contrib import admin

from .models import RateLimit


@admin.register(RateLimit)
class RateLimitAdmin(admin.ModelAdmin):
    list_display = ("user", "endpoint", "count", "reset_at", "updated_at")
    list_filter = ("endpoint",)
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at")
