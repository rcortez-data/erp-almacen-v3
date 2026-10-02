import csv
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from catalog.models import Category, Product, ProductVariant

class Command(BaseCommand):
    help = "Importa productos y variantes desde CSV UTF-8"
    def add_arguments(self, parser): parser.add_argument("csv_file")
    @transaction.atomic
    def handle(self, *args, **options):
        try:
            with open(options["csv_file"], encoding="utf-8-sig", newline="") as handle:
                rows = csv.DictReader(handle)
                required = {"product_sku", "name", "category", "price", "variant_sku", "size", "color", "stock"}
                if not required.issubset(rows.fieldnames or []): raise CommandError("Faltan columnas requeridas: " + ", ".join(sorted(required)))
                count = 0
                for row in rows:
                    category, _ = Category.objects.get_or_create(name=row["category"].strip(), defaults={"slug": slugify(row["category"])})
                    product, _ = Product.objects.update_or_create(sku=row["product_sku"].strip(), defaults={"name": row["name"].strip(), "slug": slugify(f'{row["name"]}-{row["product_sku"]}'), "category": category, "price": Decimal(row["price"]), "brand": row.get("brand", "").strip(), "model": row.get("model", "").strip(), "gender": row.get("gender", "unisex").strip() or "unisex", "description": row.get("description", "").strip(), "active": True})
                    ProductVariant.objects.update_or_create(sku=row["variant_sku"].strip(), defaults={"product": product, "size": row["size"].strip(), "color": row["color"].strip(), "stock": int(row["stock"]), "active": True})
                    count += 1
        except FileNotFoundError: raise CommandError("No se encontró el archivo CSV.")
        self.stdout.write(self.style.SUCCESS(f"Se importaron {count} filas."))
