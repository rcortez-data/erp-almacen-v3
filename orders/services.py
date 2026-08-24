from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from catalog.models import ProductVariant
from .models import Order, OrderItem

@transaction.atomic
def create_order(cart, form, user=None):
    items = list(cart)
    if not items: raise ValidationError("El carrito está vacío.")
    locked = {v.id: v for v in ProductVariant.objects.select_for_update().filter(id__in=[i["variant"].id for i in items])}
    for item in items:
        variant = locked.get(item["variant"].id)
        if not variant or not variant.active or variant.stock < item["quantity"]: raise ValidationError(f"Existencias insuficientes para {item['product'].name}.")
    subtotal = sum((i["total"] for i in items), Decimal("0"))
    shipping = Decimal("0") if form.cleaned_data["delivery_method"] == Order.Delivery.PICKUP else Decimal(settings.SHIPPING_COST)
    order = form.save(commit=False); order.user = user if getattr(user, "is_authenticated", False) else None; order.subtotal=subtotal; order.shipping=shipping; order.total=subtotal+shipping; order.save()
    for item in items:
        variant = locked[item["variant"].id]; variant.stock -= item["quantity"]; variant.save(update_fields=["stock"])
        OrderItem.objects.create(order=order, variant=variant, product_name=item["product"].name, variant_label=f"Talla {variant.size} · {variant.color}", sku=variant.sku, unit_price=item["unit_price"], quantity=item["quantity"], total=item["total"])
    cart.clear(); return order
