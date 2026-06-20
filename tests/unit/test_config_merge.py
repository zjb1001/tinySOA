import os
import pytest
from tinysoa.config.loader import ConfigLoader
from tinysoa.config.schema import Config

def test_merge_dicts():
    loader = ConfigLoader()
    base = {
        "a": 1,
        "b": {"c": 2, "d": 3},
        "e": [1, 2]
    }
    override = {
        "a": 10,
        "b": {"c": 20},
        "f": "new"
    }
    
    merged = loader.merge_configs(base, override)
    
    assert merged["a"] == 10
    assert merged["b"]["c"] == 20
    assert merged["b"]["d"] == 3
    assert merged["e"] == [1, 2]
    assert merged["f"] == "new"
    
    # Original should be untouched
    assert base["a"] == 1

def test_load_priority(tmp_path):
    # Create a dummy config file
    config_file = tmp_path / "config.json"
    config_file.write_text('{"runtime": {"thread_pool_size": 5}, "logging": {"level": "debug"}}')
    
    loader = ConfigLoader()
    
    # Set env vars
    os.environ["TINYSOA_RUNTIME_THREAD_POOL_SIZE"] = "20"
    
    try:
        config = loader.load(file_path=config_file)
        
        # Env should override file
        assert config.runtime.thread_pool_size == 20
        # File should override default (default is usually INFO)
        assert config.logging.level == "debug"
        # Default should be preserved if not overridden
        assert config.runtime.enable_health_check is True
        
    finally:
        del os.environ["TINYSOA_RUNTIME_THREAD_POOL_SIZE"]

def test_load_env_types():
    loader = ConfigLoader()
    
    os.environ["TINYSOA_RUNTIME_HEALTH_CHECK_INTERVAL"] = "15.5"
    os.environ["TINYSOA_RUNTIME_ENABLE_HEALTH_CHECK"] = "false"
    
    try:
        config = loader.load()
        assert config.runtime.health_check_interval == 15.5
        assert config.runtime.enable_health_check is False
    finally:
        del os.environ["TINYSOA_RUNTIME_HEALTH_CHECK_INTERVAL"]
        del os.environ["TINYSOA_RUNTIME_ENABLE_HEALTH_CHECK"]
