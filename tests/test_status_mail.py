"""Status changes mail the leads (prw) or production (cmpt, pkg)."""

import os

import config
import fakes
import status_mail

TASK = {"type": "Task", "id": 77, "content": "Comp",
        "project": {"type": "Project", "id": 5, "name": "UAT6"},
        "entity": {"type": "Shot", "id": 9, "name": "AD1030"},
        "step": {"type": "Step", "id": 3, "name": "Comp"}}


def _send(leads, note="Edge fixed, please check", new="prw"):
    sg = fakes.FakeShotgun()
    sg.tasks.append(dict(TASK, **{config.TASK_LEAD_FIELD: leads}))
    sent = []
    real = status_mail._send_email
    status_mail._send_email = lambda: lambda *a: sent.append(a)
    try:
        to = status_mail.send(sg, TASK, "Jitesh", "jitesh@5and8.ai",
                              note, "ip", new)
    finally:
        status_mail._send_email = real
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
    assert status_mail.recipients("rahul, priya@5and8.ai;") == \
        ["priya@5and8.ai"], "names without an address are not mailable"


def test_complete_and_package_mail_production_not_the_leads():
    saved = config.PRODUCTION_MAIL
    config.PRODUCTION_MAIL = ["production@5and8.ai"]
    try:
        for code in ("cmpt", "pkg"):
            assert status_mail.wants_mail(code)
            to, sent = _send("rahul@5and8.ai", new=code)
            assert to == ["production@5and8.ai"]
            assert sent[0][1] == f"[UAT6] AD1030 Comp set to {code} - Jitesh"
        assert not status_mail.wants_mail("ip")
        assert _send("rahul@5and8.ai", new="ip") == ([], [])
        config.PRODUCTION_MAIL = []
        assert _send("rahul@5and8.ai", new="cmpt") == ([], [])
    finally:
        config.PRODUCTION_MAIL = saved


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
