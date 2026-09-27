"""USD assembly and publish, from inside Maya and Houdini.

Shots and assets are built the same way: one immutable layer per department
publish, a pointer per department naming the current one, one stage composing
the departments. Plain file paths, no resolver, no symlinks.

    Asset  <asset root>/usd/
        tree.usda               defaultPrim </tree>, kind=component,
                                payload -> payload.usda</tree>
        payload.usda            sublayers the department pointers
        model/model.usda        pointer -> ./tree_model_v003.usd
        model/tree_model_v003.usd

    Shot   <shot root>/usd/
        shot.usda               sublayers the department pointers, strongest
                                first, then assets.usda
        assets.usda             /assets/<asset> references, generated from the
                                shot's asset breakdown in ShotGrid
        anim/anim.usda          pointer -> ./AD1030_anim_v004.usd
        anim/AD1030_anim_v004.usd

Publishing exports the layer, checks it, then rewrites the pointer and the
stage -- anything opening the stage sees the new layer. Rolling back is
pointing the pointer at an older file.

Every generated layer is a few lines of .usda text, written here as text, so
this module needs no `pxr` and is tested outside any DCC. `pxr` is used only
when present, to check a fresh export (see check_layer). The export and the
loading are host code: the adapters' export_usd() and load_usd_stage().
"""

import os
import re

from . import context, publish, shotgrid

# Strongest first. A step not listed sits below the known ones, alphabetically.
# ponytail: one order per studio; per-show order via these variables if a show
# ever needs a different stack.
DEPARTMENTS = {
    "Shot": [d for d in os.environ.get(
        "FLOW_USD_DEPARTMENTS", "lighting,fx,cfx,anim,layout").split(",") if d],
    "Asset": [d for d in os.environ.get(
        "FLOW_USD_ASSET_DEPARTMENTS", "lookdev,rig,model").split(",") if d],
}

SHOT_STAGE = "shot.usda"
PAYLOAD = "payload.usda"
ASSETS_LAYER = "assets.usda"
LAYER_EXT = ".usd"          # binary crate; text only for the generated layers
LAYER_RE = re.compile(r"_v(\d+)\.usd[ac]?$", re.IGNORECASE)
KINDS = ("Shot", "Asset")

# Exported by Flow at launch, e.g. /jobs/uat6/assets/{asset_type}/{asset}.
ASSET_TEMPLATE_VAR = "FLOW_ASSET_PATH_TEMPLATE"


class Result(object):
    def __init__(self, layer, version, stage, published_file=None,
                 registration_error=None):
        self.layer = layer
        self.version = version
        self.stage = stage
        self.published_file = published_file
        self.registration_error = registration_error

    def summary(self):
        lines = ["Published USD layer v{0:03d}".format(self.version), "",
                 "Layer       {0}".format(self.layer),
                 "Stage       {0}".format(self.stage)]
        if self.published_file:
            lines.append("ShotGrid    PublishedFile {0}".format(
                self.published_file.get("id")))
        else:
            lines += ["ShotGrid    NOT registered", "",
                      str(self.registration_error)]
        return "\n".join(lines)


# -- names and places -------------------------------------------------------

def prim_name(name):
    """A valid USD prim name: letters, digits, _; not starting with a digit."""
    clean = re.sub(r"[^A-Za-z0-9_]", "_", name or "") or "_"
    return "_" + clean if clean[0].isdigit() else clean


def usd_root(ctx=None):
    ctx = ctx or context.get()
    root = (ctx.entity_root or "").rstrip("/")
    return root + "/usd" if root else None


def department(ctx=None):
    ctx = ctx or context.get()
    return (ctx.step or "").strip().lower()


def stage_name(kind, entity_name):
    return SHOT_STAGE if kind == "Shot" else prim_name(entity_name) + ".usda"


def stage_path(ctx=None):
    ctx = ctx or context.get()
    root = usd_root(ctx)
    return root + "/" + stage_name(ctx.entity_type, ctx.entity_name) \
        if root else None


def asset_stage_path(asset, asset_type, template=None):
    """Where an asset's stage lives, from Flow's own path template."""
    template = template or os.environ.get(ASSET_TEMPLATE_VAR, "")
    if not template:
        return None
    root = template.format(asset=asset, asset_type=asset_type or "",
                           entity=asset).rstrip("/")
    return "{0}/usd/{1}".format(root, stage_name("Asset", asset))


def layer_versions(dept_dir):
    """Published layer versions in a department folder, ascending."""
    if not os.path.isdir(dept_dir):
        return []
    found = [LAYER_RE.search(n) for n in os.listdir(dept_dir)]
    return sorted(set(int(m.group(1)) for m in found if m))


