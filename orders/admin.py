from django.contrib import admin
from .models import Order, OrderItem
class ItemInline(admin.TabularInline): model=OrderItem; extra=0; readonly_fields=("product_name","variant_label","sku","unit_price","quantity","total"); can_delete=False
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display=("number","name","status","total","created_at"); list_filter=("status","delivery_method","created_at"); search_fields=("number","name","email","phone"); readonly_fields=("number","subtotal","shipping","total","created_at","updated_at"); inlines=(ItemInline,); list_editable=("status",)
