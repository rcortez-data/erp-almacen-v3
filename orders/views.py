from urllib.parse import quote
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from cart.cart import Cart
from .forms import CheckoutForm
from .models import Order
from .services import create_order

def checkout(request):
    cart = Cart(request)
    if not len(cart): messages.info(request, "Agrega productos antes de finalizar el pedido."); return redirect("catalog:list")
    initial = {}
    if request.user.is_authenticated: initial = {"name": request.user.get_full_name(), "email": request.user.email}
    form = CheckoutForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            order = create_order(cart, form, request.user)
            if not request.user.is_authenticated:
                guest_orders = request.session.get("guest_orders", [])
                request.session["guest_orders"] = (guest_orders + [order.number])[-10:]
            return redirect("orders:success", number=order.number)
        except ValidationError as exc: form.add_error(None, exc.message)
    return render(request, "orders/checkout.html", {"form": form, "cart": cart})

def success(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number)
    allowed_guest = not order.user and order.number in request.session.get("guest_orders", [])
    allowed_user = order.user and order.user == request.user
    if not (allowed_guest or allowed_user or request.user.is_staff): return redirect("core:home")
    lines = [f"Hola, quiero confirmar el pedido {order.number}:"] + [f"• {i.product_name} ({i.variant_label}) x{i.quantity} — ${i.total}" for i in order.items.all()] + [f"Total: ${order.total}", f"Cliente: {order.name}"]
    whatsapp_url = f"https://wa.me/{settings.WHATSAPP_NUMBER}?text={quote(chr(10).join(lines))}"
    return render(request, "orders/success.html", {"order": order, "whatsapp_url": whatsapp_url})
