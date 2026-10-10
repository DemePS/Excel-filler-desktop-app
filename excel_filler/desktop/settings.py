"""The person's Anthropic API key and model, saved on this PC and handed to the agent engine.

The key goes to the Windows Credential Manager (through `keyring`), never to a file. When no keyring
works it is kept in memory for this run only, and the window says so. The model, which is not a secret,
is a small JSON file next to the agent's other files.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Protocol

log = logging.getLogger("excel-filler.settings")

HOME = Path(os.environ["HOME"]).expanduser() if os.environ.get("HOME") else Path.home()
SETTINGS_FILE = HOME / ".coding-agent" / "excel-filler-settings.json"
SERVICE, ACCOUNT = "Excel filler", "anthropic-api-key"

# What the window offers. "" is the engine's default.
MODELS = [
    ("", "Default (recommended)"),
    ("claude-opus-5-5", "Most capable (claude-opus-5-5)"),
    ("claude-sonnet-5-5", "Balanced: faster and cheaper (claude-sonnet-5-5)"),
    ("claude-haiku-4-5", "Fastest and cheapest (claude-haiku-4-5)"),
]
KEY_FORMAT = re.compile(r"[\x21-\x7e]{20,300}")  # visible ASCII, no spaces


class SecretStore(Protocol):
    persistent: bool

    def get(self) -> str | None: ...
    def set(self, value: str) -> None: ...
    def delete(self) -> None: ...


class MemoryStore:
    """For this run only (no keyring on this PC)."""

    persistent = False

    def __init__(self) -> None:
        self.value: str | None = None

    def get(self) -> str | None:
        return self.value

    def set(self, value: str) -> None:
        self.value = value

    def delete(self) -> None:
        self.value = None


class KeyringStore:
    """Windows Credential Manager (macOS Keychain, Linux Secret Service). Raises if no keyring works."""

    persistent = True

    def __init__(self) -> None:
        import keyring
        from keyring.backends import fail
        if os.name == "nt":
            from keyring.backends.Windows import WinVaultKeyring
            keyring.set_keyring(WinVaultKeyring())
        if isinstance(keyring.get_keyring(), fail.Keyring):
            raise RuntimeError("no keyring backend")
        self._keyring = keyring

    def get(self) -> str | None:
        return self._keyring.get_password(SERVICE, ACCOUNT)

    def set(self, value: str) -> None:
        self._keyring.set_password(SERVICE, ACCOUNT, value)

    def delete(self) -> None:
        try:
            self._keyring.delete_password(SERVICE, ACCOUNT)
        except self._keyring.errors.PasswordDeleteError:
            pass  # nothing was saved


def default_store() -> SecretStore:
    try:
        return KeyringStore()
    except Exception as e:  # no keyring module or backend
        log.warning("No keyring (%s: %s): the API key will not be remembered after the window closes.",
                    type(e).__name__, e)
        return MemoryStore()


def valid_key(key: str) -> bool:
    return bool(KEY_FORMAT.fullmatch(key))


class Settings:
    """The saved key and model, and what the engine is told to use."""

    def __init__(self, store: SecretStore | None = None, path: Path | None = None) -> None:
        self.store = store if store is not None else default_store()
        self.path = path or SETTINGS_FILE
        self.lock = threading.RLock()  # a save or remove must not run while a job runs: the server takes it

    def model(self) -> str:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8")).get("model", "")
        except (OSError, ValueError, AttributeError):
            return ""
        return value if value in dict(MODELS) else ""

    def _write_model(self, model: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"model": model}), encoding="utf-8")
        tmp.replace(self.path)

    def saved_key(self) -> str | None:
        try:
            return self.store.get() or None
        except Exception as e:
            log.warning("Could not read the saved API key (%s: %s)", type(e).__name__, e)
            return None

    def load_and_apply(self) -> None:
        """At startup: hand a saved key and model to the engine."""
        from coding_agent import configure
        key = self.saved_key()
        if key:
            configure(api_key=key, model=self.model())

    def save(self, api_key: str, model: str) -> None:
        from coding_agent import configure
        with self.lock:
            self.store.set(api_key)
            self._write_model(model)
            configure(api_key=api_key, model=model)

    def remove(self) -> None:
        from coding_agent import config
        with self.lock:
            self.store.delete()
            config.clear()  # back to the environment (a Foundry setup, or ANTHROPIC_API_KEY)

    def info(self) -> dict:
        """What the window shows: never the key, only its last four characters."""
        from coding_agent import active_provider
        saved = self.saved_key()
        provider = active_provider()
        source = "saved" if saved else ("foundry" if provider == "foundry" else "environment" if provider else "none")
        return {
            "configured": provider is not None,
            "source": source,
            "key_hint": saved[-4:] if saved else None,
            "model": self.model(),
            "models": [{"id": i, "label": label} for i, label in MODELS],
            "storage": "credential-manager" if self.store.persistent else "session",
        }
