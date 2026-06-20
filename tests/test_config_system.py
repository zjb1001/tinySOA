import pytest
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from tinysoa.config.schema import (
    Config,
    ServiceConfig,
    RuntimeConfig,
    LoggingConfig,
    ObservabilityConfig,
    LogLevel,
)
from tinysoa.config.loader import ConfigLoader
from tinysoa.core.errors import ValidationError


def test_service_config_validation():
    # Valid config
    svc = ServiceConfig(name="echo", port=8080)
    svc.validate()
    
    # Invalid port
    with pytest.raises(ValidationError):
        svc = ServiceConfig(name="echo", port=70000)
        svc.validate()
    
    # Invalid timeout
    with pytest.raises(ValidationError):
        svc = ServiceConfig(name="echo", timeout=-1)
        svc.validate()
    
    # Empty name
    with pytest.raises(ValidationError):
        svc = ServiceConfig(name="")
        svc.validate()


def test_runtime_config_validation():
    # Valid config
    rt = RuntimeConfig(thread_pool_size=10)
    rt.validate()
    
    # Invalid thread pool size
    with pytest.raises(ValidationError):
        rt = RuntimeConfig(thread_pool_size=0)
        rt.validate()
    
    # Invalid health check interval
    with pytest.raises(ValidationError):
        rt = RuntimeConfig(health_check_interval=-1)
        rt.validate()


def test_logging_config_validation():
    # Valid stdout
    log = LoggingConfig(level=LogLevel.INFO, output="stdout")
    log.validate()
    
    # Invalid output
    with pytest.raises(ValidationError):
        log = LoggingConfig(output="invalid")
        log.validate()
    
    # File output without path
    with pytest.raises(ValidationError):
        log = LoggingConfig(output="file", file_path=None)
        log.validate()
    
    # File output with path
    log = LoggingConfig(output="file", file_path="/tmp/test.log")
    log.validate()


def test_observability_config_validation():
    # Valid config
    obs = ObservabilityConfig(enable_metrics=True, metrics_port=9090)
    obs.validate()
    
    # Invalid port
    with pytest.raises(ValidationError):
        obs = ObservabilityConfig(metrics_port=70000)
        obs.validate()
    
    # Tracing enabled without endpoint
    with pytest.raises(ValidationError):
        obs = ObservabilityConfig(enable_tracing=True, tracing_endpoint=None)
        obs.validate()
    
    # Tracing enabled with endpoint
    obs = ObservabilityConfig(enable_tracing=True, tracing_endpoint="http://localhost:4318")
    obs.validate()


def test_config_from_dict():
    data = {
        "services": [
            {"name": "echo", "port": 8080},
            {"name": "calc", "port": 8081},
        ],
        "runtime": {
            "thread_pool_size": 20,
        },
        "logging": {
            "level": "debug",
            "output": "stdout",
        },
        "observability": {
            "enable_metrics": True,
        },
        "custom": {
            "my_key": "my_value",
        },
    }
    
    config = Config.from_dict(data)
    config.validate()
    
    assert len(config.services) == 2
    assert config.services[0].name == "echo"
    assert config.runtime.thread_pool_size == 20
    assert config.logging.level == LogLevel.DEBUG
    assert config.observability.enable_metrics is True
    assert config.custom["my_key"] == "my_value"


def test_config_to_dict_roundtrip():
    config = Config(
        services=[
            ServiceConfig(name="echo", port=8080),
            ServiceConfig(name="calc", port=8081),
        ],
        runtime=RuntimeConfig(thread_pool_size=15),
        logging=LoggingConfig(level=LogLevel.WARNING),
    )
    
    data = config.to_dict()
    restored = Config.from_dict(data)
    
    assert len(restored.services) == 2
    assert restored.services[0].name == "echo"
    assert restored.runtime.thread_pool_size == 15
    assert restored.logging.level == LogLevel.WARNING


def test_config_duplicate_service_names():
    data = {
        "services": [
            {"name": "echo", "port": 8080},
            {"name": "echo", "port": 8081},
        ],
    }
    
    config = Config.from_dict(data)
    with pytest.raises(ValidationError, match="Duplicate service names"):
        config.validate()


def test_loader_from_dict():
    loader = ConfigLoader()
    data = {
        "services": [{"name": "test", "port": 9000}],
        "runtime": {"thread_pool_size": 5},
    }
    
    config = loader.load_from_dict(data)
    
    assert config.services[0].name == "test"
    assert config.runtime.thread_pool_size == 5
    assert loader.config is config


