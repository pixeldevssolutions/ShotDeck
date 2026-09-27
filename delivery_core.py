"""
delivery_core.py — CLIENT delivery engine
==========================================
Single source of truth for CLIENT deliveries. Imported by:

  * delivery_config_designer.py   (producer GUI — live preview uses this engine)
  * sg_delivery_plugin.py          (auto delivery on Shot status change)
  * Flow's package_service.py      (producer delivery from the Flow launcher)

Copied from vfx-ingest-pipeline/tools/delivery_core.py. Flow's copy adds two
things, both backwards compatible with existing configs: `dry_run` on
run_delivery(), and the per-rule `match_version` key. Port them back rather
than letting the two copies drift.

NOT related to freelancer/task packaging (task_packaging_config.yaml). That is a
separate system that keeps our internal structure unchanged. This one REMAPS our
fixed internal structure onto whatever naming + folder layout the client wants.

Config schema (produced by delivery_config_designer.py):

    client: "Acme Studios"
    client_code: "ACME"
    token_transforms:                 # how internal tokens render client-side
      Seq:  { strip_prefix: "SEQ", add_prefix: "seq" }   # SEQ001 -> seq001
      Shot: { strip_prefix: "SH" }                         # SH0010 -> 0010
    placeholder_folders:              # empty folders the client spec demands
      - "<Shot>/for_review"
      - "_aspera"
    keep_empty: false                 # write .keep so empties survive transfer
    rules:
      plates:
        source_paths: ["elements/plates"]
        dest_folder:  "<Shot>/plates"     # NO <Seq> -> no seq folder at all
        extensions:   [".exr", ".dpx"]
        naming:       "<ClientCode>_<Shot>_plates_v<Version>.<Frame>.<ext>"
        match_version: false          # true: only files whose path has v<Version>

Standalone test (no ShotGrid):
    python delivery_core.py acme_delivery_config.yaml /path/to/shot /path/to/out \
        --seq SEQ001 --shot SH0010 --version 003

    pip install pyyaml
"""

from __future__ import annotations

import csv
import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

FRAME_RE = re.compile(r"^(.+?)[._](\d+)\.(\w+)$")   # name<digits>.ext
TOKEN_RE = re.compile(r"<(\w+)>")
ZONE_ID = "Zone.Identifier"


# ── transform engine ─────────────────────────────────────────────────────────
def apply_transform(value: Any, t: dict) -> str:
    """SEQ001 -> 001 / seq001 / 0001. Identical logic to the designer preview."""
    s = str(value)
    sp = t.get("strip_prefix", "")
    if sp and s.upper().startswith(sp.upper()):
        s = s[len(sp):]
    pad = int(t.get("pad", 0) or 0)
    if pad and s.isdigit():
        s = s.zfill(pad)
    case = t.get("case", "keep")
    if case == "upper":
        s = s.upper()
    elif case == "lower":
        s = s.lower()
    elif case == "title":
        s = s.title()
    return t.get("add_prefix", "") + s


def render_template(template: str, context: dict, file_tokens: dict,
                    transforms: dict) -> str:
    """Substitute <Token> in a dest_folder or naming string.
    Resolution: file tokens (Frame/ext) -> shot context -> verbatim if unknown.
    """
    def resolve(tok: str) -> str:
        if tok in file_tokens and file_tokens[tok] is not None:
            val = file_tokens[tok]
        elif tok in context and context[tok] is not None:
            val = context[tok]
        else:
            return "<%s>" % tok
        if tok in transforms:
            val = apply_transform(val, transforms[tok])
        return str(val)
    return TOKEN_RE.sub(lambda m: resolve(m.group(1)), template)


def file_tokens(fp: Path) -> dict:
    ext = fp.suffix.lstrip(".").lower()
    m = FRAME_RE.match(fp.name)
    return {"ext": ext, "Frame": m.group(2) if m else None}


