from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from catalog.models import Category,Product,ProductVariant
from .models import Order
class OrderFlowTests(TestCase):
    def setUp(self):
        c=Category.objects.create(name="Tenis",slug="tenis"); p=Product.objects.create(category=c,name="Demo",slug="demo",sku="D",price=Decimal("100")); self.v=ProductVariant.objects.create(product=p,size="25",color="Negro",sku="DV",stock=2)
    def test_guest_checkout_decrements_stock(self):
        self.client.post(f"/carrito/agregar/{self.v.id}/",{"quantity":2})
        response=self.client.post("/pedidos/finalizar/",{"name":"Cliente Demo","phone":"5512345678","email":"demo@example.com","address":"Calle 1, Ciudad","delivery_method":"shipping","notes":""})
        order=Order.objects.get(); self.assertRedirects(response,f"/pedidos/confirmado/{order.number}/"); self.v.refresh_from_db(); self.assertEqual(self.v.stock,0); self.assertEqual(order.total,Decimal("299.00")); self.assertNotIn("cart",self.client.session)
    def test_order_history_requires_login(self): self.assertEqual(self.client.get("/cuenta/perfil/").status_code,302)
    def test_user_order_is_private(self):
        user=User.objects.create_user("one",password="test-pass-123"); other=User.objects.create_user("two",password="test-pass-123")
        order=Order.objects.create(user=user,name="One",phone="5512345678",email="a@a.com",address="x",delivery_method="pickup",subtotal=0,shipping=0,total=0)
        self.client.force_login(other); self.assertRedirects(self.client.get(f"/pedidos/confirmado/{order.number}/"),"/")
