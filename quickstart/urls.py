from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"marcas", views.MarcaViewSet, basename="marca")
router.register(r"categorias", views.CategoriaViewSet, basename="categoria")
router.register(r"tenis", views.TenisViewSet, basename="tenis")
router.register(r"inventario", views.InventarioViewSet, basename="inventario")
router.register(r"movimientos", views.MovimientoViewSet, basename="movimiento")

urlpatterns = [
    path("", include(router.urls)),
    path("api-token-auth/", views.CustomAuthToken.as_view(), name="api_token_auth"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("me/", views.me, name="me"),
    path("logout/", views.logout, name="logout"),
    path("reset-token/", views.reset_token, name="reset_token"),
]
