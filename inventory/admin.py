from django.contrib import admin
from .models import Product, InventoryHistory, RestockSchedule


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "stock", "is_active", "qr_token", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "qr_token")


@admin.register(InventoryHistory)
class InventoryHistoryAdmin(admin.ModelAdmin):
    list_display = ("product", "change_type", "quantity", "created_at")
    list_filter = ("change_type",)
    search_fields = ("product__name",)


@admin.register(RestockSchedule)
class RestockScheduleAdmin(admin.ModelAdmin):
    list_display = ("product", "quantity", "scheduled_at", "processed", "created_at")
    list_filter = ("processed",)
    search_fields = ("product__name",)
