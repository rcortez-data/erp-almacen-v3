from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from .forms import RegistrationForm
def register(request):
    form=RegistrationForm(request.POST or None)
    if request.method=="POST" and form.is_valid(): user=form.save(); login(request,user); return redirect("accounts:profile")
    return render(request,"accounts/register.html",{"form":form})
@login_required
def profile(request): return render(request,"accounts/profile.html",{"orders":request.user.orders.prefetch_related("items")})
