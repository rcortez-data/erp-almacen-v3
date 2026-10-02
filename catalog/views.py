from decimal import Decimal, InvalidOperation
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from .models import Category, Product

def product_list(request):
    products = Product.objects.available().select_related("category")
    q = request.GET.get("q", "").strip()
    if q: products = products.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(model__icontains=q) | Q(sku__icontains=q))
    filters = {"category__slug": "categoria", "gender": "genero", "variants__size": "talla", "variants__color": "color"}
    for field, param in filters.items():
        if request.GET.get(param): products = products.filter(**{field: request.GET[param]})
    if request.GET.get("disponible") == "1": products = products.filter(variants__stock__gt=0, variants__active=True)
    try:
        if request.GET.get("precio_min"): products = products.filter(price__gte=Decimal(request.GET["precio_min"]))
        if request.GET.get("precio_max"): products = products.filter(price__lte=Decimal(request.GET["precio_max"]))
    except InvalidOperation: pass
    order = request.GET.get("orden", "nuevos")
    products = products.order_by({"precio_asc": "price", "precio_desc": "-price", "nombre": "name"}.get(order, "-created_at")).distinct()
    from django.core.paginator import Paginator
    page = Paginator(products, 12).get_page(request.GET.get("page"))
    active_products = Product.objects.available()
    context = {"page_obj": page, "categories": Category.objects.filter(active=True), "sizes": sorted(set(active_products.values_list("variants__size", flat=True))), "colors": sorted(set(active_products.values_list("variants__color", flat=True))), "filters": request.GET}
    return render(request, "catalog/list.html", context)

def product_detail(request, slug):
    product = get_object_or_404(Product.objects.available().select_related("category"), slug=slug)
    return render(request, "catalog/detail.html", {"product": product, "variants": product.variants.filter(active=True)})
