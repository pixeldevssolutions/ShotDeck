"""Active Directory authentication for Flow.

Produces the validated login the rest of the app runs as:

    result = authenticate(prompt=login_dialog.prompt)
    if result.authorized:
        window.login = result.login

Two paths, tried in order:

  1. system-login trust (SSO)  -- the box is domain-joined, so the artist
     already authenticated to AD at OS login. We only confirm group
     membership. No password is ever handled by the app.
  2. explicit LDAP bind        -- ask for username and password, bind to the
     domain controller over an encrypted channel, then read the bound user's
     own group membership. The password lives for the duration of the bind
     call and is never logged, cached or written to disk.

Fail closed: any error, any inconclusive check, any missing group is a denial
with a readable reason, never an exception into the UI.
"""

import getpass
import os
import ssl

import applog

from . import config as auth_config
from . import group_check

log = applog.get()

MAX_ATTEMPTS = 3

# Methods, for logging and for the UI to explain how the artist got in.
DEV = "dev"
DISABLED = "disabled"
SSO = "sso"
BIND = "bind"
DENIED = "denied"


class AuthResult:
    """Outcome of an authentication attempt.

    login          AD sAMAccountName, mapped to the ShotGrid HumanUser login
    display_name   human-readable name for the header, falls back to login
    authorized     True only when identity and group membership both hold
    method         one of DEV / DISABLED / SSO / BIND / DENIED
    reason         why authorization failed, empty when it did not
    """

    def __init__(self, login="", display_name="", authorized=False,
                 method=DENIED, reason="", domain=""):
        self.login = login
        self.display_name = display_name or login
        self.authorized = bool(authorized)
        self.method = method
        self.reason = reason
        self.domain = domain      # shown in the header's profile menu

    def __repr__(self):
        return (f"AuthResult(login={self.login!r}, authorized={self.authorized}, "
                f"method={self.method!r}, reason={self.reason!r})")


class AuthError(Exception):
    """Raised inside this module only; callers get an AuthResult instead."""


# -- dev override ----------------------------------------------------------

def _dev_user():
    """SGDESK_DEV_USER, or the OS user when SGDESK_DEV=1. Empty otherwise."""
    user = os.environ.get("SGDESK_DEV_USER", "").strip()
    if user:
        return user
    if os.environ.get("SGDESK_DEV") == "1":
        return getpass.getuser()
    return ""


# -- ldap plumbing ---------------------------------------------------------

def _tls_object(cfg):
    """TLS settings for LDAPS or StartTLS, honouring validate_certificate."""
    from ldap3 import Tls

    validate = ssl.CERT_REQUIRED if cfg.validate_certificate else ssl.CERT_NONE
    kwargs = {"validate": validate}
    if cfg.ca_certs_file:
        kwargs["ca_certs_file"] = cfg.ca_certs_file
    return Tls(**kwargs)


def bind(cfg, username, password):
    """Bind to the DC as username. Returns a live ldap3 Connection.

    The bind itself is the password check: AD rejects a wrong password with
    invalidCredentials. Transport is always encrypted — LDAPS on 636, or
    StartTLS before the bind on 389 — so the password never crosses the wire
    in the clear.
    """
    try:
        from ldap3 import Server, Connection, SIMPLE
    except ImportError as e:
        raise AuthError(
            "the ldap3 package is required for password login "
            "(pip install ldap3)"
        ) from e
    from ldap3.core.exceptions import LDAPException

    if not cfg.server_address:
        raise AuthError("no domain controller configured (host/server_ip)")

    server = Server(
        cfg.server_address,
        port=cfg.port,
        use_ssl=cfg.use_ssl,
        tls=_tls_object(cfg),
        get_info="ALL",
        connect_timeout=cfg.timeout,
    )
    try:
        conn = Connection(
            server,
            user=cfg.upn(username),
            password=password,
            authentication=SIMPLE,
            auto_bind=False,
            raise_exceptions=False,
            receive_timeout=cfg.timeout,
        )
        if not cfg.use_ssl:
            # Cleartext port: upgrade before sending the password, never after.
            if not conn.start_tls():
                raise AuthError("could not start TLS on the domain controller")
        if not conn.bind():
            detail = (conn.result or {}).get("description", "invalid credentials")
            raise AuthError(f"login failed: {detail}")
    except AuthError:
        raise
    except LDAPException as e:
        raise AuthError(f"could not reach {cfg.server_address}: {e}") from e
    except Exception as e:
        raise AuthError(f"could not reach {cfg.server_address}: {e}") from e
    return conn


