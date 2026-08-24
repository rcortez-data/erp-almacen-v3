from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from .models import Category, Product, ProductVariant
class CatalogTests(TestCase):
    def setUp(self):
        self.category=Category.objects.create(name="Tenis",slug="tenis")
        self.product=Product.objects.create(category=self.category,name="Demo",slug="demo",sku="D1",price=Decimal("500"),sale_price=Decimal("400"))
        self.variant=ProductVariant.objects.create(product=self.product,size="25",color="Negro",sku="D1-25-N",stock=2)
    def test_current_price_and_stock(self): self.assertEqual(self.product.current_price,Decimal("400")); self.assertTrue(self.product.in_stock)
    def test_invalid_sale_price(self):
        self.product.sale_price=Decimal("600")
        with self.assertRaises(ValidationError): self.product.full_clean()
    def test_catalog_search(self): self.assertContains(self.client.get("/catalogo/",{"q":"D1"}),"Demo")
