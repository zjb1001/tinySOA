from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from enum import Enum

from tinysoa.core.errors import ValidationError


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ServiceConfig:
    """Configuration for a service."""
    name: str
    version: str = "1.0.0"
    host: str = "localhost"
    port: int = 8080
    protocol: str = "tcp"
    timeout: float = 30.0
    max_retries: int = 3
    
    def validate(self) -> None:
        """Validate service configuration."""
        if not self.name:
            raise ValidationError("Service name is required")
        if not (0 < self.port < 65536):
            raise ValidationError(f"Invalid port: {self.port}")
        if self.timeout <= 0:
            raise ValidationError(f"Timeout must be positive: {self.timeout}")
        if self.max_retries < 0:
            raise ValidationError(f"max_retries must be non-negative: {self.max_retries}")


@dataclass
class RuntimeConfig:
    """Runtime configuration."""
    thread_pool_size: int = 10
    enable_health_check: bool = True
    health_check_interval: float = 60.0
    graceful_shutdown_timeout: float = 30.0
    
    def validate(self) -> None:
        """Validate runtime configuration."""
        if self.thread_pool_size <= 0:
            raise ValidationError(f"thread_pool_size must be positive: {self.thread_pool_size}")
        if self.health_check_interval <= 0:
            raise ValidationError(f"health_check_interval must be positive")
        if self.graceful_shutdown_timeout < 0:
            raise ValidationError(f"graceful_shutdown_timeout must be non-negative")


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: LogLevel = LogLevel.INFO
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    output: str = "stdout"
    file_path: Optional[str] = None
    
    def validate(self) -> None:
        """Validate logging configuration."""
        if self.output not in ("stdout", "stderr", "file"):
            raise ValidationError(f"Invalid output: {self.output}")
        if self.output == "file" and not self.file_path:
            raise ValidationError("file_path is required when output is 'file'")


@dataclass
class ObservabilityConfig:
    """Observability configuration."""
    enable_metrics: bool = True
    enable_tracing: bool = False
    metrics_port: int = 9090
    tracing_endpoint: Optional[str] = None
    
    def validate(self) -> None:
        """Validate observability configuration."""
        if self.metrics_port and not (0 < self.metrics_port < 65536):
            raise ValidationError(f"Invalid metrics_port: {self.metrics_port}")
        if self.enable_tracing and not self.tracing_endpoint:
            raise ValidationError("tracing_endpoint is required when enable_tracing is True")


@dataclass
class Config:
    """Root configuration schema for tinySOA."""
    services: List[ServiceConfig] = field(default_factory=list)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    custom: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """Validate the entire configuration."""
        self.runtime.validate()
        self.logging.validate()
        self.observability.validate()
        
        for svc_config in self.services:
            svc_config.validate()
        
        # Check for duplicate service names
        names = [s.name for s in self.services]
        if len(names) != len(set(names)):
            raise ValidationError("Duplicate service names found")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create Config from dictionary."""
        services = []
        for svc_data in data.get("services", []):
            services.append(ServiceConfig(**svc_data))
        
        runtime_data = data.get("runtime", {})
        runtime = RuntimeConfig(**runtime_data)
        
        logging_data = data.get("logging", {})
        if "level" in logging_data:
            logging_data["level"] = LogLevel(logging_data["level"])
        logging = LoggingConfig(**logging_data)
        
        obs_data = data.get("observability", {})
        observability = ObservabilityConfig(**obs_data)
        
        custom = data.get("custom", {})
        
        return cls(
            services=services,
            runtime=runtime,
            logging=logging,
            observability=observability,
            custom=custom,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Config to dictionary."""
        return {
            "services": [
                {
                    "name": s.name,
                    "version": s.version,
                    "host": s.host,
                    "port": s.port,
                    "protocol": s.protocol,
                    "timeout": s.timeout,
                    "max_retries": s.max_retries,
                }
                for s in self.services
            ],
            "runtime": {
                "thread_pool_size": self.runtime.thread_pool_size,
                "enable_health_check": self.runtime.enable_health_check,
                "health_check_interval": self.runtime.health_check_interval,
                "graceful_shutdown_timeout": self.runtime.graceful_shutdown_timeout,
            },
            "logging": {
                "level": self.logging.level.value,
                "format": self.logging.format,
                "output": self.logging.output,
                "file_path": self.logging.file_path,
            },
            "observability": {
                "enable_metrics": self.observability.enable_metrics,
                "enable_tracing": self.observability.enable_tracing,
                "metrics_port": self.observability.metrics_port,
                "tracing_endpoint": self.observability.tracing_endpoint,
            },
            "custom": self.custom,
        }


ConfigSchema = Config  # Alias for backward compatibility
