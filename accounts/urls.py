from django.urls import path
from . import views
app_name="accounts"
urlpatterns=[path("registro/",views.register,name="register"),path("perfil/",views.profile,name="profile")]
