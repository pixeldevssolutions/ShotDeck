import os

import yaml

import config


def _load_yaml(path):
    if os.path.isfile(path):
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def build_env(project, software, extra=None):
    """os.environ + default.yml + <project>.yml (env/software sections) + extra."""
    env = dict(os.environ)

    default = _load_yaml(os.path.join(config.ENVS_DIR, "default.yml"))
    proj_key = project.get("tank_name") or project["name"].replace(" ", "_").lower()
    proj_cfg = _load_yaml(os.path.join(config.ENVS_DIR, f"{proj_key}.yml"))

    tokens = {
        "PROJECT_NAME": project["name"],
        "PROJECT_CODE": proj_key,
        "PROJECT_ID": str(project["id"]),
        "SOFTWARE": software["code"] if software else "",
    }

    def apply(section):
        for k, v in (section or {}).items():
            v = str(v).format(**tokens, **env)
            if k.endswith("+"):  # PATH+: prepend style
                k = k[:-1]
                env[k] = v + os.pathsep + env.get(k, "")
            else:
                env[k] = v

    apply(default.get("env"))
    apply(proj_cfg.get("env"))
    if software:
        sw_key = software["code"].lower()
        apply((default.get("software") or {}).get(sw_key))
        apply((proj_cfg.get("software") or {}).get(sw_key))
    apply(extra)

    env.update({f"SGDESK_{k}": v for k, v in tokens.items()})
    return env
