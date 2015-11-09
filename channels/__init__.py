__version__ = "0.8"

# Load backends, using settings if available (else falling back to a default)
DEFAULT_CHANNEL_BACKEND = "default"
from .backends import BackendManager
from django.conf import settings
channel_backends = BackendManager(
    getattr(settings, "CHANNEL_BACKENDS", {
        DEFAULT_CHANNEL_BACKEND: {
            "BACKEND": "channels.backends.memory.InMemoryChannelBackend",
            "ROUTING": {},
        }
    })
)

default_app_config = 'channels.apps.ChannelsConfig'

# Promote channel to top-level (down here to avoid circular import errs)
from .channel import Channel, Group  # NOQA
