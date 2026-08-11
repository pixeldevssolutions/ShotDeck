"""Load and validate auth_config.yml.

Server details only: the file never carries a password. Everything here is a
plain dict lookup with a default, so a partial or hand-edited config still
yields a usable AuthConfig instead of a KeyError at launch time.

    SGDESK_AUTH_CONFIG=/path/to/auth_config.yml   overrides the bundled file
"""

import os

import yaml

import applog

log = applog.get()

CONFIG_PATH = os.environ.get(
    "SGDESK_AUTH_CONFIG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_config.yml"),
)

DEFAULTS = {
    "enabled": True,
    "domain": "",
    "netbios": "",
    "host": "",
    "server_ip": "",
    "port": 636,
    "use_ssl": True,
    "base_dn": "",
    "upn_template": "{username}",
    "required_group": "",
    "required_group_dn": "",
    "trust_system_login": True,
    "system_login_check": "local",
    "validate_certificate": True,
    "ca_certs_file": "",
    "timeout": 10,
    "fallback_to_prompt": True,
    "sg_login_mapping": "same",
}


class AuthConfig:
    """Typed view over the yaml, with the fields the auth modules ask for."""

    def __init__(self, data=None, path=None):
        merged = dict(DEFAULTS)
        merged.update(data or {})
        self._data = merged
        self.path = path

        self.enabled = bool(merged["enabled"])
        self.domain = str(merged["domain"] or "")
        self.netbios = str(merged["netbios"] or "")
        self.host = str(merged["host"] or "")
        self.server_ip = str(merged["server_ip"] or "")
        self.port = int(merged["port"] or 636)
        self.use_ssl = bool(merged["use_ssl"])
        self.base_dn = str(merged["base_dn"] or "")
        self.upn_template = str(merged["upn_template"] or "{username}")
        self.required_group = str(merged["required_group"] or "")
        self.required_group_dn = str(merged["required_group_dn"] or "")
        self.trust_system_login = bool(merged["trust_system_login"])
        self.system_login_check = str(merged["system_login_check"] or "local").lower()
        self.validate_certificate = bool(merged["validate_certificate"])
        self.ca_certs_file = str(merged["ca_certs_file"] or "")
        self.timeout = int(merged["timeout"] or 10)
        self.fallback_to_prompt = bool(merged["fallback_to_prompt"])
        self.sg_login_mapping = str(merged["sg_login_mapping"] or "same")

    # -- derived ----------------------------------------------------------
    @property
    def server_address(self):
        """Host to dial. The name is preferred so the TLS cert can match it."""
        return self.host or self.server_ip

    def upn(self, username):
        """username -> username@5and8.net (whatever upn_template says)."""
        return self.upn_template.format(username=username, domain=self.domain)

    def down_level(self, username):
        """username -> 5AND8\\username, for error messages and log lines."""
        return f"{self.netbios}\\{username}" if self.netbios else username

    def normalize_username(self, raw):
        """Accept 5AND8\\jitesh, jitesh@5and8.net or jitesh -> jitesh."""
        name = (raw or "").strip()
        if "\\" in name:
            name = name.rsplit("\\", 1)[1]
        if "@" in name:
            name = name.split("@", 1)[0]
        return name

    def validate(self):
        """Return a list of problems that would stop a bind from working.

        Non-fatal by itself: the caller decides. The SSO path only needs
        required_group, so a half-filled config can still authorize locally.
        """
        problems = []
        if not self.domain:
            problems.append("domain is not set")
        if not self.server_address:
            problems.append("neither host nor server_ip is set")
        if not self.base_dn:
            problems.append("base_dn is not set")
        if not self.required_group:
            problems.append("required_group is not set")
        if self.port == 389 and self.use_ssl:
            problems.append("use_ssl is true but port 389 is the cleartext port")
        return problems


def load(path=None):
    """Read the yaml at path (or CONFIG_PATH) and return an AuthConfig.

    A missing or unreadable file is not fatal here — it yields defaults with
    enabled left on, and validate() reports the empty fields. The caller fails
    closed on the resulting authorize attempt rather than on the read.
    """
    path = path or CONFIG_PATH
    data = {}
    try:
        if os.path.isfile(path):
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        else:
            log.warning("auth config not found at %s, using defaults", path)
    except Exception as e:
        log.error("could not read auth config %s: %s", path, e)
    return AuthConfig(data, path=path)
