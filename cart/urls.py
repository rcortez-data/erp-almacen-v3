from django.urls import path
from . import views
app_name = "cart"
urlpatterns = [path("", views.detail, name="detail"), path("agregar/<int:variant_id>/", views.add, name="add"), path("actualizar/<int:variant_id>/", views.update, name="update"), path("eliminar/<int:variant_id>/", views.remove, name="remove")]
