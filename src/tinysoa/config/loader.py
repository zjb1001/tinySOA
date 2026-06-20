from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from tinysoa.config.schema import Config
from tinysoa.core.errors import ValidationError


class ConfigLoader:
    """Multi-source configuration loader.
    
    Supports loading configuration from:
    - JSON/YAML files
    - Environment variables
    - Direct dictionary injection
    - Merging multiple sources with priority
    """
    
    ENV_PREFIX = "TINYSOA_"
    
    def __init__(self):
        self._config: Optional[Config] = None
    
    def load_from_file(self, file_path: Union[str, Path]) -> Config:
        """Load configuration from a JSON or YAML file."""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise ValidationError(f"Config file not found: {file_path}")
        
        with open(file_path, "r") as f:
            if file_path.suffix in (".yaml", ".yml"):
                # Try to import yaml
                try:
                    import yaml
                    data = yaml.safe_load(f)
                except ImportError:
                    raise ValidationError("PyYAML not installed. Install with: pip install pyyaml")
            elif file_path.suffix == ".json":
                data = json.load(f)
            else:
                raise ValidationError(f"Unsupported file format: {file_path.suffix}")
        
        config = Config.from_dict(data or {})
        config.validate()
        self._config = config
        return config
    
    def load_from_dict(self, data: Dict[str, Any]) -> Config:
        """Load configuration from a dictionary."""
        config = Config.from_dict(data)
        config.validate()
        self._config = config
        return config
    
    def load_from_env(self, prefix: str = ENV_PREFIX) -> Dict[str, Any]:
        """Load configuration from environment variables.
        
        Environment variables are mapped as follows:
        - TINYSOA_RUNTIME_THREAD_POOL_SIZE -> runtime.thread_pool_size
        - TINYSOA_LOGGING_LEVEL -> logging.level
        - etc.
        
        Returns a partial config dict that can be merged with other sources.
        """
        config_data: Dict[str, Any] = {
            "runtime": {},
            "logging": {},
            "observability": {},
            "custom": {},
        }
        
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            
            # Remove prefix and convert to lowercase
            config_key = key[len(prefix):].lower()
            parts = config_key.split("_")
            
            if len(parts) < 2:
                continue
            
            section = parts[0]
            field = "_".join(parts[1:])
            
            if section in config_data:
                # Try to parse as int, float, bool, or keep as string
                parsed_value = self._parse_value(value)
                config_data[section][field] = parsed_value
        
        return config_data
    
    def _parse_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Try bool
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        
        # Try int
        try:
            return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
            
        return value

    def merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries.
        
        Args:
            base: Base dictionary
            override: Dictionary with overrides
            
        Returns:
            Merged dictionary (new instance)
        """
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.merge_configs(result[key], value)
            else:
                result[key] = value
                
        return result

    def load(self, file_path: Optional[Union[str, Path]] = None, env_prefix: str = ENV_PREFIX, override: Optional[Dict[str, Any]] = None) -> Config:
        """Load configuration from multiple sources with priority.
        
        Priority (lowest to highest):
        1. Default values (from schema)
        2. Config file (if provided)
        3. Environment variables
        4. Override dict (if provided)
        
        Args:
            file_path: Path to config file (optional)
            env_prefix: Prefix for environment variables
            override: Optional dictionary to override all other sources
            
        Returns:
            Validated Config object
        """
        # 1. Start with defaults (empty dict will use dataclass defaults)
        config_data: Dict[str, Any] = {}
        
        # 2. Load from file if provided
        if file_path:
            file_path = Path(file_path)
            if file_path.exists():
                with open(file_path, "r") as f:
                    if file_path.suffix in (".yaml", ".yml"):
                        try:
                            import yaml
                            file_data = yaml.safe_load(f) or {}
                        except ImportError:
                            raise ValidationError("PyYAML not installed")
                    elif file_path.suffix == ".json":
                        file_data = json.load(f) or {}
                    else:
                        raise ValidationError(f"Unsupported file format: {file_path.suffix}")
                
                config_data = self.merge_configs(config_data, file_data)
        
        # 3. Load from environment
        env_data = self.load_from_env(env_prefix)
        config_data = self.merge_configs(config_data, env_data)
        
        # 4. Apply overrides
        if override:
            config_data = self.merge_configs(config_data, override)
        
        # 5. Create and validate Config object
        config = Config.from_dict(config_data)
        config.validate()
        self._config = config
        return config
    def reload(self) -> Config:
        """Reload configuration (for dynamic refresh support)."""
        if self._config is None:
            raise ValidationError("No configuration loaded yet")
        # For now, just return the cached config
        # In a real implementation, this would re-read sources
        return self._config
    
    @property
    def config(self) -> Optional[Config]:
        """Get the currently loaded configuration."""
        return self._config
