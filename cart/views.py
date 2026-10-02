from django.contrib import messages
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from catalog.models import ProductVariant
from .cart import Cart

def detail(request): return render(request, "cart/detail.html")

@require_POST
def add(request, variant_id):
    variant = get_object_or_404(ProductVariant.objects.select_related("product"), id=variant_id, active=True, product__active=True)
    try: quantity = int(request.POST.get("quantity", 1))
    except ValueError: return HttpResponseBadRequest("Cantidad inválida")
    if quantity < 1 or variant.stock < quantity:
        messages.error(request, "No hay existencias suficientes para esa variante.")
    else:
        Cart(request).add(variant, quantity); messages.success(request, "Producto agregado al carrito.")
    return redirect(request.POST.get("next") or "cart:detail")

@require_POST
def update(request, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id)
    try: quantity = int(request.POST.get("quantity", 1))
    except ValueError: quantity = 1
    if quantity <= 0: Cart(request).remove(variant.id)
    elif quantity <= variant.stock: Cart(request).add(variant, quantity, replace=True)
    else: messages.error(request, "La cantidad supera las existencias disponibles.")
    return redirect("cart:detail")

@require_POST
def remove(request, variant_id): Cart(request).remove(variant_id); return redirect("cart:detail")
