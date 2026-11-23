"""North Face learning ledger."""
import hashlib,json,re
from datetime import datetime,timezone,timedelta
from pathlib import Path
DAYS=timedelta(days=30)
def _now(): return datetime.now(timezone.utc).isoformat()
def _dt(v):
 try:
  d=datetime.fromisoformat(str(v).replace("Z","+00:00")); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
 except Exception: return datetime.now(timezone.utc)
def _key(v): return re.sub(r"[^a-z0-9]+"," ",str(v).lower()).strip()[:180]
def _id(k): return hashlib.sha1(_key(k).encode()).hexdigest()[:12]
def _list(v,n=12): return v[:n] if isinstance(v,list) else ([] if v is None or v=="" else [str(v)[:700]])
def _defaults(x):
 k=x.get("key") or _key(x.get("improvement_rule") or x.get("lesson","")); x["key"]=k; x.setdefault("id",_id(k))
 x.setdefault("state","confirmed" if int(x.get("count",1))>=2 else "candidate")
 for k,v in (("role_scope",["all"]),("task_types",["all"]),("source_task_ids",[]),("times_applied",0),("outcomes",{"positive":0,"negative":0}),("superseded_by",None),("confidence","low"),("improvement_rule",x.get("lesson","")),("root_cause",""),("count",1)): x.setdefault(k,v)
 last=x.get("last_seen",_now()); x.setdefault("last_seen",last); x.setdefault("first_seen",last); x.setdefault("expires_at",(_dt(last)+DAYS).isoformat()); return x
def load(path):
 try:
  d=json.loads(Path(path).read_text(encoding="utf-8"))
  if isinstance(d,dict):
   for k,v in (("version",1),("lessons",[]),("task_reviews",[]),("mistake_patterns",[]),("business_postmortems",[])): d.setdefault(k,v)
   for x in d["lessons"]:
    if isinstance(x,dict): _defaults(x)
   for x in d["mistake_patterns"]:
    if isinstance(x,dict): x.setdefault("role_scope",["all"])
   return d
 except Exception: pass
 return {"version":1,"created_at":_now(),"lessons":[],"task_reviews":[],"mistake_patterns":[],"business_postmortems":[]}
def save(path,data):
 p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); data["updated_at"]=_now(); t=p.with_suffix(".tmp"); t.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8"); t.replace(p)
def _similar(a,b):
 a,b=set(_key(a).split()),set(_key(b).split()); return bool(a and b and len(a&b)/max(len(a),len(b))>=.8)
def _find(xs,k): return next((x for x in xs if x.get("key")==k),None) or next((x for x in xs if _similar(k,x.get("key",""))),None)
def _trim(xs):
 now=datetime.now(timezone.utc); return sorted(xs,key=lambda x:(x.get("state")!="retired",_dt(x.get("expires_at"))>now,int(x.get("count",1)),x.get("last_seen","")))[-120:]
