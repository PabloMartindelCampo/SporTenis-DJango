from django.contrib import admin, messages
from django.db.models import Count, IntegerField, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils.html import format_html

from .models import Categoria, Inventario, Marca, MovimientoInventario, Tenis
from .services import registrar_movimiento

admin.site.site_header = "Tienda de Tenis - Administración"
admin.site.site_title = "Tienda de Tenis"
admin.site.index_title = "Catálogo e inventario"


def miniatura(imagen, alto=50):
    if not imagen:
        return "—"
    return format_html('<img src="{}" style="height:{}px;border-radius:4px;" />',
                       imagen.url, alto)


class TenisInline(admin.TabularInline):
    model = Tenis
    fields = ["sku", "nombre", "color", "precio", "estado"]
    extra = 0
    show_change_link = True


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "pais_origen", "total_modelos", "vista_logo"]
    search_fields = ["nombre", "pais_origen"]
    inlines = [TenisInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_total=Count("tenis"))

    @admin.display(description="Modelos", ordering="_total")
    def total_modelos(self, obj):
        return obj._total

    @admin.display(description="Logo")
    def vista_logo(self, obj):
        return miniatura(obj.logo, 30)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "descripcion"]
    search_fields = ["nombre"]


class InventarioInline(admin.TabularInline):
    model = Inventario
    fields = ["talla", "cantidad", "stock_minimo"]
    extra = 1


@admin.register(Tenis)
class TenisAdmin(admin.ModelAdmin):
    list_display = ["vista_imagen", "sku", "nombre", "marca", "color", "genero", "precio",
                    "precio_oferta", "stock", "estado"]
    list_display_links = ["vista_imagen", "sku", "nombre"]
    list_filter = ["estado", "genero", "marca", "categorias"]
    list_editable = ["precio", "precio_oferta"]
    search_fields = ["sku", "nombre", "color", "marca__nombre"]
    filter_horizontal = ["categorias"]
    readonly_fields = ["vista_imagen_grande", "creado", "actualizado"]
    inlines = [InventarioInline]
    actions = ["descontinuar", "activar"]
    fieldsets = [
        ("Producto", {"fields": ["sku", "nombre", "marca", "categorias", "descripcion"]}),
        ("Detalles", {"fields": ["color", "genero", "estado"]}),
        ("Precio", {"fields": ["precio", "precio_oferta"]}),
        ("Imagen", {"fields": ["imagen", "vista_imagen_grande"]}),
        ("Fechas", {"fields": ["creado", "actualizado"], "classes": ["collapse"]}),
    ]

    def get_queryset(self, request):
        stock = (Inventario.objects.filter(tenis=OuterRef("pk")).values("tenis")
                 .annotate(total=Sum("cantidad")).values("total"))
        return (super().get_queryset(request).select_related("marca")
                .annotate(_stock=Coalesce(Subquery(stock, output_field=IntegerField()), 0)))

    @admin.display(description="Stock", ordering="_stock")
    def stock(self, obj):
        return obj._stock

    @admin.display(description="Imagen")
    def vista_imagen(self, obj):
        return miniatura(obj.imagen)

    @admin.display(description="Vista previa")
    def vista_imagen_grande(self, obj):
        return miniatura(obj.imagen, 200)

    @admin.action(description="Marcar como descontinuados")
    def descontinuar(self, request, queryset):
        n = queryset.update(estado=Tenis.Estado.DESCONTINUADO)
        self.message_user(request, f"{n} modelo(s) descontinuado(s).", messages.SUCCESS)

    @admin.action(description="Marcar como activos")
    def activar(self, request, queryset):
        n = queryset.update(estado=Tenis.Estado.ACTIVO)
        self.message_user(request, f"{n} modelo(s) activado(s).", messages.SUCCESS)

    def save_formset(self, request, form, formset, change):
        if formset.model is not Inventario:
            return super().save_formset(request, form, formset, change)

        instancias = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for inv in instancias:
            nueva = inv.cantidad
            if inv.pk is None:
                inv.cantidad = 0
                inv.save()
                if nueva:
                    registrar_movimiento(inv, MovimientoInventario.Tipo.ENTRADA, nueva,
                                         usuario=request.user, motivo="Alta desde el admin")
            else:
                anterior = Inventario.objects.get(pk=inv.pk).cantidad
                inv.cantidad = anterior
                inv.save()
                if nueva != anterior:
                    registrar_movimiento(inv, MovimientoInventario.Tipo.AJUSTE, nueva,
                                         usuario=request.user, motivo="Ajuste desde el admin")
        formset.save_m2m()


@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = ["tenis", "talla", "cantidad", "stock_minimo", "alerta"]
    list_filter = ["tenis__marca", "talla"]
    search_fields = ["tenis__nombre", "tenis__sku"]
    readonly_fields = ["cantidad"]

    @admin.display(description="Alerta", boolean=True)
    def alerta(self, obj):
        return not obj.bajo_stock


@admin.register(MovimientoInventario)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ["fecha", "tipo", "inventario", "cantidad", "stock_anterior",
                    "stock_resultante", "usuario", "motivo"]
    list_filter = ["tipo", "fecha", "inventario__tenis__marca"]
    search_fields = ["motivo", "inventario__tenis__nombre", "inventario__tenis__sku"]
    date_hierarchy = "fecha"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
