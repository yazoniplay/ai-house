"""Regression tests for readable business decision documents."""
import autonomous_engine as engine

def test_business_decision_is_readable_and_evidence_cautious():
    text=engine.business_decision_text({
        "name":"Example Workflow Tool",
        "customer":"Independent contractors",
        "problem":"Manual repetitive admin",
        "solution":"A focused automation tool",
        "validation":"Three credible source links and a small pilot hypothesis",
        "score":82,
        "owner_success_metric":"10 external users complete core action",
        "sources":["https://example.com/research"],
        "alternatives":["A spreadsheet template"],
        "risks":["Need to validate willingness to pay"],
    })
    assert "AI HOUSE — BUSINESS DECISION" in text
    assert "Target customer" in text
    assert "Alternatives considered" in text
    assert "https://example.com/research" in text
    assert "not yet proven successful" in text
    assert "Selected to test" in text
