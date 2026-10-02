from django.contrib import admin
from .models import Category, Product, ProductImage, ProductVariant

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "active"); list_filter = ("active",); search_fields = ("name",); prepopulated_fields = {"slug": ("name",)}

class VariantInline(admin.TabularInline): model = ProductVariant; extra = 1
class ImageInline(admin.TabularInline): model = ProductImage; extra = 1

@admin.action(description="Marcar seleccionados como destacados")
def make_featured(modeladmin, request, queryset): queryset.update(featured=True)
@admin.action(description="Activar productos seleccionados")
def activate(modeladmin, request, queryset): queryset.update(active=True)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "current_price", "active", "featured", "stock_total")
    list_filter = ("active", "featured", "gender", "category", "brand")
    search_fields = ("name", "sku", "brand", "model")
    prepopulated_fields = {"slug": ("name",)}
    actions = (make_featured, activate); inlines = (VariantInline, ImageInline)
    def stock_total(self, obj): return sum(v.stock for v in obj.variants.all())
    stock_total.short_description = "Existencias"

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "size", "color", "sku", "stock", "active"); list_filter = ("active", "size", "color"); search_fields = ("sku", "product__name")
