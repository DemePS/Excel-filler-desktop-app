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

The organization's values are built into the downloadable app (excel_filler/organization.json,
filled by the release build); environment variables override them:
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
ORGANIZATION_FILE = Path(__file__).with_name("organization.json")
ORGANIZATION_KEYS = {"gateway": "EXCEL_FILLER_GATEWAY", "api_scope": "EXCEL_FILLER_API_SCOPE",
                     "client_id": "EXCEL_FILLER_CLIENT_ID", "tenant_id": "EXCEL_FILLER_TENANT_ID"}


def organization_defaults(file: Path = ORGANIZATION_FILE) -> None:
    """The organization's settings built into the app, unless environment variables set them."""
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for key, variable in ORGANIZATION_KEYS.items():
        if str(data.get(key) or "").strip() and not os.environ.get(variable):
            os.environ[variable] = str(data[key]).strip()


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
    organization_defaults()
    url = (os.environ.get("EXCEL_FILLER_GATEWAY") or "").strip().rstrip("/")
    headers = {"x-app-name": "excel-filler", "x-app-version": app_version()}
    # The organization's app registration: the sign-in (and the access check) use it.
    if os.environ.get("EXCEL_FILLER_TENANT_ID"):
        os.environ["AZURE_TENANT_ID"] = os.environ["EXCEL_FILLER_TENANT_ID"]
    if os.environ.get("EXCEL_FILLER_CLIENT_ID"):
        os.environ["ANTHROPIC_FOUNDRY_CLIENT_ID"] = os.environ["EXCEL_FILLER_CLIENT_ID"]
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


# --- Access: is the signed-in person an authorized Excel filler user?

@dataclass
class Access:
    state: str  # "allowed", "denied", "signin_failed", "unreachable", or "not_required" (no gateway)
    user: str | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.state in ("allowed", "not_required")


ROLE = "Excel.Filler.User"


def access_required() -> bool:
    """With the organization's app registration (the downloadable app), only its authorized users may
    use Excel filler. Without it (developers), no check: Foundry is called with your own credential."""
    return bool(os.environ.get("EXCEL_FILLER_CLIENT_ID") and os.environ.get("EXCEL_FILLER_API_SCOPE"))


def token_claims(token: str) -> dict:
    """A token's claims, for this app's decisions about what to show: the token is not verified here
    (Entra ID issued it to this sign-in; the gateway verifies it on every call)."""
    import base64

    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims if isinstance(claims, dict) else {}
    except (IndexError, ValueError):
        return {}


def check_access() -> Access:
    """Sign in (the Windows account, or the Microsoft sign-in page once) for the organization's Excel
    filler app registration. Entra ID decides: with "assignment required", only members of the Excel
    filler users group get a token, and it carries the Excel.Filler.User role. No other service is
    asked."""
    if not access_required():
        return Access("not_required")
    from coding_agent import errors, signin

    try:
        token = signin.access_token(os.environ["EXCEL_FILLER_API_SCOPE"])
    except Exception as error:
        text = str(error)
        if "AADSTS50105" in text:  # the user is not assigned to the application (not in the group)
            return Access("denied", None, "Your account is not assigned to Excel filler. Ask IT to add you to "
                          "the Excel filler users group.")
        return Access("signin_failed", message=errors.describe(error) or f"{type(error).__name__}: {error}")
    claims = token_claims(token)
    user = claims.get("name") or claims.get("preferred_username") or claims.get("upn")
    roles = claims.get("roles") or []
    if ROLE in (roles if isinstance(roles, list) else [roles]):
        return Access("allowed", user)
    return Access("denied", user, "Your account does not have the Excel filler user role. Ask IT to add you to "
                  "the Excel filler users group.")


def is_access_refusal(error: BaseException) -> bool:
    """A call to Claude refused by the gateway because the person is not (or no longer) allowed."""
    return getattr(error, "status_code", None) == 403 and bool(_current.url)

