import io
import random
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from quickstart.models import Categoria, Inventario, Marca, MovimientoInventario, Tenis
from quickstart.services import registrar_movimiento

MARCAS = [("Nike", "Estados Unidos"), ("Adidas", "Alemania"), ("Puma", "Alemania"),
          ("New Balance", "Estados Unidos"), ("Converse", "Estados Unidos"),
          ("Vans", "Estados Unidos")]

CATEGORIAS = [("Running", "Para correr"), ("Basketball", "Para cancha"),
              ("Casual", "Uso diario"), ("Fútbol", "Tacos y tenis de fútbol"),
              ("Skate", "Suela plana y resistente"), ("Training", "Gimnasio y entrenamiento")]

TENIS = [
    ("NK-PEG41-NG", "Pegasus 41", "Nike", ["Running"], "Negro/Blanco", "U", "2899", None, "#1f2937"),
    ("NK-AF1-BL", "Air Force 1 '07", "Nike", ["Casual"], "Blanco", "U", "2499", "2199", "#e5e7eb"),
    ("NK-LBJ22-RJ", "LeBron XXII", "Nike", ["Basketball"], "Rojo", "H", "4599", None, "#b91c1c"),
    ("AD-ULTRA-GR", "Ultraboost 5", "Adidas", ["Running"], "Gris", "M", "3799", "3299", "#6b7280"),
    ("AD-SAMBA-NG", "Samba OG", "Adidas", ["Casual", "Fútbol"], "Negro", "U", "2399", None, "#111827"),
    ("AD-PRED-AZ", "Predator League", "Adidas", ["Fútbol"], "Azul", "H", "1899", None, "#1d4ed8"),
    ("PM-SUEDE-VD", "Suede Classic", "Puma", ["Casual"], "Verde", "U", "1699", "1399", "#15803d"),
    ("PM-VELO-NR", "Velocity Nitro 3", "Puma", ["Running"], "Naranja", "M", "2799", None, "#ea580c"),
    ("NB-574-GR", "574 Core", "New Balance", ["Casual"], "Gris", "U", "2199", None, "#9ca3af"),
    ("NB-990V6-AZ", "990v6", "New Balance", ["Running", "Casual"], "Azul marino", "H", "4999", None, "#1e3a8a"),
    ("CV-CHUCK-NG", "Chuck Taylor All Star", "Converse", ["Casual"], "Negro", "U", "1299", None, "#0f172a"),
    ("VN-OLDSK-NB", "Old Skool", "Vans", ["Skate", "Casual"], "Negro/Blanco", "U", "1599", None, "#27272a"),
    ("NK-METCON-BL", "Metcon 9", "Nike", ["Training"], "Blanco", "M", "2999", None, "#f3f4f6"),
    ("PM-KIDS-RS", "Smash v2 Kids", "Puma", ["Casual"], "Rosa", "N", "899", None, "#db2777"),
]

TALLAS_ADULTO = ["24", "24.5", "25", "25.5", "26", "26.5", "27", "27.5", "28", "29"]
TALLAS_NINO = ["17", "18", "19", "20", "21"]


def imagen_placeholder(texto, color_hex):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 400), color_hex)
    d = ImageDraw.Draw(img)
    claro = sum(int(color_hex[i:i + 2], 16) for i in (1, 3, 5)) > 450
    tinta = "#111111" if claro else "#ffffff"
    d.rounded_rectangle([120, 210, 480, 280], radius=30, outline=tinta, width=6)
    d.polygon([(140, 210), (220, 140), (330, 150), (380, 210)], outline=tinta, width=6)
    d.line([(120, 300), (480, 300)], fill=tinta, width=8)
    d.text((300, 350), texto, fill=tinta, anchor="mm", font_size=28)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = "Carga datos de ejemplo para la tienda de tenis."

    def handle(self, *args, **options):
        random.seed(42)

        admin, creado = User.objects.get_or_create(
            username="admin", defaults={"email": "admin@tenis.local", "is_staff": True,
                                        "is_superuser": True})
        if creado:
            admin.set_password("Admin12345")
            admin.save()
        cliente, creado = User.objects.get_or_create(
            username="cliente", defaults={"email": "cliente@tenis.local"})
        if creado:
            cliente.set_password("Cliente12345")
            cliente.save()
        for u in (admin, cliente):
            Token.objects.get_or_create(user=u)

        marcas = {n: Marca.objects.get_or_create(nombre=n, defaults={"pais_origen": p})[0]
                  for n, p in MARCAS}
        categorias = {n: Categoria.objects.get_or_create(nombre=n, defaults={"descripcion": d})[0]
                      for n, d in CATEGORIAS}

        nuevos = 0
        for sku, nombre, marca, cats, color, genero, precio, oferta, hex_ in TENIS:
            if Tenis.objects.filter(sku=sku).exists():
                continue
            tenis = Tenis.objects.create(
                sku=sku, nombre=nombre, marca=marcas[marca], color=color, genero=genero,
                precio=Decimal(precio), precio_oferta=Decimal(oferta) if oferta else None,
                descripcion=f"{marca} {nombre} en color {color.lower()}.",
            )
            tenis.categorias.set([categorias[c] for c in cats])
            tenis.imagen.save(f"{sku.lower()}.png",
                              imagen_placeholder(f"{marca} {nombre}", hex_), save=True)

            tallas = TALLAS_NINO if genero == "N" else TALLAS_ADULTO
            for talla in tallas:
                inv = Inventario.objects.create(tenis=tenis, talla=Decimal(talla), cantidad=0)
                cantidad = random.choice([0, 1, 2, 3, 5, 8, 10, 12])
                if cantidad:
                    registrar_movimiento(inv, MovimientoInventario.Tipo.ENTRADA, cantidad,
                                         usuario=admin, motivo="Stock inicial")
                    if cantidad > 3 and random.random() < 0.5:
                        registrar_movimiento(inv, MovimientoInventario.Tipo.SALIDA,
                                             random.randint(1, 3), usuario=admin,
                                             motivo="Venta en tienda")
            nuevos += 1

        Tenis.objects.filter(sku="CV-CHUCK-NG").update(estado=Tenis.Estado.DESCONTINUADO)
        for sku in ("NK-AF1-BL", "AD-SAMBA-NG"):
            Tenis.objects.get(sku=sku).favoritos.add(cliente)

        self.stdout.write(self.style.SUCCESS(f"Listo: {nuevos} tenis nuevos."))
        self.stdout.write("Usuarios de prueba:")
        self.stdout.write(f"  admin   / Admin12345    token: {admin.auth_token.key}")
        self.stdout.write(f"  cliente / Cliente12345  token: {cliente.auth_token.key}")
