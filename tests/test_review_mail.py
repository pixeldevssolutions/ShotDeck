"""Sending a task for review mails its leads, with the artist's note."""

import os

import config
import fakes
import review_mail

TASK = {"type": "Task", "id": 77, "content": "Comp",
        "project": {"type": "Project", "id": 5, "name": "UAT6"},
        "entity": {"type": "Shot", "id": 9, "name": "AD1030"},
        "step": {"type": "Step", "id": 3, "name": "Comp"}}


def _send(leads, note="Edge fixed, please check"):
    sg = fakes.FakeShotgun()
    sg.tasks.append(dict(TASK, **{config.TASK_LEAD_FIELD: leads}))
    sent = []
    real = review_mail._send_email
    review_mail._send_email = lambda: lambda *a: sent.append(a)
    try:
        to = review_mail.send(sg, TASK, "Jitesh", "jitesh@5and8.ai",
                              note, "ip", "prw")
    finally:
        review_mail._send_email = real
    return to, sent


def test_the_leads_get_the_task_and_the_note():
    to, sent = _send("rahul@5and8.ai, priya@5and8.ai")
    assert to == ["rahul@5and8.ai", "priya@5and8.ai"]
    (addrs, subject, body), = sent
    assert addrs == to
    assert subject == "[UAT6] AD1030 Comp ready for review - Jitesh"
    assert "Edge fixed, please check" in body
    assert "ip -&gt; prw" in body
    assert config.entity_url("Task", 77) in body


def test_no_leads_means_no_mail():
    assert _send("") == ([], [])
    assert review_mail.recipients("rahul, priya@5and8.ai;") == \
        ["priya@5and8.ai"], "names without an address are not mailable"


def test_a_redirect_sends_everything_to_one_address():
    os.environ["FLOW_MAIL_REDIRECT"] = "test@5and8.ai"
    try:
        to, sent = _send("rahul@5and8.ai")
    finally:
        del os.environ["FLOW_MAIL_REDIRECT"]
    assert to == ["test@5and8.ai"] and sent[0][0] == ["test@5and8.ai"]


def test_the_note_is_escaped():
    _, sent = _send("rahul@5and8.ai", note="<b>a</b>\nb")
    assert "&lt;b&gt;a&lt;/b&gt;<br>b" in sent[0][2]