def next_layer_path(ctx=None):
    """(path, version) for the next department layer. Raises PublishError."""
    ctx = publish.validate(ctx)        # also refuses a task with no step
    if ctx.entity_type not in KINDS:
        raise publish.PublishError(
            "USD publishing is for shots and assets; this task is on a {0}."
            .format(ctx.entity_type or "task with no entity"))
    dept = department(ctx)
    dept_dir = usd_root(ctx) + "/" + dept
    existing = layer_versions(dept_dir)
    version = (existing[-1] + 1) if existing else 1
    name = "{0}_{1}_v{2:03d}{3}".format(prim_name(ctx.entity_name), dept,
                                        version, LAYER_EXT)
    return dept_dir + "/" + name, version


# -- generated layers --------------------------------------------------------

def _header(doc, extra=(), sublayers=()):
    lines = ["#usda 1.0", "(", '    doc = "{0}"'.format(doc)]
    lines += ["    " + e for e in extra]
    if sublayers:
        lines.append("    subLayers = [")
        lines.append(",\n".join("        @{0}@".format(s) for s in sublayers))
        lines.append("    ]")
    lines.append(")")
    return "\n".join(lines) + "\n"


def sublayer_text(sublayers, doc):
    """A .usda layer that only sublayers others."""
    return _header(doc, sublayers=sublayers)


def _write(path, text):
    """Readers see the old file or the new one, never half of one."""
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


def point_department(dept_dir, dept, layer_name):
    """Make <dept>/<dept>.usda sublayer `layer_name`."""
    return _write("{0}/{1}.usda".format(dept_dir, dept), sublayer_text(
        ["./" + layer_name],
        "Flow: current {0} layer. Rewritten on every {0} publish."
        .format(dept)))


def departments_on_disk(root, kind="Shot"):
    """Departments with a pointer layer, strongest first."""
    if not os.path.isdir(root):
        return []
    order = DEPARTMENTS.get(kind, [])
    present = [d for d in os.listdir(root)
               if os.path.isfile("{0}/{1}/{1}.usda".format(root, d))]
    known = [d for d in order if d in present]
    return known + sorted(d for d in present if d not in order)


def write_stage(root, kind, entity_name):
    """(Re)build the entity's stage from what has been published. Returns it."""
    pointers = ["./{0}/{0}.usda".format(d)
                for d in departments_on_disk(root, kind)]
    if kind == "Shot":
        if os.path.isfile(root + "/" + ASSETS_LAYER):
            pointers.append("./" + ASSETS_LAYER)      # weakest: departments win
        return _write(root + "/" + SHOT_STAGE, sublayer_text(
            pointers, "Flow: shot assembly. Rebuilt on every publish; do not "
            "edit by hand."))

    # An asset is referenced by shots, so it needs a single root prim and a
    # payload: a shot can then open without loading every asset's geometry.
    prim = prim_name(entity_name)
    _write(root + "/" + PAYLOAD, sublayer_text(
        pointers, "Flow: {0} departments. Rebuilt on every publish.".format(
            prim)))
    return _write(root + "/" + stage_name("Asset", entity_name), _header(
        "Flow: {0} asset. Rebuilt on every publish; do not edit by "
        "hand.".format(prim),
        extra=['defaultPrim = "{0}"'.format(prim)]) +
        '\ndef Xform "{0}" (\n    kind = "component"\n'
        '    prepend payload = @./{1}@</{0}>\n)\n{{\n}}\n'.format(prim, PAYLOAD))


def write_assets_layer(root, assets):
    """assets.usda: one /assets/<name> reference per (name, stage path).

    Returns the names left out because their stage has not been published.
    """
    body, missing, used = [], [], set()
    for name, path in assets:
        if not path or not os.path.isfile(path):
            missing.append(name)
            continue
        prim = prim_name(name)
        while prim in used:                     # same code, two asset types
            prim += "_"
        used.add(prim)
        body.append('    def "{0}" (\n        prepend references = @{1}@\n'
                    '    )\n    {{\n    }}\n'.format(prim, path))
    text = _header("Flow: shot asset breakdown from ShotGrid. Rebuilt on "
                   "load; do not edit by hand.") + \
        '\ndef Scope "assets"\n{\n' + "\n".join(body) + "}\n"
    _write(root + "/" + ASSETS_LAYER, text)
    return missing


def check_layer(path, kind, entity_name):
    """What is wrong with a fresh export, or "" -- only when pxr is here.

    Hosts that write USD ship pxr; outside them (tests, a bare Python) the
    check is skipped rather than failing the publish.
    """
    try:
        from pxr import Sdf
    except ImportError:
        return ""
    layer = Sdf.Layer.FindOrOpen(path)
    if layer is None:
        return "USD cannot open the exported layer."
    if not layer.rootPrims:
        return "The exported layer has no prims -- was anything selected?"
    prim = prim_name(entity_name)
    if kind == "Asset" and not layer.GetPrimAtPath("/" + prim):
        return ("An asset layer must put everything under /{0}; this one "
                "has {1}.".format(prim, ", ".join(
                    "/" + p.name for p in layer.rootPrims)))
    return ""


