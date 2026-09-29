"""Reaching Claude through the organization's API Management gateway, and its central settings.

With EXCEL_FILLER_GATEWAY set (by IT, once per PC: Intune, Group Policy, or the installer), the app
talks only to the gateway, never to Foundry directly:
- every request carries the employee's Microsoft sign-in token for the gateway's API (no key on
  the PC); the gateway checks it, then calls Foundry with its own identity;
- at startup the app reads the gateway's settings (GET <gateway>/settings): the Claude deployment
  to use, the minimum app version, and an optional notice to show. IT changes them in the gateway
  (named values), and every PC follows at its next launch.

The last settings read are kept (~/.coding-agent/gateway-settings.json), so a gateway that does not
answer at startup does not stop the app: the next call to Claude says whether it is reachable.

Call configure() before importing coding_agent: the engine reads its settings when imported.

Environment variables (IT sets them; see infra/README.md):
    EXCEL_FILLER_GATEWAY      https://<apim>.azure-api.net/excel-filler
    EXCEL_FILLER_API_SCOPE    api://<gateway API app id>/.default
    EXCEL_FILLER_CLIENT_ID    the desktop app's registration (public client) employees sign in with
    EXCEL_FILLER_TENANT_ID    the organization's tenant (for this app only, unlike AZURE_TENANT_ID)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

log = logging.getLogger("excel-filler")

SETTINGS_FILE_NAME = "gateway-settings.json"


def app_version() -> str:
    try:
        return version("excel-filler-desktop-app")
    except PackageNotFoundError:
        return "0.0.0"


def version_tuple(text: str) -> tuple[int, ...]:
    parts = []
    for part in str(text).split("."):
        digits = "".join(c for c in part if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


@dataclass
class Gateway:
    url: str | None = None  # None: no gateway, Foundry is called directly (developers)
    deployment: str | None = None
    minimum_version: str | None = None
    notice: str | None = None  # a message from IT, shown in the window
    source: str = "none"  # "gateway", "saved" (the last settings read) or "none"
    problem: str | None = None  # why the settings could not be read
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def update_required(self) -> str | None:
        """Why this version may not be used (None if it may)."""
        if self.minimum_version and version_tuple(app_version()) < version_tuple(self.minimum_version):
            return (f"This version of Excel filler ({app_version()}) is no longer supported: version "
                    f"{self.minimum_version} or later is required. Please install the latest version.")
        return None


_current = Gateway()


def current() -> Gateway:
    return _current


def fetch_settings(url: str, headers: dict[str, str], timeout: float = 10.0) -> dict:
    import httpx

    response = httpx.get(url.rstrip("/") + "/settings", headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("the gateway's settings are not a JSON object")
    return data


def configure(home: Path) -> Gateway:
    """Point the agent engine at the gateway and apply its settings. Without EXCEL_FILLER_GATEWAY,
    nothing changes (Foundry is called directly, as configured by ANTHROPIC_FOUNDRY_*)."""
    global _current
    url = (os.environ.get("EXCEL_FILLER_GATEWAY") or "").strip().rstrip("/")
    headers = {"x-app-name": "excel-filler", "x-app-version": app_version()}
    if not url:
        _current = Gateway(headers=headers)
        return _current

    saved = home / ".coding-agent" / SETTINGS_FILE_NAME
    gateway = Gateway(url=url, headers=headers)
    try:
        settings = fetch_settings(url, headers)
        gateway.source = "gateway"
        try:
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_text(json.dumps({"url": url, **settings}, indent=2), encoding="utf-8")
        except OSError:
            pass
    except Exception as error:  # unreachable, refused, not JSON...
        gateway.problem = f"{type(error).__name__}: {error}"
        settings = {}
        try:
            data = json.loads(saved.read_text(encoding="utf-8"))
            if data.get("url") == url:
                settings, gateway.source = data, "saved"
        except (OSError, ValueError):
            pass
    gateway.deployment = str(settings["deployment"]) if settings.get("deployment") else None
    gateway.minimum_version = str(settings["minimum_version"]) if settings.get("minimum_version") else None
    gateway.notice = str(settings["notice"]) if settings.get("notice") else None

    # The engine: the gateway as its endpoint, signing in for the gateway's API; never a key.
    os.environ["ANTHROPIC_FOUNDRY_ENDPOINT"] = url
    os.environ.pop("ANTHROPIC_FOUNDRY_API_KEY", None)
    if os.environ.get("EXCEL_FILLER_API_SCOPE"):
        os.environ["TOKEN_SCOPE"] = os.environ["EXCEL_FILLER_API_SCOPE"]
    if os.environ.get("EXCEL_FILLER_TENANT_ID"):
        os.environ["AZURE_TENANT_ID"] = os.environ["EXCEL_FILLER_TENANT_ID"]
    if os.environ.get("EXCEL_FILLER_CLIENT_ID"):
        os.environ["ANTHROPIC_FOUNDRY_CLIENT_ID"] = os.environ["EXCEL_FILLER_CLIENT_ID"]
    if gateway.deployment:
        os.environ["ANTHROPIC_FOUNDRY_DEPLOYMENT"] = gateway.deployment
    _current = gateway
    return gateway


def apply_headers() -> None:
    """Send the app's name and version with every request (the gateway logs them per user)."""
    from coding_agent import config

    config.CLIENT_HEADERS.update(_current.headers)


def describe(gateway: Gateway) -> str:
    """One line for the log: where the settings came from."""
    if not gateway.url:
        return "no gateway (Foundry called directly)"
    where = {"gateway": "read from the gateway", "saved": "the last ones read (gateway not reachable)",
             "none": "none (gateway not reachable, never read)"}[gateway.source]
    text = (f"gateway {gateway.url}; settings: {where}; deployment {gateway.deployment or '(default)'}"
            f"{'; minimum version ' + gateway.minimum_version if gateway.minimum_version else ''}")
    return text + (f"; problem: {gateway.problem}" if gateway.problem else "")
