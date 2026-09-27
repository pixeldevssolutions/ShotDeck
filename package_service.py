"""Client delivery from Flow: approved versions in, a checked package out.

The engine is delivery_core, the same one the producer's Delivery Designer
previews against and the event daemon's sg_shot_delivery plugin runs, so a
config designed there ships the same way from here. What this module adds is
the part the daemon path lacks:

    approval   only the newest approved Version per shot is offered
    check      a dry run is validated before a single byte is copied --
               unresolved <Tokens>, two sources renaming onto one file,
               empty files, nothing to deliver
    staging    the package is built in <shot>.partial and renamed into the
               outbox only after the copied files pass the same check, so the
               client-facing folder is either complete or absent

No Qt here; ui/package_dialog.py draws it.
"""

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import applog
import config
import delivery_core
import paths

log = applog.get()

VERSION_RE = re.compile(r"v(\d+)", re.IGNORECASE)


class DeliveryError(RuntimeError):
    pass


@dataclass
class ShotDelivery:
    """One shot's delivery: where from, where to, and the token values."""
    version: dict
    work_dir: str
    output_root: Path
    context: dict

    @property
    def label(self):
        return f"{self.context['Seq']}/{self.context['Shot']} " \
               f"({self.version.get('code', '')})"


@dataclass
class Outcome:
    shot: ShotDelivery
    result: delivery_core.DeliveryResult = None
    problems: list = field(default_factory=list)
    delivered: bool = False
    log: list = field(default_factory=list)


def version_number(code):
    """'SH010_comp_v003' -> '003'. The last v### wins; '001' if none."""
    found = VERSION_RE.findall(code or "")
    return found[-1].zfill(3) if found else "001"


def project_code(project):
    # Same fallback as context.build(), so the outbox folder matches /jobs.
    return project.get("tank_name") or project["name"].replace(" ", "_").lower()


def _safe(name):
    return "".join(c if c.isalnum() or c in "._-" else "_"
                   for c in (name or "")).strip("_")


def shot_delivery(project, version, outbox=None):
    """Build the ShotDelivery for an approved Version, or raise DeliveryError."""
    shot = version.get("entity") or {}
    seq = (version.get("entity.Shot.sg_sequence") or {}).get("name") or ""
    # paths.entity_root wants a task; the Version carries the same two fields.
    work_dir = paths.entity_root(project, {
        "entity": shot, "entity.Shot.sg_sequence": seq})
    if not work_dir:
        raise DeliveryError(
            f"{shot.get('name', 'shot')}: no folder on disk — the shot has "
            f"no sequence linked in ShotGrid")
    code = project_code(project)
    root = Path(outbox or config.DELIVERY_OUTBOX) / _safe(code) / _safe(seq) \
        / _safe(shot.get("name"))
    return ShotDelivery(
        version=version, work_dir=work_dir, output_root=root,
        context={"Project": code, "Seq": seq, "Shot": shot.get("name") or "",
                 "Version": version_number(version.get("code"))})


def problems(result):
    """Reasons this delivery must not reach the client. Empty means clean."""
    out = [f"{Path(fp).name}: {why}" for fp, why in result.errors]
    seen = {}
    for e in result.entries:
        if delivery_core.TOKEN_RE.search(e.rel_dest):
            out.append(f"{e.rel_dest}: unresolved token in the config's "
                       f"naming or dest_folder")
        clash = seen.get(e.rel_dest)
        if clash is not None and clash != e.source:
            out.append(f"{e.rel_dest}: {Path(clash).name} and "
                       f"{Path(e.source).name} both rename to this — add "
                       f"match_version or <Frame>/<Pass> to rule '{e.rule}'")
        seen[e.rel_dest] = e.source
        if e.size == 0:
            out.append(f"{e.rel_dest}: empty file")
    for rel in result.placeholders:
        if delivery_core.TOKEN_RE.search(rel):
            out.append(f"{rel}: unresolved token in placeholder_folders")
    if not result.entries and not result.placeholders:
        out.append("nothing matched any rule — the package would be empty")
    return out


def preview(cfg, shot):
    """Dry run and check. Touches nothing on disk."""
    outcome = Outcome(shot)
    outcome.result = delivery_core.run_delivery(
        cfg, shot.work_dir, shot.output_root, shot.context,
        log=lambda m, lvl="info": outcome.log.append(f"[{lvl}] {m}"),
        dry_run=True)
    outcome.problems = problems(outcome.result)
    return outcome


def deliver(cfg, shot, sg=None):
    """Check, build in staging, check again, publish into the outbox.

    Refuses to overwrite an existing delivery. A failed build leaves its
    .partial folder for inspection; the next attempt replaces it.
    """
    outcome = preview(cfg, shot)
    if outcome.problems:
        return outcome

    final = shot.output_root
    if final.exists():
        outcome.problems.append(
            f"{final} already exists — a delivery for this shot is already in "
            f"the outbox. Move it aside first; Flow will not overwrite it.")
        return outcome
    staging = final.with_name(final.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)      # our own leftover from a failed run

    outcome.log.append(f"[info] building in {staging}")
    outcome.result = delivery_core.run_delivery(
        cfg, shot.work_dir, staging, shot.context,
        log=lambda m, lvl="info": outcome.log.append(f"[{lvl}] {m}"))
    outcome.problems = problems(outcome.result)
    if outcome.problems:
        return outcome

    staging.rename(final)
    outcome.delivered = True
    outcome.log.append(f"[success] delivered to {final}")
    log.info("delivered %s -> %s (%d files)", shot.label, final,
             len(outcome.result.entries))

    shot_id = (shot.version.get("entity") or {}).get("id")
    if sg is not None and shot_id and config.DELIVERY_DONE_STATUS:
        # The files are already out; a status that will not stick is a
        # warning, never a failed delivery.
        try:
            sg.set_status("Shot", shot_id, config.DELIVERY_DONE_STATUS)
        except Exception as e:
            log.warning("delivered %s but could not set its status: %s",
                        shot.label, e)
            outcome.log.append(f"[warn] Shot status not updated: {e}")
    return outcome
