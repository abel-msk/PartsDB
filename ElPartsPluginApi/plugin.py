"""Common contract implemented by every PartsDB plugin."""
from abc import ABC, abstractmethod


class Plugin(ABC):
    @abstractmethod
    def get_plugin_type(self) -> str:
        """Return the supported type declared in this plugin's manifest."""
        raise NotImplementedError
