"""Owner decision briefs stored as atomic JSON files."""
import json, secrets
from datetime import datetime, timezone
from pathlib import Path

def _root(workspace): return Path(workspace).resolve()/".ai-house"/"briefs"
def _now(): return datetime.now(timezone.utc).isoformat()
def _read(path): return json.loads(path.read_text(encoding="utf-8"))
def _write(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(".tmp")
 tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
 tmp.replace(path)

def create_brief(workspace,room_id,question,options,context=""):
 if not isinstance(options,(list,tuple)) or not 2<=len(options)<=4: raise ValueError("A brief must have 2 to 4 options")
 choices=[str(x).strip() for x in options]
 if any(not x or len(x)>=60 for x in choices): raise ValueError("Each brief option must be non-empty and under 60 characters")
 question=str(question).strip()
 if not question: raise ValueError("Brief question must not be empty")
 root=_root(workspace);root.mkdir(parents=True,exist_ok=True)
 for path in root.glob("*.json"):
  try:
   item=_read(path)
   if item.get("status")=="open" and item.get("room")==str(room_id) and item.get("question")==question:return str(item["id"])
  except (OSError,ValueError,TypeError): pass
 bid=secrets.token_hex(4)
 _write(root/(bid+".json"),{"id":bid,"room":str(room_id),"question":question,"options":choices,"context":str(context)[:800],"status":"open","created_at":_now()})
 return bid

def answer_brief(workspace,brief_id,choice):
 bid=str(brief_id);path=_root(workspace)/(bid+".json")
 if not path.is_file():raise ValueError("Unknown brief id: "+bid)
 item=_read(path)
 if item.get("status")!="open":raise ValueError("Brief "+bid+" has already been answered")
 options=item.get("options",[]);selected=str(choice).strip()
 if selected.isdigit():
  index=int(selected)
  if not 1<=index<=len(options):raise ValueError("Choice number must be between 1 and "+str(len(options)))
  selected=options[index-1]
 if selected not in options:raise ValueError("Invalid choice; choose one of: "+", ".join(options))
 item.update(status="answered",choice=selected,answered_at=_now());_write(path,item);return item

def get_brief_answer(workspace,brief_id):
 if not brief_id:return None
 try:
  item=_read(_root(workspace)/(str(brief_id)+".json"))
  return item.get("choice") if item.get("status")=="answered" else None
 except (OSError,ValueError,TypeError):return None

def list_briefs(workspace,open_only=True):
 out=[];root=_root(workspace)
 try:paths=list(root.glob("*.json"))
 except OSError:paths=[]
 for path in paths:
  try:
   item=_read(path)
   if isinstance(item,dict) and (not open_only or item.get("status")=="open"):out.append(item)
  except (OSError,ValueError,TypeError):pass
 out.sort(key=lambda x:str(x.get("created_at","")));return out