# -- ShotGrid breakdown -------------------------------------------------------

def shot_assets(ctx, sg=None):
    """[(asset code, stage path)] for the shot's Assets field in ShotGrid."""
    sg = sg or shotgrid.connect()
    shot = sg.find_one("Shot", [["id", "is", ctx.entity_id]], ["assets"])
    ids = [a["id"] for a in (shot or {}).get("assets") or []]
    if not ids:
        return []
    rows = sg.find("Asset", [["id", "in", ids]], ["code", "sg_asset_type"])
    return [(r["code"], asset_stage_path(r["code"], r.get("sg_asset_type")))
            for r in sorted(rows, key=lambda r: r["code"])]


def refresh_shot_assets(ctx=None, sg=None):
    """Rebuild assets.usda and shot.usda. Returns the missing asset names."""
    ctx = ctx or context.get()
    root = usd_root(ctx)
    missing = write_assets_layer(root, shot_assets(ctx, sg))
    write_stage(root, "Shot", ctx.entity_name)
    return missing


# -- the actions ---------------------------------------------------------------

def publish_layer(adapter, ctx=None, description=""):
    """Export this department's layer and put it in the stage. Returns Result.

    Raises PublishError for anything that fails before the stage changes. A
    layer that fails the check is deleted, so its version number is reused.
    Once the stage has changed, a ShotGrid failure is reported on the Result.
    """
    ctx = ctx or context.get()
    path, version = next_layer_path(ctx)
    dept_dir = os.path.dirname(path)
    if not os.path.isdir(dept_dir):
        os.makedirs(dept_dir)

    try:
        adapter.export_usd(path, prim_name(ctx.entity_name)
                           if ctx.entity_type == "Asset" else None)
    except Exception as e:
        raise publish.PublishError(
            "USD export failed:\n{0}\n\n{1}".format(path, e))
    problem = "" if os.path.isfile(path) and os.path.getsize(path) else \
        "The export reported success but wrote nothing."
    problem = problem or check_layer(path, ctx.entity_type, ctx.entity_name)
    if problem:
        if os.path.isfile(path):
            os.remove(path)
        raise publish.PublishError("{0}\n\nNothing was published.".format(
            problem))

    point_department(dept_dir, department(ctx), os.path.basename(path))
    stage = write_stage(usd_root(ctx), ctx.entity_type, ctx.entity_name)

    published_file, error = None, None
    try:
        published_file = shotgrid.register(path, ctx, description)
    except Exception as e:
        error = e
    return Result(path, version, stage, published_file, error)


def load_stage(adapter, ctx=None):
    """Open the entity's stage in the host. Returns (path, note).

    A shot's asset breakdown is refreshed from ShotGrid first; offline, the
    last assets.usda stays and the note says so.
    """
    ctx = ctx or context.get()
    root = usd_root(ctx)
    if not root or ctx.entity_type not in KINDS:
        raise publish.PublishError(
            "This session was launched without a shot or asset, so there is "
            "no USD stage to load.")
    note = ""
    if ctx.entity_type == "Shot":
        try:
            missing = refresh_shot_assets(ctx)
            if missing:
                note = "Not published yet, left out: " + ", ".join(missing)
        except Exception as e:
            note = "Asset breakdown not refreshed ({0}).".format(e)
    path = stage_path(ctx)
    if not os.path.isfile(path):
        write_stage(root, ctx.entity_type, ctx.entity_name)
    adapter.load_usd_stage(path)
    return path, note


# -- menu actions (bound onto adapters that implement export_usd) ----------

def action_publish_usd(adapter):
    try:
        path, version = next_layer_path()
    except publish.PublishError as e:
        adapter.message(str(e))
        return None
    if not adapter.confirm(
            "Publish {0} USD layer v{1:03d}?\n\n{2}\n\nThe stage will use it "
            "straight away.".format(department(), version, path)):
        return None
    try:
        result = publish_layer(adapter)
    except publish.PublishError as e:
        adapter.message(str(e))
        return None
    adapter.message(result.summary())
    return result


def action_load_usd_stage(adapter):
    try:
        path, note = load_stage(adapter)
    except Exception as e:
        adapter.message("Could not load the USD stage: {0}".format(e))
        return None
    adapter.message("Loaded {0}{1}".format(path, "\n\n" + note if note else ""))
    return path


def action_open_usd_folder(adapter):
    from .adapters import common
    return common._open(adapter, usd_root(), "USD")
