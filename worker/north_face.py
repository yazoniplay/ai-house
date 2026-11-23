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
def context(path,max_lessons=18,role=None,task_type=None): return context_with_ids(path,role,task_type)[0]
