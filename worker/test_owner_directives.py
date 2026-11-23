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


def test_new_directive_changes_leader_selected_priority(monkeypatch, tmp_path):
    import autonomous_engine as engine
    monkeypatch.setattr(engine,"WORK",tmp_path)
    monkeypatch.setattr(engine,"save",lambda state:None)
    monkeypatch.setattr(engine,"log",lambda *args,**kwargs:None)
    monkeypatch.setattr(engine,"leader_json",lambda prompt:{"priority_changes":[{"task_id":"onboarding","priority":99,"reason":"Owner asked to focus on activation"}],"replan_required":False,"reason":"Applied owner direction"})
    directive=add_directive(tmp_path,"Prioritize onboarding and activation")
    state={"roadmap":{"tasks":[{"id":"onboarding","title":"Improve onboarding","priority":40,"status":"pending"}]}}
    assert engine.apply_owner_directives(state) is False
    assert state["roadmap"]["tasks"][0]["priority"]==99
    assert directive["id"] in state["owner_directives_reviewed"]
