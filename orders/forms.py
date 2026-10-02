from django import forms
from .models import Order

class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order; fields = ("name", "phone", "email", "address", "delivery_method", "notes")
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "notes": forms.Textarea(attrs={"rows": 2})}
    def clean_phone(self):
        phone = "".join(c for c in self.cleaned_data["phone"] if c.isdigit() or c == "+")
        if len("".join(filter(str.isdigit, phone))) < 10: raise forms.ValidationError("Captura un teléfono de al menos 10 dígitos.")
        return phone
