# Tienda de Tenis: API REST con inventario

Proyecto Final de Tópicos Avanzados de Desarrollo Web. Es una API REST hecha con Django REST Framework que expone un catálogo de tenis (marcas, categorías y modelos) y controla el inventario por talla, con historial de entradas, salidas y ajustes.

## Instalación

Requiere Python 3.13 o superior (probado con 3.14). Desde la carpeta raíz del proyecto (donde está `manage.py`):

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py cargar_datos     # datos de ejemplo: 6 marcas, 14 tenis, tallas, ventas e imágenes
python manage.py runserver
```

`cargar_datos` crea dos usuarios de prueba:

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin` | `Admin12345` | staff (puede todo y entra al panel `/admin/`) |
| `cliente` | `Cliente12345` | usuario normal (consulta y maneja sus favoritos) |

- API navegable: http://127.0.0.1:8000/api/
- Panel de administración: http://127.0.0.1:8000/admin/
- Pruebas automáticas: `python manage.py test quickstart` (49 pruebas)

### Variables de entorno (opcionales)

En desarrollo no hace falta definir nada. En producción:

| Variable | Para qué | Valor por defecto |
|---|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta de Django | una clave insegura solo para desarrollo |
| `DJANGO_DEBUG` | `true` / `false` | `true` |
| `DJANGO_ALLOWED_HOSTS` | Dominios permitidos, separados por coma | vacío (con `DEBUG` activo basta para `localhost`) |

## Probar con Postman

Importa `TiendaTenis.postman_collection.json`. Ejecuta la carpeta **1. Autenticación** completa (o solo **Login admin**, que es la última): guarda el token en la variable `{{token}}` y todas las demás peticiones lo usan solas. La colección tiene 68 peticiones organizadas por tema, incluida una carpeta de validaciones que deben fallar con 400.

Para subir imágenes, el body va en **form-data**. En la clave `imagen`, cambia el tipo de *Text* a *File* y elige la foto.

## Modelo de datos

```
Marca 1 ──< N Tenis N >──< N Categoria
                │ N >──< N User        (favoritos)
                │
                1
                └──< N Inventario (una fila por talla)
                          1
                          └──< N MovimientoInventario (ENTRADA / SALIDA / AJUSTE) >── User
```

- **Tenis.stock_total** = suma de las existencias de todas sus tallas.
- **Inventario.cantidad** no se edita directamente: solo cambia al registrar un movimiento, así cada cambio de stock queda en el historial con quién lo hizo y por qué.
- **MovimientoInventario** guarda el stock anterior y el resultante. Se puede crear y consultar, pero no editar ni borrar.

## Endpoints

Todos van bajo `/api/`. Header de autenticación: `Authorization: Token <token>`.

| Método | Ruta | Quién | Qué hace |
|---|---|---|---|
| POST | `register/` | público | Crear cuenta |
| POST | `api-token-auth/` | público | Login: devuelve `token`, `user_id`, `username`, `email`, `is_staff` |
| GET / PATCH | `me/` | autenticado | Ver o editar mi perfil (email y username no pueden ser de otro usuario) |
| POST | `logout/` | autenticado | Borrar el token (204) |
| POST | `reset-token/` | autenticado | Borrar el token actual y obtener uno nuevo |
| GET | `tenis/`, `marcas/`, `categorias/` | público | Consultar el catálogo |
| POST / PUT / PATCH / DELETE | `tenis/`, `marcas/`, `categorias/` | admin | Administrar el catálogo |
| POST / DELETE | `tenis/<id>/favorito/` | autenticado | Agregar o quitar de mis favoritos |
| GET | `tenis/favoritos/` | autenticado | Mis favoritos |
| PATCH | `tenis/<id>/estado/` | admin | `{"estado": "DESCONTINUADO"}` o `"ACTIVO"` |
| POST | `tenis/<id>/imagen/` | admin | Subir o reemplazar la imagen (form-data) |
| GET | `tenis/<id>/disponibilidad/` | público | Tallas con existencias |
| GET | `tenis/mas-vendidos/` | público | Ranking por pares vendidos (suma de salidas); acepta los mismos filtros que `tenis/` |
| CRUD | `inventario/` | admin | Tallas registradas por modelo |
| GET | `inventario/bajo-stock/` | admin | Tallas con cantidad ≤ stock mínimo |
| GET | `inventario/resumen/` | admin | Totales del inventario |
| GET / POST | `movimientos/` | admin | Historial y registro de entradas, salidas y ajustes |

### Búsqueda, filtros y orden en `tenis/`

| Parámetro | Ejemplo |
|---|---|
| `search` | `?search=air` (busca en nombre, SKU, color, marca y descripción) |
| `marca`, `categoria` | `?marca=1&categoria=3` |
| `color` | `?color=Negro` |
| `genero` | `?genero=M` (H, M, U, N) |
| `estado` | `?estado=DESCONTINUADO` |
| `precio_min`, `precio_max` | `?precio_min=1500&precio_max=3000` |
| `talla` | `?talla=26.5` (solo modelos con existencias en esa talla) |
| `disponible` | `?disponible=true` (activos y con stock) |
| `en_oferta` | `?en_oferta=true` |
| `ordering` | `?ordering=precio`, `-precio`, `nombre`, `-creado`, `-stock` |
| `page` | `?page=2` (10 resultados por página) |

En `inventario/`: `?tenis=`, `?talla=`, `?marca=`, `?sin_stock=true`. En `movimientos/`: `?tipo=SALIDA`, `?inventario=`, `?inventario__tenis=`, `?usuario=`.