def load_config(path: str | Path) -> dict:
    import yaml
    p = Path(path)
    with open(p, "r", encoding="utf-8") as fh:
        if p.suffix.lower() == ".json":
            import json
            return json.load(fh)
        return yaml.safe_load(fh)


# Config search paths — checked in order, first match wins.
# Override at startup by modifying this list or by setting env var
# VFX_DELIVERY_CONFIG_DIR to a colon-separated list of extra directories.
_CONFIG_SEARCH = [
    # 1. project-specific  e.g. /jobs/UAT/config/lola_delivery_config.yaml
    "/jobs/{project}/config/{project}_delivery_config.yaml",
    "/jobs/{project}/config/delivery_config.yaml",
    # 2. pipeline per-project named file (producer drops here for smaller projects)
    "/software/pipeline/vfx-ingest-pipeline/config/{project}_delivery_config.yaml",
    # 3. studio canonical default — always the final fallback
    "/software/pipeline/vfx-ingest-pipeline/config/default_package_config.yaml",
]


def find_config(project: str = "", extra_dirs: list | None = None,
                log=None) -> tuple[dict | None, str]:
    """Locate and load a delivery config using the standard priority chain.

    Priority (first match wins):
      1. project-specific  →  /jobs/<project>/_config/delivery_config.yaml
      2. pipeline per-project  →  …/config/<project>_delivery_config.yaml
      3. studio global default  →  …/config/global_delivery_config.yaml

    Returns (config_dict, path_used) or (None, "") if nothing found.
    The caller can also pass `extra_dirs` (prepended, highest priority) for
    local overrides, e.g. from a freelancer's Browse selection.
    """
    import os
    _log = log or (lambda msg, lvl="info": None)

    # build the candidate list
    candidates: list[Path] = []

    # 0. extra_dirs — highest priority (e.g. freelancer UI Browse)
    for d in (extra_dirs or []):
        for name in (
            f"{project}_delivery_config.yaml" if project else None,
            "delivery_config.yaml",
        ):
            if name:
                candidates.append(Path(d) / name)

    # 1-3. standard chain
    env_extra = os.environ.get("VFX_DELIVERY_CONFIG_DIR", "")
    env_dirs = [d for d in env_extra.split(":") if d]
    search = _CONFIG_SEARCH.copy()
    for d in env_dirs:
        search.insert(0, str(Path(d) / "{project}_delivery_config.yaml"))
        search.insert(0, str(Path(d) / "delivery_config.yaml"))

    for tmpl in search:
        try:
            p = Path(tmpl.format(project=project) if project else tmpl)
        except KeyError:
            p = Path(tmpl)
        candidates.append(p)

    for p in candidates:
        if p.is_file():
            _log(f"delivery config: {p} (project={project or 'any'})", "info")
            try:
                return load_config(p), str(p)
            except Exception as e:
                _log(f"failed to read {p}: {e}", "warn")
                continue

    tried = [str(c) for c in candidates]
    _log(f"no delivery config found for project={project!r}. tried: {tried}", "warn")
    return None, ""


# ── result types ─────────────────────────────────────────────────────────────
@dataclass
class DeliveryEntry:
    rule: str
    original: str
    package: str
    rel_dest: str
    size: int
    md5: str
    source: str = ""


