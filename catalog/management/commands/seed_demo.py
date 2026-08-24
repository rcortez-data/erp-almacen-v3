from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from catalog.models import Category, Product, ProductVariant

class Command(BaseCommand):
    help = "Crea un catálogo de demostración sin imágenes ni marcas protegidas"
    def handle(self, *args, **options):
        data = [
            ("Tenis", "Paso Urbano", "Demo", "PU-001", "899.00", "699.00", "unisex", ["23","24","25","26"], ["Negro","Blanco"]),
            ("Casual", "Línea Nómada", "Demo", "LN-002", "1099.00", None, "mujer", ["23","24","25"], ["Arena","Café"]),
            ("Deportivo", "Impulso Runner", "Demo", "IR-003", "1299.00", "999.00", "hombre", ["26","27","28"], ["Azul","Gris"]),
            ("Infantil", "Mini Aventura", "Demo", "MA-004", "649.00", None, "infantil", ["18","19","20","21"], ["Rosa","Azul"]),
            ("Sandalias", "Brisa Ligera", "Demo", "BL-005", "549.00", None, "mujer", ["23","24","25"], ["Negro","Natural"]),
            ("Botas", "Ruta Norte", "Demo", "RN-006", "1499.00", "1199.00", "hombre", ["26","27","28"], ["Café"]),
        ]
        for category_name, name, brand, sku, price, sale, gender, sizes, colors in data:
            category,_=Category.objects.get_or_create(name=category_name,defaults={"slug":slugify(category_name)})
            product,_=Product.objects.update_or_create(sku=sku,defaults={"category":category,"name":name,"slug":slugify(f"{name}-{sku}"),"brand":brand,"model":sku,"gender":gender,"description":"Producto de demostración. Sustituye esta información con datos autorizados del catálogo.","price":Decimal(price),"sale_price":Decimal(sale) if sale else None,"active":True,"featured":True})
            for size in sizes:
                for color in colors: ProductVariant.objects.update_or_create(sku=f"{sku}-{size}-{color[:2].upper()}",defaults={"product":product,"size":size,"color":color,"stock":8,"active":True})
        self.stdout.write(self.style.SUCCESS("Catálogo demo creado correctamente."))
