"""Public Hermes surfaces used by the Volcengine voice plugin.

Configuration is read through ``hermes_cli.config.load_config_readonly()`` (the
documented, non-mutating ``config.yaml`` accessor for plugins) and credentials
through ``agent.secret_scope.get_secret()`` (the profile-aware secret route
named by the plugin catalog). No Hermes core module is imported for its private
helpers and nothing is rebound.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def load_config_section(section: str) -> dict[str, Any]:
    """Return one top-level ``config.yaml`` section, or ``{}`` when unavailable."""
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
        value = config.get(section)
        return value if isinstance(value, dict) else {}
    except Exception as exc:  # config read is best-effort; the caller keeps its defaults
        logger.debug("volcengine-voice: could not read %s config: %s", section, exc)
        return {}


def load_tts_config() -> dict[str, Any]:
    """The ``tts`` config section (``provider`` plus ``volcengine.*``)."""
    return load_config_section("tts")


def load_stt_config() -> dict[str, Any]:
    """The ``stt`` config section (``provider`` plus ``volcengine.*``)."""
    return load_config_section("stt")


def active_tts_provider() -> str:
    """The configured ``tts.provider``, normalized, or ``""`` when unset."""
    provider = load_tts_config().get("provider")
    return provider.strip().lower() if isinstance(provider, str) else ""


def get_secret(name: str, default: str = "") -> str:
    """Resolve a credential through Hermes's profile-aware secret scope.

    Falls back to ``os.environ`` only when the public secret module is not
    importable (e.g. running the plugin's unit tests outside Hermes). A scope
    error returns *default* instead of reading another profile's environment.
    """
    try:
        from agent.secret_scope import get_secret as hermes_get_secret
    except ImportError:
        value = os.getenv(name, default)
    else:
        try:
            value = hermes_get_secret(name, default)
        except Exception as exc:
            logger.warning("volcengine-voice: could not resolve %s: %s", name, exc)
            value = default
    return value if isinstance(value, str) else default
