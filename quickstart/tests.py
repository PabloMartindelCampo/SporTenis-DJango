import io
import os
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Categoria, Inventario, Marca, MovimientoInventario, Tenis
from .services import registrar_movimiento

MEDIA_TMP = tempfile.mkdtemp()


def png(nombre="foto.png", tam=(10, 10)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", tam, "red").save(buf, format="PNG")
    return SimpleUploadedFile(nombre, buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA_TMP,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BaseTest(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TMP, ignore_errors=True)

    def setUp(self):
        # El throttling guarda sus contadores en la caché; se limpia para aislar cada prueba
        cache.clear()
        self.admin = User.objects.create_user("admin", "a@a.com", "Admin12345", is_staff=True)
        self.cliente = User.objects.create_user("cliente", "c@c.com", "Cliente12345")
        self.nike = Marca.objects.create(nombre="Nike")
        self.running = Categoria.objects.create(nombre="Running")
        self.casual = Categoria.objects.create(nombre="Casual")
        self.tenis = Tenis.objects.create(marca=self.nike, sku="NK-001", nombre="Pegasus",
                                          color="Negro", precio=Decimal("2500"))
        self.tenis.categorias.add(self.running)
        self.inv26 = Inventario.objects.create(tenis=self.tenis, talla=Decimal("26"), cantidad=5)
        self.inv27 = Inventario.objects.create(tenis=self.tenis, talla=Decimal("27"), cantidad=0)

    def como(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")


class AutenticacionTests(BaseTest):
    def test_registro_login_me_logout(self):
        r = self.client.post("/api/register/", {"username": "nuevo", "email": "n@n.com",
                                                "password": "Segura12345"})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertIn("message", r.data)

        r = self.client.post("/api/api-token-auth/", {"username": "nuevo",
                                                      "password": "Segura12345"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["email"], "n@n.com")
        self.assertFalse(r.data["is_staff"])
        token = r.data["token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(self.client.get("/api/me/").data["username"], "nuevo")
        self.assertEqual(self.client.post("/api/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/me/").status_code, 401)

    def test_registro_rechaza_password_debil_y_email_repetido(self):
        r = self.client.post("/api/register/", {"username": "x", "email": "C@C.com",
                                                "password": "123"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.data)
        self.assertIn("password", r.data)

    def test_registro_username_repetido_sin_importar_mayusculas(self):
        r = self.client.post("/api/register/", {"username": "CLIENTE", "email": "otro@c.com",
                                                "password": "Segura12345"})
        self.assertIn("username", r.data)

    def test_me_patch_no_permite_email_de_otro(self):
        self.como(self.cliente)
        r = self.client.patch("/api/me/", {"email": "A@A.com"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.data)
        r = self.client.patch("/api/me/", {"email": "nuevo@c.com"}, format="json")
        self.assertEqual(r.data["email"], "nuevo@c.com")

    def test_reset_token(self):
        self.como(self.cliente)
        viejo = self.cliente.auth_token.key
        r = self.client.post("/api/reset-token/")
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.data["token"], viejo)
        self.assertEqual(self.client.get("/api/me/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {r.data['token']}")
        self.assertEqual(self.client.get("/api/me/").status_code, 200)

    def test_catalogo_publico_pero_inventario_privado(self):
        self.assertEqual(self.client.get("/api/tenis/").status_code, 200)
        self.assertEqual(self.client.get("/api/marcas/").status_code, 200)
        self.assertEqual(self.client.get("/api/inventario/").status_code, 401)
        self.assertEqual(self.client.get("/api/movimientos/").status_code, 401)
        self.como(self.cliente)
        self.assertEqual(self.client.get("/api/inventario/").status_code, 403)
        self.assertEqual(self.client.get("/api/movimientos/").status_code, 403)

    def test_cliente_no_puede_crear_tenis(self):
        self.como(self.cliente)
        r = self.client.post("/api/tenis/", {"sku": "X-1234", "nombre": "Test", "color": "Rojo",
                                             "precio": "100", "marca_id": self.nike.id},
                             format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.post("/api/marcas/", {"nombre": "Fila"}).status_code, 403)


class ThrottlingTests(BaseTest):
    def test_login_limitado(self):
        for _ in range(10):
            r = self.client.post("/api/api-token-auth/", {"username": "admin", "password": "mala"})
            self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/api-token-auth/", {"username": "admin",
                                                      "password": "Admin12345"})
        self.assertEqual(r.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_registro_limitado(self):
        for i in range(5):
            r = self.client.post("/api/register/", {"username": f"u{i}", "email": f"u{i}@x.com",
                                                    "password": "Segura12345"})
            self.assertEqual(r.status_code, 201)
        r = self.client.post("/api/register/", {"username": "u9", "email": "u9@x.com",
                                                "password": "Segura12345"})
        self.assertEqual(r.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class SerializersAnidadosTests(BaseTest):
    def test_tenis_trae_marca_categorias_e_inventario(self):
        r = self.client.get(f"/api/tenis/{self.tenis.id}/")
        self.assertEqual(r.data["marca"]["nombre"], "Nike")
        self.assertEqual(r.data["categorias"][0]["nombre"], "Running")
        self.assertEqual(len(r.data["inventario"]), 2)
        self.assertEqual(r.data["stock_total"], 5)
        self.assertEqual(r.data["genero_display"], "Unisex")
        self.assertTrue(r.data["disponible"])
        self.assertFalse(r.data["es_favorito"])

    def test_marca_detalle_trae_sus_tenis(self):
        r = self.client.get(f"/api/marcas/{self.nike.id}/")
        self.assertEqual(r.data["tenis"][0]["sku"], "NK-001")
        self.assertEqual(r.data["total_modelos"], 1)

    def test_crear_tenis_con_inventario_anidado(self):
        self.como(self.admin)
        r = self.client.post("/api/tenis/", {
            "sku": "nk-002", "nombre": "Air Max", "color": "Blanco", "precio": "3000",
            "marca_id": self.nike.id, "categoria_ids": [self.running.id, self.casual.id],
            "inventario": [{"talla": "25", "cantidad": 4}, {"talla": "25.5", "cantidad": 2}],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["sku"], "NK-002")
        self.assertEqual(r.data["stock_total"], 6)
        self.assertEqual(len(r.data["categorias"]), 2)
        movs = MovimientoInventario.objects.filter(inventario__tenis__sku="NK-002")
        self.assertEqual(movs.filter(tipo="ENTRADA", motivo="Stock inicial").count(), 2)


class ValidacionesTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.como(self.admin)
        self.base = {"sku": "AD-100", "nombre": "Samba", "color": "Negro", "precio": "2000",
                     "marca_id": self.nike.id}

    def post(self, **cambios):
        return self.client.post("/api/tenis/", {**self.base, **cambios}, format="json")

    def test_oferta_mayor_que_precio(self):
        r = self.post(precio_oferta="2500")
        self.assertIn("precio_oferta", r.data)

    def test_oferta_en_patch_considera_precio_guardado(self):
        url = f"/api/tenis/{self.tenis.id}/"
        self.assertIn("precio_oferta",
                      self.client.patch(url, {"precio_oferta": "3000"}, format="json").data)
        r = self.client.patch(url, {"precio_oferta": "2000"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_sku_invalido(self):
        self.assertIn("sku", self.post(sku="a b").data)
        self.assertIn("sku", self.post(sku="AB").data)

    def test_nombre_corto(self):
        self.assertIn("nombre", self.post(nombre="ab").data)

    def test_precio_excesivo(self):
        self.assertIn("precio", self.post(precio="99999").data)

    def test_tallas_repetidas_y_media_talla(self):
        r = self.post(inventario=[{"talla": "26", "cantidad": 1}, {"talla": "26", "cantidad": 2}])
        self.assertIn("inventario", r.data)
        r = self.post(inventario=[{"talla": "26.3", "cantidad": 1}])
        self.assertIn("inventario", r.data)
        r = self.post(inventario=[{"talla": "26.5", "cantidad": 1}])
        self.assertEqual(r.status_code, 201, r.data)

    def test_editar_inventario_desde_tenis(self):
        r = self.client.patch(f"/api/tenis/{self.tenis.id}/",
                              {"inventario": [{"talla": "28", "cantidad": 1}]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("/api/movimientos/", str(r.data["inventario"]))

    def test_marca_y_categoria_unicas_sin_importar_mayusculas(self):
        self.assertIn("nombre", self.client.post("/api/marcas/", {"nombre": "NIKE"}).data)
        self.assertIn("nombre", self.client.post("/api/categorias/", {"nombre": "running"}).data)

    def test_no_se_borra_marca_con_tenis(self):
        r = self.client.delete(f"/api/marcas/{self.nike.id}/")
        self.assertEqual(r.status_code, 400)
        self.assertTrue(Marca.objects.filter(pk=self.nike.id).exists())

    def test_inventario_talla_repetida(self):
        r = self.client.post("/api/inventario/", {"tenis": self.tenis.id, "talla": "26"},
                             format="json")
        self.assertIn("talla", r.data)

    def test_entrada_con_cantidad_cero(self):
        r = self.client.post("/api/movimientos/", {"inventario": self.inv26.id, "tipo": "ENTRADA",
                                                   "cantidad": 0}, format="json")
        self.assertIn("cantidad", r.data)

    def test_salida_mayor_al_stock(self):
        r = self.client.post("/api/movimientos/", {"inventario": self.inv26.id, "tipo": "SALIDA",
                                                   "cantidad": 10}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Stock insuficiente", str(r.data["cantidad"]))
        self.inv26.refresh_from_db()
        self.assertEqual(self.inv26.cantidad, 5)

    def test_ajuste_sin_motivo(self):
        r = self.client.post("/api/movimientos/", {"inventario": self.inv26.id, "tipo": "AJUSTE",
                                                   "cantidad": 3}, format="json")
        self.assertIn("motivo", r.data)


class InventarioTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.como(self.admin)

    def test_entrada_salida_ajuste(self):
        url = "/api/movimientos/"
        r = self.client.post(url, {"inventario": self.inv26.id, "tipo": "ENTRADA", "cantidad": 3},
                             format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["stock_resultante"], 8)
        r = self.client.post(url, {"inventario": self.inv26.id, "tipo": "SALIDA", "cantidad": 2,
                                   "motivo": "Venta"}, format="json")
        self.assertEqual(r.data["stock_anterior"], 8)
        self.assertEqual(r.data["stock_resultante"], 6)
        r = self.client.post(url, {"inventario": self.inv26.id, "tipo": "AJUSTE", "cantidad": 4,
                                   "motivo": "Conteo físico"}, format="json")
        self.assertEqual(r.data["stock_resultante"], 4)
        self.assertEqual(r.data["usuario"], "admin")
        self.inv26.refresh_from_db()
        self.assertEqual(self.inv26.cantidad, 4)

    def test_movimientos_no_se_editan_ni_borran(self):
        self.client.post("/api/movimientos/", {"inventario": self.inv26.id, "tipo": "ENTRADA",
                                               "cantidad": 1}, format="json")
        mov = MovimientoInventario.objects.first()
        url = f"/api/movimientos/{mov.id}/"
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(self.client.patch(url, {"cantidad": 9}).status_code, 405)

    def test_cantidad_no_se_edita_directo(self):
        r = self.client.patch(f"/api/inventario/{self.inv26.id}/", {"cantidad": 99},
                              format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["cantidad"], 5)

    def test_crear_talla_con_cantidad_inicial(self):
        r = self.client.post("/api/inventario/", {"tenis": self.tenis.id, "talla": "28",
                                                  "cantidad_inicial": 7}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["cantidad"], 7)
        mov = MovimientoInventario.objects.get(inventario_id=r.data["id"])
        self.assertEqual((mov.tipo, mov.stock_anterior, mov.stock_resultante), ("ENTRADA", 0, 7))

    def test_filtros_inventario_y_movimientos(self):
        def ids(url):
            return [i["id"] for i in self.client.get(url).data["results"]]

        self.assertEqual(ids("/api/inventario/?sin_stock=true"), [self.inv27.id])
        self.assertEqual(ids("/api/inventario/?talla=26"), [self.inv26.id])
        self.assertEqual(len(ids(f"/api/inventario/?marca={self.nike.id}")), 2)
        self.assertEqual(len(ids(f"/api/inventario/?tenis={self.tenis.id}")), 2)
        self.client.post("/api/movimientos/", {"inventario": self.inv26.id, "tipo": "SALIDA",
                                               "cantidad": 1}, format="json")
        self.assertEqual(len(ids("/api/movimientos/?tipo=SALIDA")), 1)
        self.assertEqual(len(ids("/api/movimientos/?tipo=ENTRADA")), 0)
        self.assertEqual(len(ids(f"/api/movimientos/?inventario__tenis={self.tenis.id}")), 1)

    def test_bajo_stock_y_resumen(self):
        r = self.client.get("/api/inventario/bajo-stock/")
        self.assertEqual([i["id"] for i in r.data["results"]], [self.inv27.id])
        r = self.client.get("/api/inventario/resumen/")
        self.assertEqual(r.data["modelos"], 1)
        self.assertEqual(r.data["tallas_registradas"], 2)
        self.assertEqual(r.data["pares_en_inventario"], 5)
        self.assertEqual(r.data["tallas_bajo_stock"], 1)
        self.assertEqual(r.data["tallas_agotadas"], 1)

    def test_no_se_borra_tenis_con_ventas(self):
        self.client.post("/api/movimientos/", {"inventario": self.inv26.id, "tipo": "SALIDA",
                                               "cantidad": 1}, format="json")
        r = self.client.delete(f"/api/tenis/{self.tenis.id}/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("descontin", r.data["detail"])


class BusquedaFiltrosTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.adidas = Marca.objects.create(nombre="Adidas")
        self.samba = Tenis.objects.create(marca=self.adidas, sku="AD-001", nombre="Samba",
                                          color="Blanco", precio=Decimal("1800"),
                                          precio_oferta=Decimal("1500"), genero="M",
                                          estado=Tenis.Estado.DESCONTINUADO)
        self.samba.categorias.add(self.casual)

    def skus(self, query):
        return sorted(t["sku"] for t in self.client.get(f"/api/tenis/{query}").data["results"])

    def test_busqueda(self):
        self.assertEqual(self.skus("?search=samba"), ["AD-001"])
        self.assertEqual(self.skus("?search=nike"), ["NK-001"])
        self.assertEqual(self.skus("?search=ad-0"), ["AD-001"])

    def test_filtros(self):
        self.assertEqual(self.skus(f"?marca={self.adidas.id}"), ["AD-001"])
        self.assertEqual(self.skus(f"?categoria={self.casual.id}"), ["AD-001"])
        self.assertEqual(self.skus("?genero=M"), ["AD-001"])
        self.assertEqual(self.skus("?estado=ACTIVO"), ["NK-001"])
        self.assertEqual(self.skus("?color=Negro"), ["NK-001"])
        self.assertEqual(self.skus("?precio_min=2000"), ["NK-001"])
        self.assertEqual(self.skus("?precio_max=2000"), ["AD-001"])
        self.assertEqual(self.skus("?talla=26"), ["NK-001"])
        self.assertEqual(self.skus("?talla=27"), [])
        self.assertEqual(self.skus("?disponible=true"), ["NK-001"])
        self.assertEqual(self.skus("?disponible=false"), ["AD-001"])
        self.assertEqual(self.skus("?en_oferta=true"), ["AD-001"])
        self.assertEqual(self.skus("?en_oferta=false"), ["NK-001"])

    def test_stock_no_se_duplica_al_filtrar_por_categoria(self):
        self.tenis.categorias.add(self.casual)
        r = self.client.get(f"/api/tenis/?categoria={self.running.id}&categoria={self.casual.id}"
                            "&ordering=-stock")
        self.assertEqual(r.data["count"], 2)
        self.assertEqual(r.data["results"][0]["stock_total"], 5)

    def test_ordenamiento(self):
        r = self.client.get("/api/tenis/?ordering=precio")
        self.assertEqual([t["sku"] for t in r.data["results"]], ["AD-001", "NK-001"])
        r = self.client.get("/api/tenis/?ordering=-nombre")
        self.assertEqual([t["sku"] for t in r.data["results"]], ["AD-001", "NK-001"])
        r = self.client.get("/api/tenis/?ordering=-stock")
        self.assertEqual(r.data["results"][0]["sku"], "NK-001")


class AccionesPersonalizadasTests(BaseTest):
    def test_favoritos(self):
        url = f"/api/tenis/{self.tenis.id}/favorito/"
        self.assertEqual(self.client.post(url).status_code, 401)
        self.como(self.cliente)
        self.assertEqual(self.client.post(url).status_code, 201)
        self.assertEqual(self.client.post(url).status_code, 200)
        r = self.client.get("/api/tenis/favoritos/")
        self.assertEqual(r.data["count"], 1)
        self.assertTrue(r.data["results"][0]["es_favorito"])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get("/api/tenis/favoritos/").data["count"], 0)

    def test_cambiar_estado(self):
        url = f"/api/tenis/{self.tenis.id}/estado/"
        self.como(self.cliente)
        self.assertEqual(self.client.patch(url, {"estado": "DESCONTINUADO"}).status_code, 403)
        self.como(self.admin)
        self.assertEqual(self.client.patch(url, {"estado": "OTRO"}).status_code, 400)
        r = self.client.patch(url, {"estado": "DESCONTINUADO"})
        self.assertEqual(r.data["estado"], "DESCONTINUADO")
        self.assertFalse(self.client.get(f"/api/tenis/{self.tenis.id}/").data["disponible"])

    def test_estado_no_se_cambia_con_patch_normal(self):
        self.como(self.admin)
        self.client.patch(f"/api/tenis/{self.tenis.id}/", {"estado": "DESCONTINUADO"},
                          format="json")
        self.tenis.refresh_from_db()
        self.assertEqual(self.tenis.estado, Tenis.Estado.ACTIVO)

    def test_es_favorito_no_hace_una_consulta_por_tenis(self):
        def consultas_listado():
            with CaptureQueriesContext(connection) as ctx:
                r = self.client.get("/api/tenis/")
            return len(ctx.captured_queries), r

        self.como(self.cliente)
        self.tenis.favoritos.add(self.cliente)
        pocos, _ = consultas_listado()
        for i in range(5):
            Tenis.objects.create(marca=self.nike, sku=f"NK-10{i}", nombre=f"Modelo {i}",
                                 color="Rojo", precio=Decimal("1000"))
        muchos, r = consultas_listado()
        self.assertEqual(pocos, muchos)
        favoritos = {t["sku"]: t["es_favorito"] for t in r.data["results"]}
        self.assertTrue(favoritos["NK-001"])
        self.assertFalse(favoritos["NK-100"])

        self.client.credentials()
        r = self.client.get("/api/tenis/")
        self.assertFalse(any(t["es_favorito"] for t in r.data["results"]))

    def test_mas_vendidos(self):
        adidas = Marca.objects.create(nombre="Adidas")
        samba = Tenis.objects.create(marca=adidas, sku="AD-001", nombre="Samba", color="Blanco",
                                     precio=Decimal("1800"))
        inv = Inventario.objects.create(tenis=samba, talla=Decimal("26"), cantidad=10)
        Tenis.objects.create(marca=adidas, sku="AD-002", nombre="Gazelle", color="Azul",
                             precio=Decimal("1900"))
        salida = MovimientoInventario.Tipo.SALIDA
        registrar_movimiento(self.inv26, salida, 2, motivo="Venta")
        registrar_movimiento(inv, salida, 3, motivo="Venta")
        registrar_movimiento(inv, salida, 1, motivo="Venta")
        registrar_movimiento(inv, MovimientoInventario.Tipo.ENTRADA, 20, motivo="Compra")

        r = self.client.get("/api/tenis/mas-vendidos/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([(t["sku"], t["pares_vendidos"]) for t in r.data["results"]],
                         [("AD-001", 4), ("NK-001", 2)])

        r = self.client.get(f"/api/tenis/mas-vendidos/?marca={self.nike.id}&ordering=precio")
        self.assertEqual([t["sku"] for t in r.data["results"]], ["NK-001"])

    def test_disponibilidad(self):
        r = self.client.get(f"/api/tenis/{self.tenis.id}/disponibilidad/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t["talla"] for t in r.data["tallas"]], ["26.0"])


class ImagenesTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.como(self.admin)

    def test_subir_imagen(self):
        url = f"/api/tenis/{self.tenis.id}/imagen/"
        r = self.client.post(url, {"imagen": png()}, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["imagen"].startswith("http://testserver/media/tenis/"))
        self.tenis.refresh_from_db()
        anterior = self.tenis.imagen.path
        self.client.post(url, {"imagen": png("otra.png")}, format="multipart")
        self.assertFalse(os.path.exists(anterior))

    def test_cliente_no_sube_imagen(self):
        self.como(self.cliente)
        r = self.client.post(f"/api/tenis/{self.tenis.id}/imagen/", {"imagen": png()},
                             format="multipart")
        self.assertEqual(r.status_code, 403)

    def test_crear_marca_con_logo(self):
        r = self.client.post("/api/marcas/", {"nombre": "Puma", "logo": png("logo.png")},
                             format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("/media/marcas/", r.data["logo"])

    def test_extension_no_permitida(self):
        r = self.client.post(f"/api/tenis/{self.tenis.id}/imagen/", {"imagen": png("foto.gif")},
                             format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("imagen", r.data)

    @override_settings(MAX_IMAGEN_MB=0)
    def test_imagen_muy_pesada(self):
        r = self.client.post(f"/api/tenis/{self.tenis.id}/imagen/", {"imagen": png()},
                             format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("MB", str(r.data["imagen"]))


class AdminTests(BaseTest):
    def test_inline_de_inventario_registra_movimientos(self):
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)
        datos = {
            "sku": "NK-001", "nombre": "Pegasus", "marca": self.nike.id,
            "categorias": [self.running.id], "descripcion": "", "color": "Negro",
            "genero": "U", "estado": "ACTIVO", "precio": "2500", "precio_oferta": "",
            "inventario-TOTAL_FORMS": "3", "inventario-INITIAL_FORMS": "2",
            "inventario-MIN_NUM_FORMS": "0", "inventario-MAX_NUM_FORMS": "1000",
            "inventario-0-id": self.inv26.id, "inventario-0-tenis": self.tenis.id,
            "inventario-0-talla": "26.0", "inventario-0-cantidad": "8",
            "inventario-0-stock_minimo": "2",
            "inventario-1-id": self.inv27.id, "inventario-1-tenis": self.tenis.id,
            "inventario-1-talla": "27.0", "inventario-1-cantidad": "0",
            "inventario-1-stock_minimo": "2",
            "inventario-2-tenis": self.tenis.id, "inventario-2-talla": "28",
            "inventario-2-cantidad": "4", "inventario-2-stock_minimo": "2",
        }
        r = self.client.post(f"/admin/quickstart/tenis/{self.tenis.id}/change/", datos)
        self.assertEqual(r.status_code, 302)
        ajuste = MovimientoInventario.objects.get(inventario=self.inv26)
        self.assertEqual((ajuste.tipo, ajuste.stock_anterior, ajuste.stock_resultante,
                          ajuste.motivo), ("AJUSTE", 5, 8, "Ajuste desde el admin"))
        alta = MovimientoInventario.objects.get(inventario__talla=Decimal("28"))
        self.assertEqual((alta.tipo, alta.cantidad, alta.motivo),
                         ("ENTRADA", 4, "Alta desde el admin"))
        self.assertFalse(MovimientoInventario.objects.filter(inventario=self.inv27).exists())

    def test_movimientos_solo_lectura_en_admin(self):
        self.client.force_login(self.admin)
        self.admin.is_superuser = True
        self.admin.save()
        self.assertEqual(self.client.get("/admin/quickstart/movimientoinventario/add/").status_code,
                         403)
