"""The North Face: persistent self-improvement memory for AI House.

This is a local learning ledger, not model fine-tuning. It stores task feedback,
root causes, reusable improvement rules, recurring mistakes, and business
postmortems so future leader/agent decisions can use real prior experience.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

def _now():
    return datetime.now(timezone.utc).isoformat()

def _key(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()[:180]

def _list(value, limit=12):
    if isinstance(value, list):
        return value[:limit]
    if value is None or value == "":
        return []
    return [str(value)[:700]]

def load(path):
    p=Path(path)
    try:
        data=json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data,dict):
            data.setdefault("version",1)
            data.setdefault("lessons",[])
            data.setdefault("task_reviews",[])
            data.setdefault("mistake_patterns",[])
            data.setdefault("business_postmortems",[])
            return data
    except Exception:
        pass
    return {"version":1,"created_at":_now(),"lessons":[],"task_reviews":[],"mistake_patterns":[],"business_postmortems":[]}

def save(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    data["updated_at"]=_now()
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    tmp.replace(p)

def record_task(path, task, status, review, learning, output_summary=""):
    data=load(path)
    task_id=str(task.get("id",task.get("title","task")))
    item={
        "at":_now(),"task_id":task_id,"title":str(task.get("title",""))[:300],
        "role":str(task.get("agent_role","")),"status":str(status),
        "score":review.get("score"),"issues":_list(review.get("issues",[]),8),
        "root_cause":str(learning.get("root_cause",""))[:700],
        "lesson":str(learning.get("lesson",""))[:700],
        "improvement_rule":str(learning.get("improvement_rule",""))[:700],
        "confidence":learning.get("confidence","medium"),
        "summary":str(output_summary)[:1200],
    }
    data["task_reviews"].append(item)
    data["task_reviews"]=data["task_reviews"][-300:]
    lesson=item["improvement_rule"] or item["lesson"]
    if lesson:
        key=_key(lesson)
        existing=next((x for x in data["lessons"] if x.get("key")==key),None)
        if existing:
            existing["count"]=int(existing.get("count",1))+1
            existing["last_seen"]=_now()
            existing["latest_context"]=task_id
            existing["status"]=status
        else:
            data["lessons"].append({"key":key,"lesson":lesson,"count":1,"first_seen":_now(),"last_seen":_now(),"latest_context":task_id,"status":status,"source":"task"})
    cause=item["root_cause"]
    if cause and status not in ("completed","approved"):
        key=_key(cause)
        pattern=next((x for x in data["mistake_patterns"] if x.get("key")==key),None)
        if pattern:
            pattern["count"]=int(pattern.get("count",1))+1
            pattern["last_seen"]=_now()
            pattern["examples"]=(pattern.get("examples",[])+[task_id])[-8:]
        else:
            data["mistake_patterns"].append({"key":key,"root_cause":cause,"count":1,"first_seen":_now(),"last_seen":_now(),"examples":[task_id]})
    data["lessons"]=data["lessons"][-120:]
    data["mistake_patterns"]=sorted(data["mistake_patterns"],key=lambda x:int(x.get("count",1)),reverse=True)[:60]
    save(path,data)
    return data

def record_business(path, business, outcome, postmortem):
    data=load(path)
    item={
        "at":_now(),"business":str(business.get("name","unknown"))[:300],
        "outcome":str(outcome.get("decision","unknown")),
        "metric":str(outcome.get("metric",""))[:500],
        "evidence":_list(outcome.get("evidence",[]),8),
        "failure_reasons":_list(outcome.get("failure_reasons",[]),8),
        "what_worked":_list(postmortem.get("what_worked",[]),8),
        "what_failed":_list(postmortem.get("what_failed",[]),8),
        "root_causes":_list(postmortem.get("root_causes",[]),8),
        "lessons":_list(postmortem.get("lessons",[]),12),
        "next_changes":_list(postmortem.get("next_changes",[]),12),
    }
    data["business_postmortems"].append(item)
    data["business_postmortems"]=data["business_postmortems"][-100:]
    for lesson in item["lessons"]+item["next_changes"]:
        lesson=str(lesson).strip()
        if not lesson:continue
        key=_key(lesson)
        existing=next((x for x in data["lessons"] if x.get("key")==key),None)
        if existing:
            existing["count"]=int(existing.get("count",1))+1
            existing["last_seen"]=_now()
            existing["latest_context"]=item["business"]
            existing["source"]="business"
        else:
            data["lessons"].append({"key":key,"lesson":lesson,"count":1,"first_seen":_now(),"last_seen":_now(),"latest_context":item["business"],"source":"business"})
    data["lessons"]=data["lessons"][-120:]
    save(path,data)
    return data

def context(path, max_lessons=18):
    data=load(path)
    lessons=sorted(data.get("lessons",[]),key=lambda x:(int(x.get("count",1)),x.get("last_seen","")),reverse=True)[:max_lessons]
    patterns=sorted(data.get("mistake_patterns",[]),key=lambda x:int(x.get("count",1)),reverse=True)[:8]
    postmortems=data.get("business_postmortems",[])[-3:]
    return (
        "THE NORTH FACE — SELF-IMPROVEMENT MEMORY (highest operating priority)\n"
        "Use this experience to improve decisions, task execution, review quality, and business strategy. "
        "Check whether a known mistake is recurring before assigning work. Apply relevant rules explicitly. "
        "Do not blindly repeat old lessons when new evidence contradicts them. After every task, extract a "
        "specific lesson/root cause/improvement rule; after every business outcome, perform a candid postmortem. "
        "Learning must change future behavior, not merely produce reflective text.\n"
        "Reusable lessons:\n"+json.dumps([{"lesson":x.get("lesson"),"frequency":x.get("count",1),"context":x.get("latest_context")} for x in lessons],ensure_ascii=False)[:7000]+
        "\nRecurring mistake patterns:\n"+json.dumps([{"root_cause":x.get("root_cause"),"frequency":x.get("count"),"examples":x.get("examples",[])} for x in patterns],ensure_ascii=False)[:3500]+
        "\nRecent business postmortems:\n"+json.dumps(postmortems,ensure_ascii=False)[:5000]
    )
