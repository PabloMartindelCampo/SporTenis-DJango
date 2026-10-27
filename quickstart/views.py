from django.contrib.auth.models import User
from django.db.models import (BooleanField, Count, Exists, F, IntegerField, OuterRef, Subquery,
                              Sum, Value)
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .filters import InventarioFilter, TenisFilter
from .models import Categoria, Inventario, Marca, MovimientoInventario, Tenis
from .permissions import IsAdminOrReadOnly
from .serializers import (CategoriaSerializer, EstadoSerializer, ImagenSerializer,
                          InventarioSerializer, InventarioTallaSerializer, MarcaDetalleSerializer,
                          MarcaSerializer, MovimientoSerializer, RegisterSerializer,
                          TenisSerializer, TenisVendidoSerializer, UserSerializer)


class MarcaViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["nombre", "pais_origen"]
    ordering_fields = ["nombre", "total_modelos"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = Marca.objects.annotate(total_modelos=Count("tenis")).order_by("nombre")
        if self.action == "retrieve":
            qs = qs.prefetch_related("tenis__inventario")
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return MarcaDetalleSerializer
        return MarcaSerializer

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "No se puede borrar una marca que tiene tenis registrados."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ["nombre"]


class TenisViewSet(viewsets.ModelViewSet):
    serializer_class = TenisSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = TenisFilter
    search_fields = ["nombre", "sku", "color", "marca__nombre", "descripcion"]
    ordering_fields = ["precio", "nombre", "creado", "stock"]
    ordering = ["-creado"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        stock = (Inventario.objects.filter(tenis=OuterRef("pk"))
                 .values("tenis").annotate(total=Sum("cantidad")).values("total"))
        # es_favorito se calcula en la misma consulta con Exists, en vez de una consulta por tenis
        user = self.request.user
        if user.is_authenticated:
            favorito = Exists(Tenis.favoritos.through.objects.filter(tenis=OuterRef("pk"),
                                                                     user=user))
        else:
            favorito = Value(False, output_field=BooleanField())
        return (Tenis.objects
                .select_related("marca")
                .prefetch_related("categorias", "inventario")
                .annotate(stock=Coalesce(Subquery(stock, output_field=IntegerField()), 0),
                          favorito_anotado=favorito))

    def destroy(self, request, *args, **kwargs):
        tenis = self.get_object()
        vendido = MovimientoInventario.objects.filter(
            inventario__tenis=tenis, tipo=MovimientoInventario.Tipo.SALIDA).exists()
        if vendido:
            return Response(
                {"detail": "Este modelo ya tiene ventas registradas; descontinúalo con "
                           "PATCH /api/tenis/<id>/estado/ en lugar de borrarlo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


    @action(detail=True, methods=["post", "delete"],
            permission_classes=[permissions.IsAuthenticated])
    def favorito(self, request, pk=None):
        tenis = self.get_object()
        if request.method == "POST":
            if tenis.favoritos.filter(pk=request.user.pk).exists():
                return Response({"detail": "Ya estaba en tus favoritos."},
                                status=status.HTTP_200_OK)
            tenis.favoritos.add(request.user)
            return Response({"detail": f"{tenis} agregado a favoritos."},
                            status=status.HTTP_201_CREATED)
        tenis.favoritos.remove(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def favoritos(self, request):
        qs = self.filter_queryset(self.get_queryset().filter(favoritos=request.user))
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["patch"], permission_classes=[permissions.IsAdminUser])
    def estado(self, request, pk=None):
        tenis = self.get_object()
        serializer = EstadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenis.estado = serializer.validated_data["estado"]
        tenis.save(update_fields=["estado", "actualizado"])
        return Response({"id": tenis.id, "estado": tenis.estado,
                         "detail": f"Estado cambiado a {tenis.get_estado_display()}."})

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser],
            parser_classes=[MultiPartParser, FormParser])
    def imagen(self, request, pk=None):
        tenis = self.get_object()
        serializer = ImagenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if tenis.imagen:
            tenis.imagen.delete(save=False)
        tenis.imagen = serializer.validated_data["imagen"]
        tenis.save(update_fields=["imagen", "actualizado"])
        return Response({"imagen": request.build_absolute_uri(tenis.imagen.url)},
                        status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="mas-vendidos",
            permission_classes=[permissions.AllowAny])
    def mas_vendidos(self, request):
        vendidos = (MovimientoInventario.objects
                    .filter(inventario__tenis=OuterRef("pk"), tipo=MovimientoInventario.Tipo.SALIDA)
                    .values("inventario__tenis").annotate(total=Sum("cantidad")).values("total"))
        # Se ordena después de filter_queryset para que no lo pise el ordering por defecto
        qs = (self.filter_queryset(self.get_queryset())
              .annotate(pares_vendidos=Coalesce(Subquery(vendidos, output_field=IntegerField()), 0))
              .filter(pares_vendidos__gt=0)
              .order_by("-pares_vendidos", "nombre"))
        page = self.paginate_queryset(qs)
        serializer = TenisVendidoSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"], permission_classes=[permissions.AllowAny])
    def disponibilidad(self, request, pk=None):
        tenis = self.get_object()
        tallas = tenis.inventario.filter(cantidad__gt=0)
        return Response({
            "tenis": str(tenis),
            "disponible": tenis.estado == Tenis.Estado.ACTIVO and tallas.exists(),
            "tallas": InventarioTallaSerializer(tallas, many=True).data,
        })


class InventarioViewSet(viewsets.ModelViewSet):
    queryset = Inventario.objects.select_related("tenis", "tenis__marca")
    serializer_class = InventarioSerializer
    permission_classes = [permissions.IsAdminUser]
    filterset_class = InventarioFilter
    search_fields = ["tenis__nombre", "tenis__sku"]
    ordering_fields = ["cantidad", "talla", "tenis__nombre"]

    @action(detail=False, methods=["get"], url_path="bajo-stock")
    def bajo_stock(self, request):
        qs = self.filter_queryset(self.get_queryset().filter(cantidad__lte=F("stock_minimo")))
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=False, methods=["get"])
    def resumen(self, request):
        datos = Inventario.objects.aggregate(pares=Sum("cantidad"), registros=Count("id"))
        return Response({
            "modelos": Tenis.objects.count(),
            "tallas_registradas": datos["registros"],
            "pares_en_inventario": datos["pares"] or 0,
            "tallas_bajo_stock": Inventario.objects.filter(
                cantidad__lte=F("stock_minimo")).count(),
            "tallas_agotadas": Inventario.objects.filter(cantidad=0).count(),
        })


class MovimientoViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                        mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = MovimientoInventario.objects.select_related(
        "inventario__tenis__marca", "usuario")
    serializer_class = MovimientoSerializer
    permission_classes = [permissions.IsAdminUser]
    filterset_fields = ["tipo", "inventario", "inventario__tenis", "usuario"]
    search_fields = ["motivo", "inventario__tenis__nombre", "inventario__tenis__sku"]
    ordering_fields = ["fecha", "cantidad"]


class CustomAuthToken(ObtainAuthToken):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "token": token.key,
            "user_id": user.pk,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
        })


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "registro"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "message": f"Usuario {user.username} registrado correctamente. "
                       "Inicia sesión en /api/api-token-auth/ para obtener tu token.",
        }, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def me(request):
    if request.method == "GET":
        return Response(UserSerializer(request.user).data)
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def reset_token(request):
    Token.objects.filter(user=request.user).delete()
    token = Token.objects.create(user=request.user)
    return Response({"token": token.key})