def record_task(path,task,status,review,learning,output_summary=""):
 d=load(path); tid=str(task.get("id",task.get("title","task"))); now=_now(); role=str(task.get("agent_role","all") or "all"); typ=str((task.get("input") or {}).get("task_type","all") or "all"); conf=str(learning.get("confidence","low")).lower()
 item={"at":now,"task_id":tid,"title":str(task.get("title",""))[:300],"role":role,"status":str(status),"score":review.get("score"),"issues":_list(review.get("issues",[]),8),"root_cause":str(learning.get("root_cause",""))[:700],"lesson":str(learning.get("lesson",""))[:700],"improvement_rule":str(learning.get("improvement_rule",""))[:700],"confidence":conf,"summary":str(output_summary)[:1200]}
 d["task_reviews"]=(d["task_reviews"]+[item])[-300:]; text=item["improvement_rule"] or item["lesson"]
 if text:
  k=_key(text); x=_find(d["lessons"],k)
  if x is None:
   x=_defaults({"key":k,"id":_id(k),"lesson":text,"improvement_rule":item["improvement_rule"] or text,"root_cause":item["root_cause"],"confidence":conf,"role_scope":[role],"task_types":[typ],"source_task_ids":[],"count":0,"state":"candidate","times_applied":0,"outcomes":{"positive":0,"negative":0},"superseded_by":None,"first_seen":now,"last_seen":now,"expires_at":(datetime.now(timezone.utc)+DAYS).isoformat(),"source":"task"}); d["lessons"].append(x)
  ids=x.setdefault("source_task_ids",[]); fresh=tid not in ids
  if fresh: ids.append(tid); ids[:]=ids[-20:]
  x["count"]=int(x.get("count",0))+int(fresh); x["last_seen"]=now; x["latest_context"]=tid; x["status"]=status
  if conf=="high": x["confidence"]="high"
  for f,v in (("role_scope",role),("task_types",typ)):
   a=x.setdefault(f,["all"])
   if v not in a: a.append(v)
  x["improvement_rule"]=item["improvement_rule"] or x.get("improvement_rule",""); x["root_cause"]=item["root_cause"] or x.get("root_cause","")
  if len(set(ids))>=2 or (conf=="high" and str(status).lower() in ("approved","completed")): x["state"]="confirmed"
  if x.get("state")=="confirmed": x["expires_at"]=(datetime.now(timezone.utc)+DAYS).isoformat()
  cause=_key(item["root_cause"])
  if cause and (conf=="high" or len(set(ids))>=2):
   for old in d["lessons"]:
    if old is not x and old.get("state")=="confirmed" and _key(old.get("root_cause",""))==cause and _key(old.get("improvement_rule",""))!=_key(item["improvement_rule"]): old["state"]="retired"; old["superseded_by"]=x["id"]
 cause=item["root_cause"]
 if cause and status not in ("completed","approved"):
  k=_key(cause); p=next((z for z in d["mistake_patterns"] if z.get("key")==k),None)
  if p:
   p["count"]=int(p.get("count",1))+1; p["last_seen"]=now; p["examples"]=(p.get("examples",[])+[tid])[-8:]
   if role not in p.setdefault("role_scope",["all"]): p["role_scope"].append(role)
  else: d["mistake_patterns"].append({"key":k,"root_cause":cause,"count":1,"first_seen":now,"last_seen":now,"examples":[tid],"role_scope":[role]})
 d["lessons"]=_trim(d["lessons"]); d["mistake_patterns"]=sorted(d["mistake_patterns"],key=lambda x:int(x.get("count",1)),reverse=True)[:60]; save(path,d); return d
def record_outcome(path,lesson_ids,task_id,status):
 d=load(path); ids=set(lesson_ids or [])
 for x in d["lessons"]:
  if x.get("id") not in ids: continue
  x["times_applied"]=int(x.get("times_applied",0))+1; o=x.setdefault("outcomes",{"positive":0,"negative":0})
  if status=="completed": o["positive"]=int(o.get("positive",0))+1
  elif status in ("failed","retry"): o["negative"]=int(o.get("negative",0))+1
  pos,neg=int(o.get("positive",0)),int(o.get("negative",0))
  if neg>=3 and neg>pos and x.get("state")!="candidate": x["state"]="candidate"; x.setdefault("demotion_log",[]).append({"at":_now(),"task_id":str(task_id),"reason":"negative outcomes >= 3 and exceed positive outcomes"})
  if x["times_applied"] and pos+neg and pos/(pos+neg)>.5: x["expires_at"]=(_dt(x.get("expires_at"))+DAYS).isoformat()
 save(path,d); return d
def record_business(path,business,outcome,postmortem):
 d=load(path); item={"at":_now(),"business":str(business.get("name","unknown"))[:300],"outcome":str(outcome.get("decision","unknown")),"metric":str(outcome.get("metric",""))[:500],"evidence":_list(outcome.get("evidence",[]),8),"failure_reasons":_list(outcome.get("failure_reasons",[]),8),"what_worked":_list(postmortem.get("what_worked",[]),8),"what_failed":_list(postmortem.get("what_failed",[]),8),"root_causes":_list(postmortem.get("root_causes",[]),8),"lessons":_list(postmortem.get("lessons",[]),12),"next_changes":_list(postmortem.get("next_changes",[]),12)}
 d["business_postmortems"]=(d["business_postmortems"]+[item])[-100:]; pid=item["at"]+":"+item["business"]
 for raw in item["lessons"]+item["next_changes"]:
  text=str(raw).strip()
  if not text: continue
  k=_key(text); x=_find(d["lessons"],k)
  if x is None:
   x=_defaults({"key":k,"id":_id(k),"lesson":text,"improvement_rule":text,"root_cause":"","confidence":"medium","role_scope":["all"],"task_types":["all"],"source_task_ids":[],"count":0,"state":"candidate","times_applied":0,"outcomes":{"positive":0,"negative":0},"superseded_by":None,"first_seen":item["at"],"last_seen":item["at"],"expires_at":(datetime.now(timezone.utc)+DAYS).isoformat(),"source":"business","source_postmortem_ids":[]}); d["lessons"].append(x)
  posts=x.setdefault("source_postmortem_ids",[])
  if pid not in posts: posts.append(pid)
  x["count"]=len(posts); x["source"]="business"; x["confidence"]="medium"; x["role_scope"]=["all"]; x["last_seen"]=item["at"]; x["latest_context"]=item["business"]; x["state"]="confirmed" if len(posts)>=2 else "candidate"
  if x["state"]=="confirmed": x["expires_at"]=(datetime.now(timezone.utc)+DAYS).isoformat()
 d["lessons"]=_trim(d["lessons"]); save(path,d); return d
