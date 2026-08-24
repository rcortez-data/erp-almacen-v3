from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from core.sitemaps import ProductSitemap, StaticSitemap

admin.site.site_header = "Administración Web Price Shoes"
admin.site.site_title = "Web Price Shoes"
admin.site.index_title = "Catálogo y pedidos"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("catalogo/", include("catalog.urls")),
    path("carrito/", include("cart.urls")),
    path("pedidos/", include("orders.urls")),
    path("cuenta/", include("accounts.urls")),
    path("cuenta/", include("django.contrib.auth.urls")),
    path("sitemap.xml", __import__("django.contrib.sitemaps.views", fromlist=["sitemap"]).sitemap, {"sitemaps": {"static": StaticSitemap, "products": ProductSitemap}}, name="sitemap"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