def test_loader_from_json_file():
    loader = ConfigLoader()
    
    data = {
        "services": [{"name": "file_service", "port": 7000}],
        "logging": {"level": "info"},
    }
    
    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        temp_path = f.name
    
    try:
        config = loader.load_from_file(temp_path)
        assert config.services[0].name == "file_service"
        assert config.logging.level == LogLevel.INFO
    finally:
        os.unlink(temp_path)


def test_loader_from_nonexistent_file():
    loader = ConfigLoader()
    
    with pytest.raises(ValidationError, match="not found"):
        loader.load_from_file("/nonexistent/path/config.json")


def test_loader_from_env():
    loader = ConfigLoader()
    
    # Set some environment variables
    os.environ["TINYSOA_RUNTIME_THREAD_POOL_SIZE"] = "25"
    os.environ["TINYSOA_LOGGING_LEVEL"] = "error"
    os.environ["TINYSOA_OBSERVABILITY_ENABLE_METRICS"] = "false"
    
    try:
        env_data = loader.load_from_env()
        
        assert env_data["runtime"]["thread_pool_size"] == 25
        assert env_data["logging"]["level"] == "error"
        assert env_data["observability"]["enable_metrics"] is False
    finally:
        # Clean up
        del os.environ["TINYSOA_RUNTIME_THREAD_POOL_SIZE"]
        del os.environ["TINYSOA_LOGGING_LEVEL"]
        del os.environ["TINYSOA_OBSERVABILITY_ENABLE_METRICS"]


def test_loader_parse_value():
    loader = ConfigLoader()
    
    # Bool
    assert loader._parse_value("true") is True
    assert loader._parse_value("FALSE") is False
    assert loader._parse_value("yes") is True
    assert loader._parse_value("0") is False
    
    # Int
    assert loader._parse_value("123") == 123
    assert loader._parse_value("-456") == -456
    
    # Float
    assert loader._parse_value("3.14") == 3.14
    assert loader._parse_value("-2.5") == -2.5
    
    # String
    assert loader._parse_value("hello") == "hello"
    assert loader._parse_value("192.168.1.1") == "192.168.1.1"


def test_loader_merge_configs():
    loader = ConfigLoader()
    
    base = {
        "services": [{"name": "base", "port": 8000}],
        "runtime": {"thread_pool_size": 10, "enable_health_check": True},
        "logging": {"level": "info"},
    }
    
    override = {
        "runtime": {"thread_pool_size": 20},
        "logging": {"level": "debug", "output": "file"},
        "observability": {"enable_metrics": False},
    }
    
    merged = loader.merge_configs(base, override)
    
    # Base service preserved
    assert merged["services"][0]["name"] == "base"
    
    # Runtime partially overridden
    assert merged["runtime"]["thread_pool_size"] == 20
    assert merged["runtime"]["enable_health_check"] is True
    
    # Logging merged
    assert merged["logging"]["level"] == "debug"
    assert merged["logging"]["output"] == "file"
    
    # New section added
    assert merged["observability"]["enable_metrics"] is False


def test_loader_full_load_with_priority():
    loader = ConfigLoader()
    
    # Create a config file
    file_data = {
        "services": [{"name": "file_svc", "port": 6000}],
        "runtime": {"thread_pool_size": 5},
        "logging": {"level": "warning"},
    }
    
    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(file_data, f)
        temp_path = f.name
    
    # Set env vars
    os.environ["TINYSOA_RUNTIME_THREAD_POOL_SIZE"] = "10"
    os.environ["TINYSOA_LOGGING_LEVEL"] = "info"
    
    # Override dict
    override = {
        "runtime": {"thread_pool_size": 15},
    }
    
    try:
        config = loader.load(file_path=temp_path, override=override)
        
        # File: service name from file
        assert config.services[0].name == "file_svc"
        
        # Override wins: thread_pool_size
        assert config.runtime.thread_pool_size == 15
        
        # Env wins over file: logging level
        assert config.logging.level == LogLevel.INFO
    finally:
        os.unlink(temp_path)
        del os.environ["TINYSOA_RUNTIME_THREAD_POOL_SIZE"]
        del os.environ["TINYSOA_LOGGING_LEVEL"]


def test_loader_reload():
    loader = ConfigLoader()
    
    with pytest.raises(ValidationError):
        loader.reload()
    
    data = {"services": [{"name": "test", "port": 8000}]}
    config = loader.load_from_dict(data)
    
    reloaded = loader.reload()
    assert reloaded is config
