"""North Face regression tests."""
import json
import north_face as nf
def task(i,role="researcher"): return {"id":i,"title":"sample","agent_role":role,"input":{"task_type":"research"}}
def learning(rule="Use automated tests for each change",cause="missing validation",confidence="low"): return {"lesson":rule,"improvement_rule":rule,"root_cause":cause,"confidence":confidence}
def add(p,i,status="failed",role="researcher",rule="Use automated tests for each change",cause="missing validation",confidence="low"): return nf.record_task(p,task(i,role),status,{},learning(rule,cause,confidence))
def test_once_candidate_hidden(tmp_path):
 p=tmp_path/"north_face.json"; d=add(p,"1"); assert d["lessons"][0]["state"]=="candidate"; assert "Use automated tests" not in nf.context(p)
def test_two_tasks_confirm(tmp_path):
 p=tmp_path/"north_face.json"; add(p,"1"); d=add(p,"2"); assert d["lessons"][0]["state"]=="confirmed"; assert "Use automated tests" in nf.context(p)
def test_role_filter(tmp_path):
 p=tmp_path/"north_face.json"; add(p,"1","completed","researcher",confidence="high"); assert "Use automated tests" not in nf.context(p,role="builder")
def test_expired_filter(tmp_path):
 p=tmp_path/"north_face.json"; add(p,"1","completed",confidence="high"); d=nf.load(p); d["lessons"][0]["expires_at"]="2000-01-01T00:00:00+00:00"; nf.save(p,d); assert "Use automated tests" not in nf.context(p)
def test_contradiction_retires_old(tmp_path):
 p=tmp_path/"north_face.json"; add(p,"old","completed",rule="Always validate before delivery",cause="validation policy",confidence="high"); d=add(p,"new","completed",rule="Never validate before delivery",cause="validation policy",confidence="high"); old=next(x for x in d["lessons"] if x["state"]=="retired"); new=next(x for x in d["lessons"] if x["state"]=="confirmed" and x["improvement_rule"].startswith("Never")); assert old["superseded_by"]==new["id"]
def test_near_duplicate_merge(tmp_path):
 p=tmp_path/"north_face.json"; add(p,"1",rule="Use automated tests for each change",cause="testing"); d=add(p,"2",rule="Use automated tests for every change",cause="testing"); assert len(d["lessons"])==1 and d["lessons"][0]["count"]==2
def test_three_failures_demote(tmp_path):
 p=tmp_path/"north_face.json"; add(p,"1","completed",confidence="high"); lid=nf.load(p)["lessons"][0]["id"]
 for i in range(3): nf.record_outcome(p,[lid],"f"+str(i),"failed")
 x=nf.load(p)["lessons"][0]; assert x["state"]=="candidate" and len(x["demotion_log"])==1
def test_path_only_context(tmp_path): assert isinstance(nf.context(tmp_path/"north_face.json"),str)
def test_legacy_migrates(tmp_path):
 p=tmp_path/"north_face.json"; p.write_text(json.dumps({"lessons":[{"key":"legacy rule","lesson":"legacy rule","count":2,"last_seen":"2026-01-01T00:00:00+00:00"}]}),encoding="utf-8")
 x=nf.load(p)["lessons"][0]; assert x["state"]=="confirmed"
 for k in ("id","role_scope","task_types","source_task_ids","times_applied","outcomes","superseded_by","expires_at"): assert k in x


def test_decision_reflection_persists_keep_modify_rollback(tmp_path):
 p=tmp_path/"north_face.json"
 item=nf.record_decision(p,{"title":"Choose onboarding flow","decision":"Use guided setup","goal":"Improve activation","rationale":"User tests showed confusion","alternatives":["single screen","guided setup"],"expected_outcome":"More users complete setup","success_metric":"activation rate","evidence":["5 moderated tests"],"confidence":"medium"},{"keep_modify_or_rollback":"modify","reason":"Completion improved but dropoff remains","observed_outcome":"3/5 completed","lesson":"Reduce step count","evidence_quality":"small_sample"})
 assert item["review"]=="modify" and item["evidence_quality"]=="small_sample"
 assert nf.load(p)["decision_reviews"][0]["lesson"]=="Reduce step count"

def test_experiment_requires_hypothesis_and_metric(tmp_path):
 import pytest
 with pytest.raises(ValueError): nf.record_experiment(tmp_path/"nf.json",{"title":"A/B"})

def test_experiment_underpowered_stays_inconclusive(tmp_path):
 p=tmp_path/"north_face.json"
 exp=nf.record_experiment(p,{"title":"Landing page test","hypothesis":"Shorter copy raises signup","metric":"signup rate","baseline":0.1,"minimum_samples":10})
 result=nf.evaluate_experiment(p,exp["id"],[{"value":0.2,"sample_size":4}])
 assert result["status"]=="inconclusive" and result["sample_size"]==4

def test_experiment_supported_only_with_registered_metric_and_samples(tmp_path):
 p=tmp_path/"north_face.json"
 exp=nf.record_experiment(p,{"title":"Activation test","hypothesis":"Improved onboarding raises activation","metric":"activation rate","baseline":0.2,"minimum_samples":10})
 result=nf.evaluate_experiment(p,exp["id"],[{"value":0.3,"sample_size":10}])
 assert result["status"]=="supported"
 assert nf.load(p)["experiments"][0]["status"]=="supported"


def test_review_decision_updates_original_with_observed_outcome(tmp_path):
 p=tmp_path/"north_face.json"
 nf.record_decision(p,{"id":"roadmap-1-0","title":"Roadmap decision","decision":"Use strategy A","rationale":"Evidence supports a small test","alternatives":["Strategy B"],"expected_outcome":"10 users","success_metric":"10 users","evidence":["source"],"risks":["uncertain demand"],"confidence":"medium"},{"decision":"keep","reason":"Plan just created","evidence_quality":"planning"})
 reviewed=nf.review_decision(p,"roadmap-1-0",{"keep_modify_or_rollback":"modify","reason":"Target missed","observed_outcome":"2 users observed","lesson":"Narrow onboarding","evidence_quality":"postmortem"})
 assert reviewed["review"]=="modify"
 assert reviewed["observed_outcome"]=="2 users observed"
 assert reviewed["lesson"]=="Narrow onboarding"
