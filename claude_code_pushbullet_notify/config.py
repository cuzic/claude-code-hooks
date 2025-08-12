"""Configuration management for Claude Code Pushbullet notifications."""

import logging
import sys
from pathlib import Path

import tomllib
from dotenv import load_dotenv

# Load environment variables from .env file in project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Default configuration
DEFAULT_NUM_MESSAGES = 3
DEFAULT_MAX_BODY_LENGTH = 1000
DEFAULT_SPLIT_LONG_MESSAGES = True


def merge_configs(default, loaded):
    """Recursively merge two configuration dictionaries."""
    result = default.copy()
    for key, value in loaded.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    """Load configuration from config.toml file."""
    config_path = Path(__file__).parent.parent / "config.toml"
    config = {
        "notification": {
            "num_messages": DEFAULT_NUM_MESSAGES,
            "max_body_length": DEFAULT_MAX_BODY_LENGTH,
            "split_long_messages": DEFAULT_SPLIT_LONG_MESSAGES,
        },
        "pushbullet": {},
        "logging": {"debug": True, "log_file": "claude-code-pushbullet-notify.log"},
    }

    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                loaded_config = tomllib.load(f)
                # Recursively merge loaded config with defaults
                config = merge_configs(config, loaded_config)
        except Exception as e:
            logging.error(f"Error loading config: {e}")

    return config


# Load configuration on import
CONFIG = load_config()


def setup_logging():
    """Configure logging based on config settings."""
    log_level = logging.DEBUG if CONFIG["logging"]["debug"] else logging.INFO
    log_file = Path(__file__).parent.parent / CONFIG["logging"]["log_file"]

    # Configure logging to file and stderr
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stderr)],
    )


# Set up logging when module is imported
setup_logging()
logger = logging.getLogger(__name__)