from .app import APP_CONFIG, DICE_CONFIG
from .system import SYSTEM_CONFIG
from .gateway import GATEWAY_CONFIG
from .worker import WORKER_CONFIG

TORTOISE_ORM = {
    "connections": {
        "default": SYSTEM_CONFIG.database_connection_string,
    },
    "apps": {
        # TODO: rename app to "piltover"
        "models": {
            "models": ["piltover.db.models"],
            "default_connection": "default",
            "migrations": "piltover.db.migrations",
        },
    },
}