def _eligible(x,role,task_type):
 if x.get("state")!="confirmed" or x.get("superseded_by") is not None or _dt(x.get("expires_at"))<=datetime.now(timezone.utc): return False
 roles=x.get("role_scope") or ["all"]; types=x.get("task_types") or ["all"]
 if "all" not in roles and (role is None or role not in roles): return False
 return task_type is None or "all" in types or task_type in types
def context_with_ids(path,role=None,task_type=None):
 d=load(path); now=datetime.now(timezone.utc)
 def rank(x): return int(x.get("count",1))*{"high":3,"medium":2,"low":1}.get(str(x.get("confidence","low")).lower(),1)*(1.0 if now-_dt(x.get("last_seen"))<=timedelta(days=7) else .5)
 ls=sorted((x for x in d.get("lessons",[]) if _eligible(x,role,task_type)),key=rank,reverse=True)[:8]; ids=[x.get("id") for x in ls]
 ps=[x for x in d.get("mistake_patterns",[]) if "all" in (x.get("role_scope") or ["all"]) or (role is not None and role in x.get("role_scope",[]))]
 ps=sorted(ps,key=lambda x:int(x.get("count",1)),reverse=True)[:8]
 txt=("THE NORTH FACE — SELF-IMPROVEMENT MEMORY (highest operating priority)\nUse confirmed, relevant experience to improve decisions and execution. Check recurring mistakes. Apply rules explicitly; do not repeat contradicted or expired lessons. After each task, extract evidence-based learning.\nReusable lessons:\n"+json.dumps([{"id":x.get("id"),"lesson":x.get("lesson"),"improvement_rule":x.get("improvement_rule"),"frequency":x.get("count",1),"context":x.get("latest_context")} for x in ls],ensure_ascii=False)[:7000]+"\nRecurring mistake patterns:\n"+json.dumps([{"root_cause":x.get("root_cause"),"frequency":x.get("count"),"examples":x.get("examples",[])} for x in ps],ensure_ascii=False)[:3500])
 return txt,ids
def context(path,max_lessons=18,role=None,task_type=None):
 base=context_with_ids(path,role,task_type)[0]
 audit=decision_review_context(path,12)
 return base+"\\n\\nNORTH FACE — LEADER DECISION AUDIT\\nBefore repeating a recent decision, compare its expected outcome with observed evidence. Challenge weak rationale, consider alternatives, and explicitly keep, modify, or rollback; do not treat untested decisions as proven. Open experiments with insufficient samples remain inconclusive.\\n"+json.dumps(audit,ensure_ascii=False)[:9000]


def record_decision(path, decision, review=None):
 """Persist a structured, evidence-aware review of a Leader decision."""
 d=load(path); review=review if isinstance(review,dict) else {}
 now=_now(); did=str(decision.get("id") or _id(str(decision.get("title","decision"))+" "+now))
 item={
  "id":did,"at":now,"title":str(decision.get("title",""))[:300],
  "decision":str(decision.get("decision",""))[:1200],
  "goal":str(decision.get("goal",""))[:700],
  "rationale":str(decision.get("rationale",""))[:1200],
  "alternatives":_list(decision.get("alternatives",[]),6),
  "expected_outcome":str(decision.get("expected_outcome",""))[:700],
  "success_metric":str(decision.get("success_metric",""))[:500],
  "evidence":_list(decision.get("evidence",[]),8),
  "risks":_list(decision.get("risks",[]),8),
  "confidence":str(decision.get("confidence","low")).lower(),
  "review":str(review.get("keep_modify_or_rollback",review.get("decision","review"))).lower(),
  "review_reason":str(review.get("reason",""))[:1000],
  "observed_outcome":str(review.get("observed_outcome",""))[:1000],
  "lesson":str(review.get("lesson",""))[:1000],
  "evidence_quality":str(review.get("evidence_quality","unverified")).lower()
 }
 d.setdefault("decision_reviews",[]); d["decision_reviews"]=(d["decision_reviews"]+[item])[-500:]
 save(path,d); return item

