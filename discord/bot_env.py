"""Small env/SSL setup helpers shared by the independent bots in this
directory (feature_bot.py, stat_bot.py). Deliberately NOT shared with the
old chatbot_bot.py -- that file keeps its own local copies since it's
slated for eventual removal and isn't worth coupling to.
"""

from __future__ import annotations

import os
import ssl
from pathlib import Path

import aiohttp


def ensure_ssl_ca_bundle() -> None:
    """Ensure aiohttp/disnake can validate TLS certificates -- useful on
    macOS/Python installs where the CA bundle is missing from the default
    trust path."""
    if os.getenv("SSL_CERT_FILE"):
        return
    try:
        import certifi

        os.environ["SSL_CERT_FILE"] = certifi.where()
    except Exception:
        pass


def build_ssl_connector() -> aiohttp.TCPConnector | None:
    try:
        if os.getenv("DISCORD_SSL_NO_VERIFY", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            print("WARNING: DISCORD_SSL_NO_VERIFY is enabled. TLS cert verification is disabled.")
            return aiohttp.TCPConnector(ssl=ctx)

        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
        return aiohttp.TCPConnector(ssl=ctx)
    except Exception:
        return None


def load_local_env() -> None:
    """Precedence: existing process env, then discord/.env, then repo_root/.env."""
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    for env_path in (here / ".env", repo_root / ".env"):
        if not env_path.exists():
            continue
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()


def strip_bot_mention(content: str, bot_user_id: int) -> str:
    return content.replace(f"<@{bot_user_id}>", "").replace(f"<@!{bot_user_id}>", "").strip()
