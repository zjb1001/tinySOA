from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Any

from tinysoa.core.errors import StateError, DuplicateError, NotFoundError


class PluginLifecycle(str, Enum):
    """Plugin lifecycle states."""
    REGISTERED = "registered"
    INITIALIZED = "initialized"
    STARTED = "started"
    STOPPED = "stopped"
    TERMINATED = "terminated"


class Plugin(ABC):
    """Base plugin interface.
    
    Plugins extend the framework with custom functionality:
    - Custom interceptors
    - Custom health checkers
    - Protocol handlers
    - Storage backends
    - etc.
    """
    
    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self._state = PluginLifecycle.REGISTERED
        self._config: Dict[str, Any] = {}
    
    @property
    def state(self) -> PluginLifecycle:
        return self._state
    
    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the plugin with settings."""
        self._config = config
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the plugin (load resources, establish connections, etc.)."""
        if self._state != PluginLifecycle.REGISTERED:
            raise StateError(f"Cannot initialize from state {self._state}")
        self._state = PluginLifecycle.INITIALIZED
    
    @abstractmethod
    def start(self) -> None:
        """Start the plugin (begin active operation)."""
        if self._state != PluginLifecycle.INITIALIZED:
            raise StateError(f"Cannot start from state {self._state}")
        self._state = PluginLifecycle.STARTED
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the plugin (pause active operation)."""
        if self._state != PluginLifecycle.STARTED:
            raise StateError(f"Cannot stop from state {self._state}")
        self._state = PluginLifecycle.STOPPED
    
    @abstractmethod
    def terminate(self) -> None:
        """Terminate the plugin (cleanup resources)."""
        self._state = PluginLifecycle.TERMINATED


class PluginManager:
    """Manages plugin registration, lifecycle, and discovery."""
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
    
    def register(self, plugin: Plugin) -> None:
        """Register a plugin."""
        if plugin.name in self._plugins:
            raise DuplicateError(f"Plugin '{plugin.name}' already registered")
        self._plugins[plugin.name] = plugin
    
    def unregister(self, name: str) -> None:
        """Unregister a plugin by name."""
        plugin = self._plugins.pop(name, None)
        if plugin and plugin.state != PluginLifecycle.TERMINATED:
            plugin.terminate()
    
    def get(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)
    
    def list_plugins(self) -> List[Plugin]:
        """List all registered plugins."""
        return list(self._plugins.values())
    
    def initialize_all(self) -> None:
        """Initialize all registered plugins."""
        for plugin in self._plugins.values():
            if plugin.state == PluginLifecycle.REGISTERED:
                plugin.initialize()
    
    def start_all(self) -> None:
        """Start all initialized plugins."""
        for plugin in self._plugins.values():
            if plugin.state == PluginLifecycle.INITIALIZED:
                plugin.start()
    
    def stop_all(self) -> None:
        """Stop all started plugins."""
        for plugin in self._plugins.values():
            if plugin.state == PluginLifecycle.STARTED:
                plugin.stop()
    
    def terminate_all(self) -> None:
        """Terminate all plugins."""
        for plugin in self._plugins.values():
            if plugin.state != PluginLifecycle.TERMINATED:
                plugin.terminate()


# Example plugin implementations

class DummyPlugin(Plugin):
    """A simple plugin for testing."""
    
    def __init__(self, name: str = "dummy"):
        super().__init__(name)
        self.initialized = False
        self.started = False
        self.stopped = False
        self.terminated = False
    
    def initialize(self) -> None:
        super().initialize()
        self.initialized = True
    
    def start(self) -> None:
        super().start()
        self.started = True
    
    def stop(self) -> None:
        super().stop()
        self.stopped = True
    
    def terminate(self) -> None:
        super().terminate()
        self.terminated = True


class CachePlugin(Plugin):
    """A simple cache plugin for demonstration."""
    
    def __init__(self, name: str = "cache"):
        super().__init__(name)
        self._cache: Dict[str, Any] = {}
    
    def initialize(self) -> None:
        super().initialize()
        max_size = self._config.get("max_size", 1000)
        self._max_size = max_size
    
    def start(self) -> None:
        super().start()
    
    def stop(self) -> None:
        super().stop()
    
    def terminate(self) -> None:
        super().terminate()
        self._cache.clear()
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        return self._cache.get(key)
    
    def set(self, key: str, value: Any) -> None:
        """Set a value in cache."""
        if len(self._cache) >= getattr(self, '_max_size', 1000):
            # Simple eviction: remove first item
            if self._cache:
                self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value
    
    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
