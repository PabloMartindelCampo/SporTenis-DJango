import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tienda_tenis.settings")

application = get_asgi_application()
