"""Group membership checks for the required AD group.

Two independent answers to the same question, "is this user in ai-users":

    local  -- `id -nG <user>`, which on a domain-joined Rocky box lists the AD
              groups SSSD resolved at OS login. No password, no network call.
    ldap   -- a search against the directory over an already-bound connection.

Both return a tri-state: True (in group), False (definitely not in group) or
None (could not determine — not domain-joined, id missing, search failed).
None is never treated as authorized; the caller falls back or fails closed.
"""

import shutil
import subprocess

import applog

log = applog.get()

# AD's "member of, transitively" matching rule. Catches membership through a
# nested group, which a plain memberOf comparison misses.
LDAP_MATCHING_RULE_IN_CHAIN = "1.2.840.113556.1.4.1941"


def local_groups(username, timeout=5):
    """Group names for username per the OS, or None if they can't be listed."""
    if not username:
        return None
    if not shutil.which("id"):
        # Windows dev box, or a container without coreutils.
        return None
    try:
        out = subprocess.run(
            ["id", "-nG", username],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as e:
        log.warning("id -nG %s failed: %s", username, e)
        return None
    if out.returncode != 0:
        # "no such user" — the OS account is not a resolvable domain user.
        log.info("id -nG %s: %s", username, (out.stderr or "").strip())
        return None
    return out.stdout.split()


def in_group_local(username, group, timeout=5):
    """Tri-state membership from the OS group list.

    A resolvable user whose group list simply lacks the group is a real False:
    that is a denial, not an inconclusive check.
    """
    groups = local_groups(username, timeout=timeout)
    if groups is None:
        return None
    if not group:
        return None
    wanted = group.lower()
    return any(g.lower() == wanted for g in groups)


def _escape(value):
    """Escape an LDAP filter value (RFC 4515)."""
    out = []
    for ch in value or "":
        if ch in "\\*()\0":
            out.append("\\%02x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def in_group_ldap(conn, username, cfg):
    """Tri-state membership via the directory, using an existing connection.

    Tries the transitive matching rule first so nested groups count, then falls
    back to reading the user's own memberOf when the server rejects the rule.
    """
    if not cfg.base_dn:
        log.warning("no base_dn configured, cannot check group over ldap")
        return None

    user = _escape(username)
    group_dn = cfg.required_group_dn
    attrs = ["memberOf", "distinguishedName", "displayName", "sAMAccountName"]

    if group_dn:
        flt = (f"(&(objectClass=user)(sAMAccountName={user})"
               f"(memberOf:{LDAP_MATCHING_RULE_IN_CHAIN}:={_escape(group_dn)}))")
        try:
            conn.search(cfg.base_dn, flt, attributes=attrs)
            if conn.entries:
                return True
        except Exception as e:
            log.warning("nested group search failed, falling back: %s", e)

    # Fall back: read the user and compare memberOf ourselves. This also
    # distinguishes "user not found" (None) from "found, not a member" (False).
    flt = f"(&(objectClass=user)(sAMAccountName={user}))"
    try:
        conn.search(cfg.base_dn, flt, attributes=attrs)
    except Exception as e:
        log.error("ldap group search failed for %s: %s", username, e)
        return None
    if not conn.entries:
        log.info("no directory entry for %s under %s", username, cfg.base_dn)
        return None

    entry = conn.entries[0]
    member_of = [str(v) for v in (entry.memberOf.values if "memberOf" in entry else [])]
    if group_dn and any(dn.lower() == group_dn.lower() for dn in member_of):
        return True
    # Match on the CN alone when the configured DN's container is wrong — IT
    # still has to confirm CN=Users vs OU=Users (see the config comments).
    wanted = (cfg.required_group or "").lower()
    if wanted and any(dn.lower().startswith(f"cn={wanted},") for dn in member_of):
        log.warning("matched %s by CN; required_group_dn container may be wrong",
                    cfg.required_group)
        return True
    return False


def display_name_ldap(conn, username, cfg):
    """Best-effort displayName for the header chip. None when unavailable."""
    if not cfg.base_dn:
        return None
    try:
        conn.search(cfg.base_dn,
                    f"(&(objectClass=user)(sAMAccountName={_escape(username)}))",
                    attributes=["displayName"])
        if conn.entries and "displayName" in conn.entries[0]:
            return str(conn.entries[0].displayName) or None
    except Exception as e:
        log.warning("displayName lookup failed for %s: %s", username, e)
    return None
