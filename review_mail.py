"""Mail a task's leads when the artist sends it for review.

When a task is set to config.REVIEW_MAIL_STATUS ("prw") in Flow, everyone
listed in the task's lead field (sg_lead_reviewer, comma-separated emails)
gets a mail with the task and the artist's note. The SMTP side is the
pipeline's own services.mailer.send_email, imported from PIPELINE_ROOT the
way the ingest API does it, so there is one mailer and one set of SMTP_*
settings for the studio.

Only changes made in Flow send mail. A status set on the ShotGrid site does
not; that needs the event daemon.

FLOW_MAIL_OFF=1 turns it off; FLOW_MAIL_REDIRECT=<addr> sends every mail to
that one address instead, for testing.
"""

import html
import os
import re
import smtplib  # noqa: F401 -- the frozen app must bundle it for the mailer
import sys

import applog
import config

log = applog.get()


def recipients(value):
    """The addresses in a lead field: "a@x, b@x" -> ["a@x", "b@x"]."""
    return [a.strip() for a in re.split(r"[,;]", value or "") if "@" in a]


def message(task, artist, email, note, old, new):
    """(subject, html body) for one review request."""
    entity = (task.get("entity") or {}).get("name") or ""
    name = task.get("content") or ""
    project = (task.get("project") or {}).get("name") or ""
    step = (task.get("step") or {}).get("name") or ""
    subject = f"[{project}] {entity} {name} ready for review - {artist}"
    rows = [("Project", project), ("Shot / Asset", entity), ("Task", name),
            ("Step", step), ("Status", f"{old or '-'} -> {new}"),
            ("Artist", f"{artist} <{email}>" if email else artist)]
    body = (
        "<p><b>{0}</b> sent <b>{1}</b> for review.</p><table>{2}</table>"
        "<p><b>Note</b></p><p>{3}</p>"
        '<p><a href="{4}">Open the task in ShotGrid</a></p>').format(
            html.escape(artist), html.escape(f"{entity} {name}".strip()),
            "".join(f"<tr><td><b>{html.escape(k)}</b></td>"
                    f"<td>{html.escape(v)}</td></tr>" for k, v in rows if v),
            html.escape(note or "(no note)").replace("\n", "<br>"),
            config.entity_url("Task", task["id"]))
    return subject, body


def send(sg, task, artist, email, note, old, new):
    """Mail the task's leads. Returns who it went to; [] if nobody."""
    if os.environ.get("FLOW_MAIL_OFF") == "1":
        return []
    row = sg.find_one("Task", [["id", "is", task["id"]]],
                      [config.TASK_LEAD_FIELD]) or {}
    to = recipients(row.get(config.TASK_LEAD_FIELD))
    if not to:
        log.info("task %s has no %s; no review mail", task["id"],
                 config.TASK_LEAD_FIELD)
        return []
    redirect = os.environ.get("FLOW_MAIL_REDIRECT")
    if redirect:
        log.info("review mail for %s redirected to %s", to, redirect)
        to = [redirect]
    subject, body = message(task, artist, email, note, old, new)
    _send_email()(to, subject, body)
    log.info("review mail for task %s sent to %s", task["id"], to)
    return to


def _send_email():
    if config.PIPELINE_ROOT not in sys.path:
        sys.path.insert(0, config.PIPELINE_ROOT)
    from services.mailer import send_email    # pipeline's SMTP helper
    return send_email
