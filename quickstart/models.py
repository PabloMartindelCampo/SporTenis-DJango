from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Sum


class Marca(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    pais_origen = models.CharField(max_length=60, blank=True)
    logo = models.ImageField(upload_to="marcas/", blank=True, null=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "categorías"

    def __str__(self):
        return self.nombre


class Tenis(models.Model):
    class Genero(models.TextChoices):
        HOMBRE = "H", "Hombre"
        MUJER = "M", "Mujer"
        UNISEX = "U", "Unisex"
        NINO = "N", "Niño"

    class Estado(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        DESCONTINUADO = "DESCONTINUADO", "Descontinuado"

    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name="tenis")
    categorias = models.ManyToManyField(Categoria, related_name="tenis", blank=True)

    sku = models.CharField("SKU", max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    color = models.CharField(max_length=40)
    genero = models.CharField(max_length=1, choices=Genero.choices, default=Genero.UNISEX)
    precio = models.DecimalField(max_digits=8, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))])
    precio_oferta = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    imagen = models.ImageField(upload_to="tenis/", blank=True, null=True)
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.ACTIVO)

    favoritos = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="tenis_favoritos",
                                       blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado"]
        verbose_name_plural = "tenis"

    def __str__(self):
        return f"{self.marca} {self.nombre} ({self.color})"

    @property
    def stock_total(self):
        return self.inventario.aggregate(total=Sum("cantidad"))["total"] or 0

    @property
    def disponible(self):
        return self.estado == self.Estado.ACTIVO and self.stock_total > 0


class Inventario(models.Model):
    tenis = models.ForeignKey(Tenis, on_delete=models.CASCADE, related_name="inventario")
    talla = models.DecimalField(max_digits=3, decimal_places=1,
                                validators=[MinValueValidator(Decimal("12")),
                                            MaxValueValidator(Decimal("35"))])
    cantidad = models.PositiveIntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=2)

    class Meta:
        ordering = ["tenis", "talla"]
        verbose_name_plural = "inventario"
        constraints = [
            models.UniqueConstraint(fields=["tenis", "talla"], name="unique_tenis_talla"),
        ]

    def __str__(self):
        return f"{self.tenis.sku} talla {self.talla}: {self.cantidad}"

    @property
    def bajo_stock(self):
        return self.cantidad <= self.stock_minimo


class MovimientoInventario(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SALIDA = "SALIDA", "Salida"
        AJUSTE = "AJUSTE", "Ajuste"

    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE, related_name="movimientos")
    tipo = models.CharField(max_length=7, choices=Tipo.choices)
    cantidad = models.PositiveIntegerField()
    stock_anterior = models.PositiveIntegerField()
    stock_resultante = models.PositiveIntegerField()
    motivo = models.CharField(max_length=200, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, related_name="movimientos")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name_plural = "movimientos de inventario"

    def __str__(self):
        return f"{self.get_tipo_display()} {self.cantidad} - {self.inventario}"
