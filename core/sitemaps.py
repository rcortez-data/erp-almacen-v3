from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from catalog.models import Product

class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8
    def items(self): return Product.objects.available()
    def lastmod(self, obj): return obj.updated_at

class StaticSitemap(Sitemap):
    def items(self): return ["core:home", "catalog:list"]
    def location(self, item): return reverse(item)
