from django.shortcuts import render
from catalog.models import Category, Product

def home(request):
    return render(request, "core/home.html", {"featured": Product.objects.available().filter(featured=True)[:8], "categories": Category.objects.filter(parent__isnull=True, active=True)[:8]})

def legal(request, page):
    pages = {
        "privacidad": ("Aviso de privacidad", "Tratamos tus datos exclusivamente para procesar pedidos, entregas y atención al cliente."),
        "terminos": ("Términos y condiciones", "Los precios, existencias y tiempos de entrega se confirman antes de procesar cada pedido."),
        "envios": ("Política de envíos", "El costo y plazo de entrega dependen del destino y se informan durante la confirmación."),
        "devoluciones": ("Cambios y devoluciones", "Solicita un cambio dentro del plazo informado, conservando el producto sin uso y su empaque."),
        "contacto": ("Contacto", "Escríbenos por WhatsApp para recibir atención personalizada."),
    }
    title, content = pages[page]
    return render(request, "core/legal.html", {"title": title, "content": content})

def robots(request):
    from django.http import HttpResponse
    return HttpResponse("User-agent: *\nAllow: /\nSitemap: " + request.build_absolute_uri("/sitemap.xml"), content_type="text/plain")
