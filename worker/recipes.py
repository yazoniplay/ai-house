"""Reusable roadmap recipes; persist task structure only."""
import json,re
from datetime import datetime,timezone
from pathlib import Path
_FIELDS=("id","title","objective","agent_role","depends_on","acceptance","deliverable","search","needs_approval")
def _root(workspace):return Path(workspace).resolve()/".ai-house"/"recipes"
def _slug(name):return (re.sub(r"[^a-z0-9]+","-",str(name).lower()).strip("-") or "recipe")[:64]
def _read(path):return json.loads(path.read_text(encoding="utf-8"))
def _write(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(".tmp")
 tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8");tmp.replace(path)
def save_recipe(workspace,name,source_business,tasks,success_metric,strategy,evidence_summary):
 tasks=list(tasks) if isinstance(tasks,(list,tuple)) else []
 clean=[]
 for task in tasks:
  if not isinstance(task,dict) or task.get("status")!="completed":continue
  item={}
  for key in _FIELDS:
   if key not in task:continue
   value=task[key]
   if key in ("depends_on","acceptance") and isinstance(value,list):item[key]=[str(x)[:500] for x in value[:12]]
   elif key=="needs_approval":item[key]=bool(value)
   elif isinstance(value,(str,int,float,bool)) or value is None:item[key]=str(value)[:1500] if isinstance(value,str) else value
  clean.append(item)
 slug=_slug(name);path=_root(workspace)/(slug+".json");old={}
 if path.is_file():
  try:old=_read(path)
  except Exception:pass
 item={"name":str(name)[:160],"slug":slug,"source_business":str(source_business)[:200],"created_at":datetime.now(timezone.utc).isoformat(),"times_used":int(old.get("times_used",0)),"outcome":"success" if clean and len(clean)==len(tasks) else "partial","success_metric":str(success_metric)[:800],"strategy":str(strategy)[:1200],"evidence_summary":str(evidence_summary)[:2500],"tasks":clean}
 _write(path,item);return item
def list_recipes(workspace):
 out=[];root=_root(workspace)
 try:paths=list(root.glob("*.json"))
 except OSError:paths=[]
 for path in paths:
  try:
   x=_read(path);out.append({"name":x.get("name",path.stem),"slug":x.get("slug",path.stem),"outcome":x.get("outcome","partial"),"times_used":int(x.get("times_used",0)),"success_metric":x.get("success_metric","")})
  except (OSError,ValueError,TypeError):pass
 out.sort(key=lambda x:(x["outcome"]!="success",-x["times_used"],x["name"].lower()));return out
def load_recipe(workspace,slug):
 try:
  x=_read(_root(workspace)/(str(slug)+".json"));return x if isinstance(x,dict) else None
 except (OSError,ValueError,TypeError):return None
def recipe_for_prompt(workspace,limit=3):
 summaries=list_recipes(workspace)[:max(0,min(3,int(limit)))];lines=[]
 for summary in summaries:
  item=load_recipe(workspace,summary["slug"])
  if not item:continue
  lines.append("- "+summary["name"]+" ("+summary["outcome"]+", used "+str(summary["times_used"])+"): metric "+str(summary["success_metric"])[:300])
  for task in item.get("tasks",[])[:8]:lines.append("  - "+str(task.get("agent_role",""))+": "+str(task.get("title",""))[:160]+" — "+str(task.get("objective",""))[:240])
 return "\n".join(lines) if lines else "(no proven recipes yet)"