@dataclass
class DeliveryResult:
    entries: list = field(default_factory=list)
    placeholders: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and (bool(self.entries) or bool(self.placeholders))


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ── core routine ─────────────────────────────────────────────────────────────
def run_delivery(
    config: dict,
    work_dir: Path | str,
    output_root: Path | str,
    context: dict,
    rules_to_run: Optional[list] = None,
    log: Callable[[str, str], None] = lambda m, l="info": None,
    progress: Callable[[int], None] = lambda p: None,
    write_manifest: bool = True,
    dry_run: bool = False,
) -> DeliveryResult:
    """Build a client delivery of `work_dir` into `output_root` per `config`.

    dry_run: work out every entry without touching disk. Entries carry the
    source size and an empty md5.

    context: raw token values for THIS shot, e.g.
        {"Seq": "SEQ001", "Shot": "SH0010", "Version": "003", "Project": "acme"}
      ClientCode is filled from config["client_code"] if absent.
    """
    work_dir = Path(work_dir)
    output_root = Path(output_root)
    transforms = config.get("token_transforms", {}) or {}
    rules = config.get("rules", {}) or {}
    context = dict(context)
    context.setdefault("ClientCode", config.get("client_code", "XX"))

    # inject <Date> = now if not already in context
    from datetime import datetime as _dt
    context.setdefault("Date", _dt.now().strftime("%Y_%m_%d_%H%M"))

    # pull vendor/plate from config context if not already set
    cfg_ctx = config.get("context", {}) or {}
    context.setdefault("Vendor", cfg_ctx.get("vendor", "vendor"))
    context.setdefault("Plate", cfg_ctx.get("plate", ""))
    context.setdefault("Project", cfg_ctx.get("project", ""))

    # resolve <GlobalPackage> and <ShotPackage> composite tokens
    # these let dest_folder reference the two-level naming as single tokens
    gp_tmpl = config.get("global_package_naming", "")
    sp_tmpl = config.get("shot_package_naming", "")
    if gp_tmpl:
        context["GlobalPackage"] = render_template(gp_tmpl, context, {}, transforms)
    if sp_tmpl:
        context["ShotPackage"] = render_template(sp_tmpl, context, {}, transforms)

    result = DeliveryResult()
    names = list(rules.keys()) if rules_to_run is None else [
        r for r in rules_to_run if r in rules]
    if rules_to_run:
        for r in rules_to_run:
            if r not in rules:
                result.skipped.append((r, "no such rule in config"))
                log(f"skip {r}: not defined in config", "warn")

    total = max(len(names), 1)
    # Task for shot_package_naming comes from rule-level "task" field
    # (short code like trk/prep/roto/cmp), not the rule name
    for i, rule_name in enumerate(names):
        rule = rules[rule_name]
        context["Task"] = rule.get("task", rule_name)  # explicit task code if set
        # recompute ShotPackage here so <Task> resolves to this rule's task code
        if sp_tmpl:
            context["ShotPackage"] = render_template(sp_tmpl, context, {}, transforms)
        naming = rule.get("naming", "")
        exts = {e.lower() for e in rule.get("extensions", [])}
        dest_tmpl = rule.get("dest_folder", rule_name)
        preserve = bool(rule.get("preserve_subdirs", False))
        pass_map = rule.get("pass_map", {}) or {}
        # A shot folder holds every version ever rendered; without this a rule
        # would sweep v001..v005 into one delivery named after the approved one.
        version_tag = ("v" + str(context.get("Version", "")).lstrip("vV")).lower() \
            if rule.get("match_version") else ""
        # if preserving subfolders and the producer didn't place <Pass> explicitly,
        # append it so the pass tree (beauty/, diffuse/, AO/ ...) is kept intact
        eff_tmpl = dest_tmpl
        if preserve and "<Pass>" not in eff_tmpl:
            eff_tmpl = (eff_tmpl + "/<Pass>") if eff_tmpl else "<Pass>"

        copied = 0
        for src_rel in rule.get("source_paths", []):
            src_dir = work_dir / src_rel
            if not src_dir.is_dir():
                result.skipped.append((rule_name, f"missing {src_rel}"))
                log(f"skip {rule_name}: {src_dir} not found", "warn")
                continue
            for fp in sorted(p for p in src_dir.rglob("*") if p.is_file()):
                if ZONE_ID in fp.name:
                    continue
                if exts and fp.suffix.lower() not in exts:
                    continue
                if version_tag and not re.search(
                        r"(?<![0-9a-z])%s(?![0-9])" % re.escape(version_tag),
                        fp.relative_to(src_dir).as_posix().lower()):
                    continue
                ft = file_tokens(fp)
                # <Pass> = the file's subfolder(s) relative to the source dir
                rel_dir = fp.parent.relative_to(src_dir)
                pass_val = "" if str(rel_dir) in (".", "") else str(rel_dir).replace("\\", "/")
                if pass_val and pass_map:                       # rename passes per-segment
                    pass_val = "/".join(pass_map.get(s, s) for s in pass_val.split("/"))
                ft["Pass"] = pass_val

                dest_rel = render_template(eff_tmpl, context, ft, transforms)
                dest_rel = re.sub(r"/+", "/", dest_rel).strip("/")   # tidy empty <Pass>
                out_dir = output_root / dest_rel

                if "<Frame>" in naming and ft["Frame"] is None:
                    new_name = fp.name
                    log(f"  {fp.name}: no frame # — kept original name", "warn")
                else:
                    new_name = render_template(naming, context, ft, transforms) \
                        if naming else fp.name
                dest = out_dir / new_name
                if dry_run:
                    size, md5 = fp.stat().st_size, ""
                else:
                    try:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(str(fp), str(dest))   # NFS-ACL safe
                    except Exception as exc:
                        result.errors.append((str(fp), str(exc)))
                        log(f"  ERROR {fp.name}: {exc}", "error")
                        continue
                    size, md5 = dest.stat().st_size, _md5(dest)
                result.entries.append(DeliveryEntry(
                    rule=rule_name, original=fp.name, package=new_name,
                    rel_dest=str(Path(dest_rel) / new_name).replace("\\", "/"),
                    size=size, md5=md5, source=str(fp)))
                copied += 1
                log(f"  {fp.name}  ->  {dest_rel}/{new_name}", "info")
        log(f"{rule_name}: {copied} file(s)", "info")
        progress(int((i + 1) / total * 85))

    # placeholder folders — created even if empty (client spec compliance)
    for tmpl in (config.get("placeholder_folders") or []):
        rel = render_template(tmpl, context, {}, transforms)
        if not dry_run:
            d = output_root / rel
            d.mkdir(parents=True, exist_ok=True)
            if config.get("keep_empty"):
                (d / ".keep").touch()
        result.placeholders.append(rel)
        log(f"placeholder folder: {rel}", "info")
    progress(92)

    if write_manifest and result.entries and not dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
        man = output_root / "manifest.csv"
        chk = output_root / "checksums.md5"
        with open(man, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=[
                "rule", "original", "package", "rel_dest", "size", "md5"],
                extrasaction="ignore")
            w.writeheader()
            for e in result.entries:
                w.writerow(e.__dict__)
        with open(chk, "w", encoding="utf-8") as fh:
            for e in result.entries:
                fh.write(f"{e.md5}  {e.rel_dest}\n")
        log(f"manifest  -> {man}", "success")
        log(f"checksums -> {chk}", "success")

    progress(100)
    log(f"done: {len(result.entries)} files, {len(result.placeholders)} placeholder "
        f"folder(s), {len(result.skipped)} skipped, {len(result.errors)} errors",
        "success" if result.ok else "warn")
    return result


# ── standalone CLI for testing ───────────────────────────────────────────────
def _main():
    import argparse
    ap = argparse.ArgumentParser(description="Run a client delivery (standalone test)")
    ap.add_argument("config")
    ap.add_argument("work_dir")
    ap.add_argument("output_root")
    ap.add_argument("--seq", default="")
    ap.add_argument("--shot", default="")
    ap.add_argument("--version", default="001")
    ap.add_argument("--project", default="")
    ap.add_argument("--rules", nargs="*", default=None)
    a = ap.parse_args()
    cfg = load_config(a.config)
    ctx = {"Seq": a.seq, "Shot": a.shot, "Version": a.version, "Project": a.project}
    run_delivery(cfg, a.work_dir, a.output_root, ctx, rules_to_run=a.rules,
                 log=lambda m, l="info": print(f"[{l}] {m}"))


if __name__ == "__main__":
    _main()