import os
from pathlib import Path

# Carpeta raíz del proyecto (donde está manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent


# Seguridad: en producción se leen de variables de entorno; los valores por defecto son solo
# para desarrollo
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-w9&s*us7hn8)1i)a#@$flge!&ucsam&=qsp_s!ekw*8+!)-cen",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "si", "sí")

# Dominios separados por coma, ej. "midominio.com,www.midominio.com"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
                 if h.strip()]


# Apps: las de Django, DRF con tokens, django-filter y la app del catálogo
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "quickstart",
]

# Middleware por defecto de Django (sesiones, CSRF, autenticación, etc.)
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Archivo principal de rutas
ROOT_URLCONF = "tienda_tenis.urls"

# Plantillas: las usan el panel de administración y la API navegable de DRF
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "tienda_tenis.wsgi.application"


# Base de datos SQLite (archivo db.sqlite3 en la raíz)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Validación de contraseñas (la usa el registro): mínimo 8 caracteres, que no se parezca al
# usuario, que no sea común y que no sea solo números
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Idioma y zona horaria: mensajes en español de México y fechas en hora del centro
LANGUAGE_CODE = "es-mx"

TIME_ZONE = "America/Mexico_City"

USE_I18N = True

USE_TZ = True


# Archivos estáticos (CSS/JS del admin y de la API navegable)
STATIC_URL = "static/"

# Archivos subidos por los usuarios (imágenes de tenis y logos de marcas)
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Peso máximo de las imágenes, en MB (lo usa validar_imagen en serializers.py)
MAX_IMAGEN_MB = 2

# Tipo de llave primaria por defecto de los modelos
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Configuración global de Django REST Framework
REST_FRAMEWORK = {
    # Se acepta token (Postman, apps) y sesión (API navegable en el navegador)
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Por defecto todo pide login; cada vista abre lo que es público (ej. el catálogo)
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Filtros (?marca=), búsqueda (?search=) y orden (?ordering=) disponibles en todas las vistas
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    # Paginación: 10 resultados por página (?page=2)
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    # Límite de peticiones para login y registro (ScopedRateThrottle en views.py)
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "registro": "5/min",
    },
}
