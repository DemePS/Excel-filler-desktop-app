"""The person's DeepSeek API key, saved on this PC and handed to the agent engine.

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
SERVICE, ACCOUNT = "ComptaIA", "deepseek-api-key"

KEYS_URL = "https://platform.deepseek.com/api_keys"  # where a person gets a key ("Get my API key")
MODELS = [("", "Default")]  # the one model of the service: the engine's default
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

    @staticmethod
    def _apply(key: str) -> None:
        """Hand the key to the engine: DeepSeek is chosen through its own variables."""
        from coding_agent import configure
        os.environ["DEEPSEEK_API_KEY"] = key
        os.environ["CODEAGENT_PROVIDER"] = "deepseek"
        configure(api_key="", model="")  # no key of another service: the engine goes to DeepSeek

    def saved_key(self) -> str | None:
        try:
            return self.store.get() or None
        except Exception as e:
            log.warning("Could not read the saved API key (%s: %s)", type(e).__name__, e)
            return None

    def load_and_apply(self) -> None:
        """At startup: hand a saved key to the engine."""
        key = self.saved_key()
        if key:
            self._apply(key)

    def save(self, api_key: str) -> None:
        with self.lock:
            self.store.set(api_key)
            self._apply(api_key)

    def remove(self) -> None:
        from coding_agent import config
        with self.lock:
            self.store.delete()
            config.clear()  # back to the environment (a Foundry setup)
            os.environ.pop("DEEPSEEK_API_KEY", None)
            os.environ.pop("CODEAGENT_PROVIDER", None)

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
            "keys_url": KEYS_URL,
            "storage": "credential-manager" if self.store.persistent else "session",
        }
