import secrets
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

def order_number(): return "WPS-" + secrets.token_hex(4).upper()

class Order(models.Model):
    class Status(models.TextChoices):
        NEW="new","Nuevo"; CONFIRMED="confirmed","Confirmado"; PAID="paid","Pagado"; PREPARING="preparing","Preparando"; SHIPPED="shipped","Enviado"; DELIVERED="delivered","Entregado"; CANCELLED="cancelled","Cancelado"
    class Delivery(models.TextChoices): SHIPPING="shipping","Envío a domicilio"; PICKUP="pickup","Recoger en punto de entrega"
    number = models.CharField("folio", max_length=20, unique=True, default=order_number, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="cliente", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    name = models.CharField("nombre completo", max_length=160)
    phone = models.CharField("teléfono", max_length=20)
    email = models.EmailField("correo electrónico")
    address = models.TextField("dirección")
    delivery_method = models.CharField("método de entrega", max_length=20, choices=Delivery.choices)
    notes = models.TextField("notas", blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    shipping = models.DecimalField("envío", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True); updated_at = models.DateTimeField(auto_now=True)
    class Meta: verbose_name="pedido"; verbose_name_plural="pedidos"; ordering=["-created_at"]
    def __str__(self): return self.number

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.ProductVariant", null=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=180); variant_label = models.CharField(max_length=100); sku = models.CharField(max_length=80)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2); quantity = models.PositiveIntegerField(); total = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self): return f"{self.product_name} × {self.quantity}"
