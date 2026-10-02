from decimal import Decimal
from django.test import TestCase
from catalog.models import Category,Product,ProductVariant
class CartTests(TestCase):
    def setUp(self):
        c=Category.objects.create(name="Tenis",slug="tenis"); p=Product.objects.create(category=c,name="Demo",slug="demo",sku="D",price=Decimal("100")); self.v=ProductVariant.objects.create(product=p,size="25",color="Negro",sku="DV",stock=2)
    def test_add_and_limit_stock(self):
        self.client.post(f"/carrito/agregar/{self.v.id}/",{"quantity":2}); response=self.client.get("/carrito/"); self.assertContains(response,"$200.00")
        self.client.post(f"/carrito/agregar/{self.v.id}/",{"quantity":3}); self.assertEqual(self.client.session["cart"][str(self.v.id)],2)
    def test_csrf_method_required(self): self.assertEqual(self.client.get(f"/carrito/agregar/{self.v.id}/").status_code,405)