def authenticate_password(username, password, cfg=None, connect=bind):
    """Bind as username/password and check the group. Returns an AuthResult.

    connect is injectable so tests can hand in a fake connection factory
    without an ldap3 install or a domain controller.
    """
    cfg = cfg or auth_config.load()
    username = cfg.normalize_username(username)
    if not username or not password:
        return AuthResult(login=username, method=DENIED,
                          reason="a username and password are required")

    conn = None
    try:
        conn = connect(cfg, username, password)
    except AuthError as e:
        log.info("bind rejected for %s", cfg.down_level(username))
        return AuthResult(login=username, method=DENIED, reason=str(e))
    finally:
        # The password argument goes out of scope here; nothing above stored it.
        password = None

    try:
        member = group_check.in_group_ldap(conn, username, cfg)
        display = group_check.display_name_ldap(conn, username, cfg) or username
    finally:
        try:
            conn.unbind()
        except Exception:
            pass

    if member is True:
        log.info("authenticated %s by bind", cfg.down_level(username))
        return AuthResult(login=username, display_name=display,
                          authorized=True, method=BIND, domain=cfg.domain)
    if member is False:
        return AuthResult(login=username, display_name=display, method=DENIED,
                          reason=f"{username} is not a member of "
                                 f"{cfg.required_group}")
    return AuthResult(login=username, display_name=display, method=DENIED,
                      reason="could not confirm group membership in the directory")


# -- sso path --------------------------------------------------------------

def authenticate_system_login(cfg=None, username=None):
    """Check the OS user's group membership without asking for a password.

    Returns an AuthResult; an unauthorized one means the caller should fall
    back to the prompt (reason says why the trust path did not hold).
    """
    cfg = cfg or auth_config.load()
    username = cfg.normalize_username(username or getpass.getuser())
    if not username:
        return AuthResult(method=DENIED, reason="no OS user to trust")

    if cfg.system_login_check == "ldap":
        member = _system_login_ldap(cfg, username)
    else:
        member = group_check.in_group_local(username, cfg.required_group)

    if member is True:
        log.info("authenticated %s by system login", cfg.down_level(username))
        return AuthResult(login=username, display_name=username,
                          authorized=True, method=SSO, domain=cfg.domain)
    if member is False:
        return AuthResult(login=username, method=DENIED,
                          reason=f"{username} is not a member of "
                                 f"{cfg.required_group}")
    return AuthResult(login=username, method=DENIED,
                      reason="this machine could not resolve the domain groups "
                             f"for {username}")


def _system_login_ldap(cfg, username):
    """Group check over an unauthenticated directory read. Tri-state."""
    try:
        from ldap3 import Server, Connection, ANONYMOUS
        from ldap3.core.exceptions import LDAPException
    except ImportError:
        log.warning("system_login_check is 'ldap' but ldap3 is not installed")
        return None
    try:
        server = Server(cfg.server_address, port=cfg.port, use_ssl=cfg.use_ssl,
                        tls=_tls_object(cfg), get_info="ALL",
                        connect_timeout=cfg.timeout)
        conn = Connection(server, authentication=ANONYMOUS, auto_bind=True,
                          receive_timeout=cfg.timeout)
    except (LDAPException, Exception) as e:
        log.warning("anonymous directory lookup failed: %s", e)
        return None
    try:
        return group_check.in_group_ldap(conn, username, cfg)
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


# -- entry point -----------------------------------------------------------

def authenticate(cfg=None, prompt=None, connect=bind):
    """Resolve the session's login. Never raises.

    prompt is a callable taking (cfg, message) and returning
    (username, password) or None when the artist cancels. Pass
    login_dialog.prompt from the UI; leave it None for headless callers, which
    then get SSO-or-denial with no dialog.
    """
    dev = _dev_user()
    if dev:
        log.info("auth bypassed by dev override, running as %s", dev)
        return AuthResult(login=dev, display_name=dev, authorized=True,
                          method=DEV)

    cfg = cfg or auth_config.load()
    if not cfg.enabled:
        user = getpass.getuser()
        log.info("auth disabled in config, running as %s", user)
        return AuthResult(login=user, display_name=user, authorized=True,
                          method=DISABLED)

    result = AuthResult(method=DENIED, reason="authentication is not configured")
    if cfg.trust_system_login:
        result = authenticate_system_login(cfg)
        if result.authorized:
            return result
        log.info("system login trust did not hold: %s", result.reason)

    if not cfg.fallback_to_prompt or prompt is None:
        return result

    problems = cfg.validate()
    if problems:
        log.error("auth config is incomplete: %s", "; ".join(problems))
        return AuthResult(method=DENIED,
                          reason="the Active Directory settings are incomplete: "
                                 + "; ".join(problems))

    message = ""
    for attempt in range(MAX_ATTEMPTS):
        creds = prompt(cfg, message)
        if not creds:
            return AuthResult(method=DENIED, reason="login cancelled")
        username, password = creds
        result = authenticate_password(username, password, cfg=cfg,
                                       connect=connect)
        password = None
        if result.authorized:
            return result
        message = result.reason
        log.info("login attempt %d/%d failed: %s", attempt + 1, MAX_ATTEMPTS,
                 result.reason)

    return AuthResult(method=DENIED,
                      reason=f"{MAX_ATTEMPTS} failed login attempts")
