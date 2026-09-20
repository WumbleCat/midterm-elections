"""Runtime settings, read from environment variables (and an optional .env file).

Secrets are never logged. Keys are read lazily so importing the package never
fails because a key is missing; connectors that need one raise
:class:`AuthenticationError` at fetch time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

PACKAGE_VERSION = "0.1.0"

# Environment variable names for every credential the platform knows about.
KEY_ENV_VARS = ("CENSUS_API_KEY", "BLS_API_KEY", "BEA_API_KEY", "FEC_API_KEY")


def _find_project_root() -> Path | None:
    """Walk up from this file to find a pyproject.toml (editable installs)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def default_data_dir() -> Path:
    env = os.environ.get("ELECTIONDATA_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    root = _find_project_root()
    if root is not None:
        return root / "data"
    return Path.cwd() / "data"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    census_api_key: str | None = None
    bls_api_key: str | None = None
    bea_api_key: str | None = None
    fec_api_key: str = "DEMO_KEY"
    contact_email: str | None = None
    http_timeout: float = 60.0
    http_retries: int = 4
    http_backoff_seconds: float = 1.5
    ssl_verify: bool = True
    log_level: str = "INFO"
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def user_agent(self) -> str:
        contact = f" ({self.contact_email})" if self.contact_email else ""
        return f"electiondata/{PACKAGE_VERSION}{contact}"

    def key_for(self, env_var: str) -> str | None:
        mapping = {
            "CENSUS_API_KEY": self.census_api_key,
            "BLS_API_KEY": self.bls_api_key,
            "BEA_API_KEY": self.bea_api_key,
            "FEC_API_KEY": self.fec_api_key,
        }
        if env_var in mapping:
            return mapping[env_var]
        return os.environ.get(env_var) or None

    def has_key(self, env_var: str) -> bool:
        return bool(self.key_for(env_var))


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_settings(dotenv: bool = True) -> Settings:
    if dotenv:
        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path, override=False)
    return Settings(
        data_dir=default_data_dir(),
        census_api_key=_clean(os.environ.get("CENSUS_API_KEY")),
        bls_api_key=_clean(os.environ.get("BLS_API_KEY")),
        bea_api_key=_clean(os.environ.get("BEA_API_KEY")),
        fec_api_key=_clean(os.environ.get("FEC_API_KEY")) or "DEMO_KEY",
        contact_email=_clean(os.environ.get("ELECTIONDATA_CONTACT_EMAIL")),
        http_timeout=float(os.environ.get("ELECTIONDATA_HTTP_TIMEOUT", "60")),
        http_retries=int(os.environ.get("ELECTIONDATA_HTTP_RETRIES", "4")),
        ssl_verify=_env_flag("ELECTIONDATA_SSL_VERIFY", True),
        log_level=os.environ.get("ELECTIONDATA_LOG_LEVEL", "INFO").upper(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reset_settings() -> None:
    """Clear the cached settings (used by tests that change env vars)."""
    get_settings.cache_clear()
