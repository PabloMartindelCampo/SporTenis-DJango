import django_filters
from django.db.models import Exists, OuterRef

from .models import Categoria, Inventario, Marca, Tenis


class TenisFilter(django_filters.FilterSet):
    marca = django_filters.ModelMultipleChoiceFilter(queryset=Marca.objects.all())
    categoria = django_filters.ModelMultipleChoiceFilter(field_name="categorias",
                                                         queryset=Categoria.objects.all())
    precio_min = django_filters.NumberFilter(field_name="precio", lookup_expr="gte")
    precio_max = django_filters.NumberFilter(field_name="precio", lookup_expr="lte")
    talla = django_filters.NumberFilter(method="filtrar_talla")
    disponible = django_filters.BooleanFilter(method="filtrar_disponible")
    en_oferta = django_filters.BooleanFilter(field_name="precio_oferta", lookup_expr="isnull",
                                             exclude=True)

    class Meta:
        model = Tenis
        fields = ["marca", "categoria", "genero", "estado", "color"]

    def filtrar_talla(self, queryset, name, value):
        hay_stock = Inventario.objects.filter(tenis=OuterRef("pk"), talla=value, cantidad__gt=0)
        return queryset.filter(Exists(hay_stock))

    def filtrar_disponible(self, queryset, name, value):
        hay_stock = Inventario.objects.filter(tenis=OuterRef("pk"), cantidad__gt=0)
        disponibles = queryset.filter(Exists(hay_stock), estado=Tenis.Estado.ACTIVO)
        if value:
            return disponibles
        return queryset.exclude(pk__in=disponibles.values("pk"))


class InventarioFilter(django_filters.FilterSet):
    marca = django_filters.NumberFilter(field_name="tenis__marca")
    sin_stock = django_filters.BooleanFilter(method="filtrar_sin_stock")

    class Meta:
        model = Inventario
        fields = ["tenis", "talla"]

    def filtrar_sin_stock(self, queryset, name, value):
        return queryset.filter(cantidad=0) if value else queryset.filter(cantidad__gt=0)
