import os
from pathlib import Path

import environ

environ.Env.read_env(Path(__file__).resolve().parent.parent / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()
