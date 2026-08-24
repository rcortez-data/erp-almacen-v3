from .cart import Cart
def cart_summary(request): return {"cart": Cart(request)}
