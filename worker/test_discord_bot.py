"""Regression tests for owner-only Discord approval button routing."""
from discord_bot import parse_approval_alert, parse_brief_alert

def test_parse_owner_approval_alert():
    text="Risky desktop action\n!approve ab12cd34\n!deny ab12cd34"
    assert parse_approval_alert(text)=="ab12cd34"

def test_rejects_mismatched_ids():
    assert parse_approval_alert("!approve ab12cd34\n!deny ff12ee34") is None

def test_rejects_unrelated_message():
    assert parse_approval_alert("Task waiting. Reply !approve to continue") is None


def test_parse_owner_decision_brief():
    assert parse_brief_alert("Pick a direction\\n!brief 12ab34cd")=="12ab34cd"

def test_parse_brief_alert_ignores_other_commands():
    assert parse_brief_alert("!approve 12ab34cd") is None
