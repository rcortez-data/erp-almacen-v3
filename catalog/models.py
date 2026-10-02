from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.urls import reverse

class Category(models.Model):
    name = models.CharField("nombre", max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey("self", verbose_name="categoría superior", blank=True, null=True, on_delete=models.SET_NULL, related_name="children")
    active = models.BooleanField("activa", default=True)
    class Meta:
        verbose_name = "categoría"; verbose_name_plural = "categorías"; ordering = ["name"]
    def __str__(self): return self.name

class ProductQuerySet(models.QuerySet):
    def available(self): return self.filter(active=True).prefetch_related("images", "variants")

class Product(models.Model):
    class Gender(models.TextChoices):
        WOMEN = "mujer", "Mujer"; MEN = "hombre", "Hombre"; KIDS = "infantil", "Infantil"; UNISEX = "unisex", "Unisex"
    category = models.ForeignKey(Category, verbose_name="categoría", on_delete=models.PROTECT, related_name="products")
    name = models.CharField("nombre", max_length=180)
    slug = models.SlugField(unique=True, max_length=200)
    sku = models.CharField("SKU", max_length=60, unique=True)
    brand = models.CharField("marca", max_length=100, blank=True)
    model = models.CharField("modelo", max_length=100, blank=True)
    gender = models.CharField("género", max_length=20, choices=Gender.choices, default=Gender.UNISEX)
    description = models.TextField("descripción", blank=True)
    price = models.DecimalField("precio", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    sale_price = models.DecimalField("precio de oferta", max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    active = models.BooleanField("activo", default=True)
    featured = models.BooleanField("destacado", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = ProductQuerySet.as_manager()
    class Meta:
        verbose_name = "producto"; verbose_name_plural = "productos"; ordering = ["-created_at"]
    def __str__(self): return f"{self.name} ({self.sku})"
    @property
    def current_price(self): return self.sale_price if self.sale_price is not None and self.sale_price < self.price else self.price
    @property
    def in_stock(self): return any(v.stock > 0 and v.active for v in self.variants.all())
    @property
    def primary_image(self): return next((i for i in self.images.all() if i.is_primary), next(iter(self.images.all()), None))
    def get_absolute_url(self): return reverse("catalog:detail", kwargs={"slug": self.slug})
    def clean(self):
        if self.sale_price is not None and self.sale_price >= self.price: raise ValidationError({"sale_price": "El precio de oferta debe ser menor al precio normal."})

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, verbose_name="producto", on_delete=models.CASCADE, related_name="variants")
    size = models.CharField("talla", max_length=20)
    color = models.CharField("color", max_length=50)
    sku = models.CharField("SKU de variante", max_length=80, unique=True)
    stock = models.PositiveIntegerField("existencias", default=0)
    active = models.BooleanField("activa", default=True)
    class Meta:
        verbose_name = "variante"; verbose_name_plural = "variantes"; constraints = [models.UniqueConstraint(fields=["product", "size", "color"], name="unique_product_size_color")]; ordering = ["size", "color"]
    def __str__(self): return f"{self.product.name} · {self.size} · {self.color}"

def validate_image_size(image):
    if image.size > 5 * 1024 * 1024: raise ValidationError("La imagen no debe superar 5 MB.")

class ProductImage(models.Model):
    product = models.ForeignKey(Product, verbose_name="producto", on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("imagen", upload_to="products/%Y/%m/", validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validate_image_size])
    alt_text = models.CharField("texto alternativo", max_length=180)
    is_primary = models.BooleanField("principal", default=False)
    position = models.PositiveSmallIntegerField("posición", default=0)
    class Meta:
        verbose_name = "imagen"; verbose_name_plural = "imágenes"; ordering = ["position", "id"]
    def __str__(self): return self.alt_text
