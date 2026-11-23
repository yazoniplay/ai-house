"""Owner directives sent from the Discord mobile command center."""
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

def _path(workspace):
 return Path(workspace).resolve()/".ai-house"/"owner_directives.json"

def _now():
 return datetime.now(timezone.utc).isoformat()

def _load(path):
 try:
  data=json.loads(path.read_text(encoding="utf-8"))
  if isinstance(data,dict) and isinstance(data.get("directives"),list):return data
 except (OSError,ValueError,TypeError):pass
 return {"version":1,"directives":[]}

def _save(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(".tmp")
 tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
 tmp.replace(path)

def add_directive(workspace,text,source="discord"):
 text=str(text or "").strip()
 if not text or len(text)>2000:raise ValueError("Directive must be 1-2000 characters")
 path=_path(workspace);data=_load(path)
 item={"id":secrets.token_hex(6),"created_at":_now(),"text":text,"source":str(source)[:40],"status":"active"}
 data["directives"]=(data["directives"]+[item])[-100:]
 _save(path,data);return item

def list_directives(workspace,active_only=True,limit=20):
 items=_load(_path(workspace)).get("directives",[])
 if active_only:items=[x for x in items if x.get("status")=="active"]
 return items[-max(1,min(int(limit),100)):]

def clear_directives(workspace):
 path=_path(workspace);data=_load(path);count=0
 for item in data["directives"]:
  if item.get("status")=="active":
   item["status"]="cleared";item["cleared_at"]=_now();count+=1
 _save(path,data);return count

def context(workspace,limit=12):
 items=list_directives(workspace,True,limit)
 if not items:return "No active owner directives."
 return "\n".join("- ["+str(x.get("id",""))+"] "+str(x.get("text","")) for x in items)