def review_decision(path, decision_id, review):
 """Update the original decision with its later measured outcome and verdict."""
 d=load(path);item=next((x for x in d.get("decision_reviews",[]) if str(x.get("id"))==str(decision_id)),None)
 if item is None:return None
 review=review if isinstance(review,dict) else {}
 item["reviewed_at"]=_now()
 item["review"]=str(review.get("keep_modify_or_rollback",review.get("decision","review"))).lower()[:40]
 item["review_reason"]=str(review.get("reason",""))[:1000]
 item["observed_outcome"]=str(review.get("observed_outcome",""))[:1000]
 item["lesson"]=str(review.get("lesson",""))[:1000]
 item["evidence_quality"]=str(review.get("evidence_quality","unverified")).lower()[:80]
 save(path,d);return item

def record_experiment(path, experiment):
 """Register a testable hypothesis; registration never marks it successful."""
 d=load(path); e=dict(experiment or {})
 title=str(e.get("title","")).strip()
 hypothesis=str(e.get("hypothesis","")).strip()
 metric=str(e.get("metric","")).strip()
 if not title or not hypothesis or not metric:
  raise ValueError("Experiment requires title, hypothesis, and metric")
 eid=str(e.get("id") or _id(title+" "+_now()))
 item={
  "id":eid,"created_at":_now(),"title":title[:300],"hypothesis":hypothesis[:1200],
  "metric":metric[:500],"baseline":e.get("baseline"),"target":e.get("target"),
  "direction":str(e.get("direction","increase")).lower(),
  "minimum_samples":max(1,int(e.get("minimum_samples",10))),
  "control_description":str(e.get("control_description",""))[:700],
  "treatment_description":str(e.get("treatment_description",""))[:700],
  "status":"proposed","observations":[],"evaluation":None
 }
 if item["direction"] not in ("increase","decrease","reduce","increase_or_equal"):
  raise ValueError("Unsupported experiment direction")
 d.setdefault("experiments",[]); d["experiments"]=(d["experiments"]+[item])[-200:]
 save(path,d); return item

def evaluate_experiment(path, experiment_id, observations):
 """Evaluate with sample-count and metric evidence; underpowered results stay inconclusive."""
 d=load(path); exp=next((x for x in d.get("experiments",[]) if x.get("id")==experiment_id),None)
 if exp is None: raise KeyError("Experiment not found")
 obs=[x for x in (observations or []) if isinstance(x,dict)]
 exp["observations"]=obs[-100:]
 def number(v):
  try:
   n=float(v); return n if n==n and abs(n)!=float("inf") else None
  except (TypeError,ValueError): return None
 baseline=number(exp.get("baseline")); actual=number(obs[-1].get("value")) if obs else None
 samples=sum(max(0,int(x.get("sample_size",0) or 0)) for x in obs)
 required=int(exp.get("minimum_samples",10))
 result={"evaluated_at":_now(),"baseline":baseline,"observed":actual,"sample_size":samples,"required_samples":required,"metric":exp.get("metric")}
 if baseline is None or actual is None:
  result.update({"status":"inconclusive","reason":"Baseline and observed numeric metric are required"})
 elif samples<required:
  result.update({"status":"inconclusive","reason":"Insufficient sample size"})
 else:
  direction=exp.get("direction","increase")
  passed=(actual>baseline if direction=="increase" else actual<baseline if direction in ("decrease","reduce") else actual>=baseline)
  result.update({"status":"supported" if passed else "not_supported","reason":"Metric met the registered direction" if passed else "Metric did not meet the registered direction"})
 exp["evaluation"]=result; exp["status"]=result["status"]
 save(path,d); return result

def decision_review_context(path, limit=12):
 d=load(path)
 decisions=d.get("decision_reviews",[])[-max(1,min(int(limit),50)):]
 experiments=d.get("experiments",[])[-max(1,min(int(limit),50)):]
 return {"recent_decisions":[{"id":x.get("id"),"title":x.get("title"),"decision":x.get("decision"),"rationale":x.get("rationale"),"expected_outcome":x.get("expected_outcome"),"review":x.get("review"),"observed_outcome":x.get("observed_outcome"),"lesson":x.get("lesson"),"evidence_quality":x.get("evidence_quality")} for x in reversed(decisions)],"experiments":[{"id":x.get("id"),"title":x.get("title"),"hypothesis":x.get("hypothesis"),"metric":x.get("metric"),"status":x.get("status"),"evaluation":x.get("evaluation")} for x in reversed(experiments)]}
