"""Active Directory authentication for ShotDeck.

    from auth import authenticate
    result = authenticate(prompt=login_dialog.prompt)

login_dialog is imported separately because it pulls in Qt; the SSO path and
the bind path are usable headless.
"""

from .ad_auth import (
    AuthError,
    AuthResult,
    authenticate,
    authenticate_password,
    authenticate_system_login,
    BIND, DENIED, DEV, DISABLED, SSO,
)
from .config import AuthConfig, load as load_config

__all__ = [
    "AuthConfig", "AuthError", "AuthResult",
    "authenticate", "authenticate_password", "authenticate_system_login",
    "load_config",
    "BIND", "DENIED", "DEV", "DISABLED", "SSO",
]
