"""Owner-authored read-only task skills."""
import re
from pathlib import Path
def _root(workspace):
 root=Path(workspace).resolve()/".ai-house"/"skills";root.mkdir(parents=True,exist_ok=True);return root
def _parse(path):
 try:text=path.read_text(encoding="utf-8",errors="replace")[:4000]
 except OSError:return None
 lines=text.splitlines();roles=None;start=0
 if lines and lines[0].strip()=="---":
  end=next((i for i,line in enumerate(lines[1:],1) if line.strip()=="---"),None)
  if end is not None:
   for line in lines[1:end]:
    if line.lower().startswith("roles:"):
     raw=line.split(":",1)[1].strip().strip("[]")
     roles=[x.strip().strip("'\"") for x in raw.split(",") if x.strip()]
   start=end+1
 body="\n".join(lines[start:]);heading=next((line.lstrip("#").strip() for line in lines[start:] if line.startswith("#")),path.stem)
 return {"name":path.stem,"heading":heading,"roles":roles,"content":body[:4000]}
def list_skills(workspace):
 out=[];root=_root(workspace)
 try:paths=sorted(root.glob("*.md"),key=lambda p:p.name.lower())
 except OSError:paths=[]
 for path in paths:
  item=_parse(path)
  if item:out.append({"name":item["name"],"heading":item["heading"]})
 return out
def skills_for_role(workspace,role,task_text,limit=3):
 root=_root(workspace);words=set(re.findall(r"[a-z0-9]+",str(task_text).lower()));out=[]
 try:paths=sorted(root.glob("*.md"),key=lambda p:p.name.lower())
 except OSError:paths=[]
 for path in paths:
  item=_parse(path)
  if not item:continue
  if item["roles"] is not None and str(role).lower() not in [r.lower() for r in item["roles"]]:continue
  skill_words=set(re.findall(r"[a-z0-9]+",(item["name"]+" "+item["heading"]).lower()))
  if words.intersection(skill_words):out.append("### "+item["heading"]+"\n"+item["content"])
  if len(out)>=max(0,min(3,int(limit))):break
 return "\n\n".join(out) if out else "(no matching owner skills)"