## Dónde está cada punto del proyecto

| # | Punto | Archivo | Qué se implementó |
|---|---|---|---|
| 1 | Autenticación (token) | `views.py` → `CustomAuthToken`, `RegisterView`, `me`, `logout`, `reset_token` | Registro con `validate_password` y email/username únicos, login que devuelve el token con los datos del usuario, perfil editable, logout que borra el token y renovación de token. |
| 2 | Modelos y relaciones | `models.py` | `ForeignKey` (Marca→Tenis, Tenis→Inventario, Inventario→Movimiento), `ManyToMany` (Tenis↔Categoría, Tenis↔User para favoritos), `UniqueConstraint` (una fila por tenis y talla), `TextChoices`. |
| 3 | Panel de administración | `admin.py` | `list_display`, `list_filter`, `search_fields`, `list_editable`, `fieldsets`, miniaturas de imagen, inline de tallas dentro del tenis, acciones masivas (descontinuar/activar) e historial de solo lectura. Si se edita una cantidad desde el admin, se registra como movimiento. |
| 4 | Serializers anidados | `serializers.py` → `TenisSerializer`, `MarcaDetalleSerializer` | El tenis trae su marca, categorías e inventario anidados, y se puede **crear con sus tallas en una sola petición** (anidado escribible). El detalle de una marca trae todos sus tenis. |
| 5 | Búsqueda y filtros | `filters.py`, `views.py` | `SearchFilter`, `OrderingFilter` y `FilterSet` propios con filtros personalizados (talla con stock, disponible, rango de precio, en oferta). |
| 6 | Vistas | `views.py` | `ModelViewSet` registrados con `DefaultRouter`, `GenericViewSet` con mixins (movimientos sin editar ni borrar), `CreateAPIView` para el registro y `@api_view` para `me`, `logout` y `reset-token`. |
| 7 | Validaciones | `serializers.py`, `services.py` | Por campo (`validate_sku`, `validate_precio`, `validate_talla`, imagen), entre campos (`validate`: oferta < precio) y de negocio (no vender más de lo que hay, ajuste con motivo, no borrar tenis con ventas ni marcas con tenis). |
| 8 | Subir archivos (imágenes) | `models.py`, `views.py` → acción `imagen` | `ImageField` en Tenis y Marca, validación de extensión y peso (máx 2 MB) y borrado de la imagen anterior al reemplazarla. |
| 9 | Custom actions | `views.py` → `@action` | `favorito`, `favoritos`, `estado`, `imagen`, `disponibilidad`, `mas-vendidos`, `bajo-stock` y `resumen`, con permisos propios y códigos HTTP correctos (201, 204, 400, 403). |
| 10 | Settings | `tienda_tenis/settings.py` | Bloque `REST_FRAMEWORK` (token, permisos, filtros y paginación por defecto), `MEDIA_URL`/`MEDIA_ROOT`, idioma `es-mx` y zona horaria de México, límites de peticiones (`DEFAULT_THROTTLE_RATES`) y `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` desde variables de entorno. |

### Mejoras extra

- **Sin consultas repetidas en `es_favorito`:** el listado de tenis calcula si cada uno es favorito del usuario con una anotación `Exists` en la misma consulta. Antes se hacía una consulta extra por cada tenis de la página. La prueba `test_es_favorito_no_hace_una_consulta_por_tenis` lo comprueba.
- **Más vendidos:** `GET tenis/mas-vendidos/` suma los movimientos `SALIDA` de cada modelo con `Subquery` + `Coalesce` y los ordena de mayor a menor.
- **Límite de peticiones:** el login permite 10 intentos por minuto y el registro 5 por minuto por IP (`ScopedRateThrottle`). Al pasarse se responde 429, lo que frena ataques de fuerza bruta a contraseñas.
- **Secretos fuera del código:** `SECRET_KEY`, `DEBUG` y `ALLOWED_HOSTS` se pueden definir con variables de entorno.

### Permisos

- `IsAdminOrReadOnly` (`permissions.py`): cualquiera consulta el catálogo y solo el staff lo modifica. A diferencia de la versión vista en clase, también define `has_permission`, así que un usuario normal tampoco puede crear registros con POST.
- El inventario y los movimientos usan `IsAdminUser`.
- Los favoritos usan `IsAuthenticated`: cada usuario solo ve y modifica los suyos.

## Estructura

```
SporTenis-DJango/
├── .venv/                 entorno virtual (no se sube a git)
├── media/                 imágenes subidas: tenis/ y marcas/ (se crea con cargar_datos)
├── tienda_tenis/          proyecto: settings.py, urls.py, wsgi.py, asgi.py
├── quickstart/            app de la API
│   ├── models.py          Marca, Categoria, Tenis, Inventario, MovimientoInventario
│   ├── serializers.py     serializers anidados y validaciones
│   ├── views.py           viewsets, acciones personalizadas, autenticación
│   ├── filters.py         filtros personalizados
│   ├── permissions.py     IsAdminOrReadOnly
│   ├── services.py        lógica de movimientos de inventario
│   ├── admin.py           panel personalizado
│   ├── urls.py            router
│   ├── tests.py           49 pruebas
│   ├── migrations/
│   └── management/commands/cargar_datos.py
├── db.sqlite3             base de datos (se crea con migrate)
├── manage.py
├── TiendaTenis.postman_collection.json
├── requirements.txt
└── README.md
```
