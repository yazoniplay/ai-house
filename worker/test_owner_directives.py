"""Tests for persistent owner directives."""
from owner_directives import add_directive, list_directives, clear_directives, context

def test_directives_persist_and_clear(tmp_path):
    first=add_directive(tmp_path,"Prioritize onboarding and ask before risky PC actions")
    second=add_directive(tmp_path,"Keep the flagship app focused")
    active=list_directives(tmp_path)
    assert [x["id"] for x in active]==[first["id"],second["id"]]
    assert "Prioritize onboarding" in context(tmp_path)
    assert clear_directives(tmp_path)==2
    assert list_directives(tmp_path)==[]

def test_directive_length_is_validated(tmp_path):
    try:
        add_directive(tmp_path,"")
    except ValueError:
        pass
    else:
        raise AssertionError("empty directive should be rejected")
