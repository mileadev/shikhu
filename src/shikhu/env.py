"""Where shikhu finds your OpenRouter key.

First found wins: your shell, then this repo's .env, then the key `shikhu init` saved for
every repo. The same order gh and hf use: a key you set on purpose beats the saved one.
"""

import os
import tempfile
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

KEY_NAME = "OPENROUTER_API_KEY"


def user_env_path() -> Path:
    """The .env `shikhu init` saves your key to, shared by every repo."""
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "shikhu" / ".env"


def load_env() -> None:
    """Load the repo's .env, then the saved one. load_dotenv never overrides a variable
    that's already set, so loading in this order is what ranks them."""
    # usecwd=True: otherwise it searches upward from this installed package, not the repo.
    load_dotenv(Path.cwd() / ".env.local")
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(user_env_path())


def save_key(key: str) -> Path:
    """Save `key` to the user .env, readable only by you, keeping anything else in it."""
    if not key or "\n" in key or "\r" in key:
        raise ValueError("API key must be a non-empty single line")
    path = user_env_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise RuntimeError("Refusing to write API key through a symlink")
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if not line.strip().startswith(f"{KEY_NAME}=")]
    lines.append(f"{KEY_NAME}={key}")
    fd, temporary = tempfile.mkstemp(prefix=".env.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path
