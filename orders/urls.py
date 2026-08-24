from django.urls import path
from . import views
app_name = "orders"
urlpatterns = [path("finalizar/", views.checkout, name="checkout"), path("confirmado/<str:number>/", views.success, name="success")]
