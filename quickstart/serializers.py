import os
import re
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import Categoria, Inventario, Marca, MovimientoInventario, Tenis
from .services import registrar_movimiento

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}


def validar_imagen(imagen):
    if imagen is None:
        return imagen
    ext = os.path.splitext(imagen.name)[1].lower()
    if ext not in EXTENSIONES_IMAGEN:
        raise serializers.ValidationError(
            f"Formato no permitido ({ext}). Usa: {', '.join(sorted(EXTENSIONES_IMAGEN))}."
        )
    max_mb = getattr(settings, "MAX_IMAGEN_MB", 2)
    if imagen.size > max_mb * 1024 * 1024:
        raise serializers.ValidationError(f"La imagen no puede pesar más de {max_mb} MB.")
    return imagen


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nombre", "descripcion"]

    def validate_nombre(self, value):
        qs = Categoria.objects.filter(nombre__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe una categoría con ese nombre.")
        return value


class InventarioTallaSerializer(serializers.ModelSerializer):
    bajo_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Inventario
        fields = ["id", "talla", "cantidad", "stock_minimo", "bajo_stock"]

    def validate_talla(self, value):
        if (value * 2) % 1 != 0:
            raise serializers.ValidationError("La talla debe ser entera o media (ej. 26 o 26.5).")
        return value


class InventarioSerializer(InventarioTallaSerializer):
    tenis_nombre = serializers.CharField(source="tenis.__str__", read_only=True)
    sku = serializers.CharField(source="tenis.sku", read_only=True)
    cantidad_inicial = serializers.IntegerField(write_only=True, required=False, min_value=0,
                                                default=0)

    class Meta(InventarioTallaSerializer.Meta):
        fields = ["id", "tenis", "sku", "tenis_nombre", "talla", "cantidad", "cantidad_inicial",
                  "stock_minimo", "bajo_stock"]
        read_only_fields = ["cantidad"]
        validators = []

    def validate(self, attrs):
        tenis = attrs.get("tenis", getattr(self.instance, "tenis", None))
        talla = attrs.get("talla", getattr(self.instance, "talla", None))
        qs = Inventario.objects.filter(tenis=tenis, talla=talla)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"talla": f"Ese modelo ya tiene registrada la talla {talla}."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        cantidad_inicial = validated_data.pop("cantidad_inicial", 0)
        inventario = Inventario.objects.create(cantidad=0, **validated_data)
        if cantidad_inicial:
            registrar_movimiento(inventario, MovimientoInventario.Tipo.ENTRADA, cantidad_inicial,
                                 usuario=self.context["request"].user, motivo="Stock inicial")
            inventario.refresh_from_db()
        return inventario

    def update(self, instance, validated_data):
        validated_data.pop("cantidad_inicial", None)
        return super().update(instance, validated_data)


class MovimientoSerializer(serializers.ModelSerializer):
    usuario = serializers.CharField(source="usuario.username", read_only=True, default=None)
    tenis = serializers.CharField(source="inventario.tenis.__str__", read_only=True)
    talla = serializers.DecimalField(source="inventario.talla", max_digits=3, decimal_places=1,
                                     read_only=True)

    class Meta:
        model = MovimientoInventario
        fields = ["id", "inventario", "tenis", "talla", "tipo", "cantidad", "stock_anterior",
                  "stock_resultante", "motivo", "usuario", "fecha"]
        read_only_fields = ["stock_anterior", "stock_resultante", "fecha"]

    def validate(self, attrs):
        if attrs["tipo"] != MovimientoInventario.Tipo.AJUSTE and attrs["cantidad"] < 1:
            raise serializers.ValidationError(
                {"cantidad": "Las entradas y salidas deben ser de al menos 1 par."}
            )
        if attrs["tipo"] == MovimientoInventario.Tipo.AJUSTE and not attrs.get("motivo"):
            raise serializers.ValidationError(
                {"motivo": "Los ajustes deben indicar el motivo (ej. conteo físico)."}
            )
        inv = attrs["inventario"]
        if attrs["tipo"] == MovimientoInventario.Tipo.SALIDA and attrs["cantidad"] > inv.cantidad:
            raise serializers.ValidationError(
                {"cantidad": f"Stock insuficiente: hay {inv.cantidad} pares en talla {inv.talla} "
                             f"y se intentan sacar {attrs['cantidad']}."}
            )
        return attrs

    def create(self, validated_data):
        return registrar_movimiento(usuario=self.context["request"].user, **validated_data)


class MarcaResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marca
        fields = ["id", "nombre", "logo"]


class MarcaSerializer(serializers.ModelSerializer):
    total_modelos = serializers.IntegerField(read_only=True)

    class Meta:
        model = Marca
        fields = ["id", "nombre", "pais_origen", "logo", "total_modelos"]

    def validate_nombre(self, value):
        qs = Marca.objects.filter(nombre__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe una marca con ese nombre.")
        return value

    def validate_logo(self, value):
        return validar_imagen(value)


class TenisResumenSerializer(serializers.ModelSerializer):
    stock_total = serializers.SerializerMethodField()

    class Meta:
        model = Tenis
        fields = ["id", "sku", "nombre", "color", "precio", "precio_oferta", "imagen", "estado",
                  "stock_total"]

    def get_stock_total(self, obj):
        return sum(i.cantidad for i in obj.inventario.all())


class MarcaDetalleSerializer(MarcaSerializer):
    tenis = TenisResumenSerializer(many=True, read_only=True)

    class Meta(MarcaSerializer.Meta):
        fields = MarcaSerializer.Meta.fields + ["tenis"]


class TenisSerializer(serializers.ModelSerializer):
    marca = MarcaResumenSerializer(read_only=True)
    categorias = CategoriaSerializer(many=True, read_only=True)
    marca_id = serializers.PrimaryKeyRelatedField(queryset=Marca.objects.all(), source="marca",
                                                  write_only=True)
    categoria_ids = serializers.PrimaryKeyRelatedField(queryset=Categoria.objects.all(),
                                                       source="categorias", many=True,
                                                       write_only=True, required=False)
    inventario = InventarioTallaSerializer(many=True, required=False)

    genero_display = serializers.CharField(source="get_genero_display", read_only=True)
    stock_total = serializers.SerializerMethodField()
    disponible = serializers.SerializerMethodField()
    es_favorito = serializers.SerializerMethodField()

    class Meta:
        model = Tenis
        fields = ["id", "sku", "nombre", "descripcion", "marca", "marca_id", "categorias",
                  "categoria_ids", "color", "genero", "genero_display", "precio",
                  "precio_oferta", "imagen", "estado", "stock_total", "disponible",
                  "es_favorito", "inventario", "creado", "actualizado"]
        read_only_fields = ["estado", "creado", "actualizado"]


    def get_stock_total(self, obj):
        return sum(i.cantidad for i in obj.inventario.all())

    def get_disponible(self, obj):
        return obj.estado == Tenis.Estado.ACTIVO and self.get_stock_total(obj) > 0

    def get_es_favorito(self, obj):
        # En listados viene anotado desde TenisViewSet (una sola consulta para toda la página)
        if hasattr(obj, "favorito_anotado"):
            return obj.favorito_anotado
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.favoritos.filter(pk=request.user.pk).exists()


    def validate_sku(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{4,20}", value):
            raise serializers.ValidationError(
                "El SKU debe tener de 4 a 20 caracteres: letras, números o guiones."
            )
        return value

    def validate_nombre(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("El nombre debe tener al menos 3 caracteres.")
        return value.strip()

    def validate_precio(self, value):
        if value > Decimal("50000"):
            raise serializers.ValidationError("El precio no puede ser mayor a $50,000.")
        return value

    def validate_imagen(self, value):
        return validar_imagen(value)

    def validate_inventario(self, value):
        tallas = [item["talla"] for item in value]
        repetidas = {str(t) for t in tallas if tallas.count(t) > 1}
        if repetidas:
            raise serializers.ValidationError(
                f"Tallas repetidas: {', '.join(sorted(repetidas))}."
            )
        return value


    def validate(self, attrs):
        precio = attrs.get("precio", getattr(self.instance, "precio", None))
        oferta = attrs.get("precio_oferta", getattr(self.instance, "precio_oferta", None))
        if oferta is not None and precio is not None and oferta >= precio:
            raise serializers.ValidationError(
                {"precio_oferta": "El precio de oferta debe ser menor al precio normal."}
            )
        if self.instance and "inventario" in attrs:
            raise serializers.ValidationError(
                {"inventario": "El inventario no se edita aquí; usa /api/inventario/ "
                               "o /api/movimientos/."}
            )
        return attrs


    @transaction.atomic
    def create(self, validated_data):
        inventario_data = validated_data.pop("inventario", [])
        categorias = validated_data.pop("categorias", [])
        tenis = Tenis.objects.create(**validated_data)
        tenis.categorias.set(categorias)

        usuario = self.context["request"].user
        for item in inventario_data:
            cantidad = item.pop("cantidad", 0)
            inv = Inventario.objects.create(tenis=tenis, cantidad=0, **item)
            if cantidad:
                registrar_movimiento(inv, MovimientoInventario.Tipo.ENTRADA, cantidad,
                                     usuario=usuario, motivo="Stock inicial")
        return tenis


class TenisVendidoSerializer(TenisSerializer):
    pares_vendidos = serializers.IntegerField(read_only=True)

    class Meta(TenisSerializer.Meta):
        fields = TenisSerializer.Meta.fields + ["pares_vendidos"]


class EstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Tenis.Estado.choices)


class ImagenSerializer(serializers.Serializer):
    imagen = serializers.ImageField()

    def validate_imagen(self, value):
        return validar_imagen(value)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True,
                                     validators=[validate_password])
    email = serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Este email ya está registrado.")
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Este username ya está registrado.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    total_favoritos = serializers.IntegerField(source="tenis_favoritos.count", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff", "total_favoritos"]
        read_only_fields = ["is_staff"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Ya existe un usuario con este email.")
        return value

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Ya existe un usuario con este username.")
        return value
