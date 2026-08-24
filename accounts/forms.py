from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
class RegistrationForm(UserCreationForm):
    email=forms.EmailField(required=True, label="Correo electrónico")
    first_name=forms.CharField(max_length=150, label="Nombre")
    last_name=forms.CharField(max_length=150, label="Apellidos")
    class Meta: model=User; fields=("username","first_name","last_name","email","password1","password2")
    def clean_email(self):
        email=self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists(): raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email
