from decimal import Decimal
from catalog.models import ProductVariant

class Cart:
    session_key = "cart"
    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(self.session_key, {})
    def add(self, variant, quantity=1, replace=False):
        key = str(variant.id); current = self.data.get(key, 0)
        self.data[key] = quantity if replace else current + quantity
        self.data[key] = max(1, min(self.data[key], variant.stock)); self.save()
    def remove(self, variant_id): self.data.pop(str(variant_id), None); self.save()
    def clear(self): self.session.pop(self.session_key, None); self.session.modified = True
    def save(self): self.session[self.session_key] = self.data; self.session.modified = True
    def __len__(self): return sum(self.data.values())
    def __iter__(self):
        variants = ProductVariant.objects.filter(id__in=self.data).select_related("product").prefetch_related("product__images")
        for variant in variants:
            quantity = self.data[str(variant.id)]
            yield {"variant": variant, "product": variant.product, "quantity": quantity, "unit_price": variant.product.current_price, "total": variant.product.current_price * quantity}
    @property
    def subtotal(self): return sum((item["total"] for item in self), Decimal("0"))
