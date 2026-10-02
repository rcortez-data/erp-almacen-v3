from django.urls import path
from . import views
app_name = "core"
urlpatterns = [
    path("", views.home, name="home"), path("robots.txt", views.robots, name="robots"),
    path("informacion/<str:page>/", views.legal, name="legal"),
]
