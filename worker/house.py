"""AI House terminal controls; standard library only."""
import json, os, sys, time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from approvals import answer, list_requests

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.getenv("AI_HOUSE_WORKSPACE",ROOT/"workspace")).resolve()
SD=WORK/".ai-house"
ROOMS=SD/"rooms.json"; CONTROL=SD/"control.json"; EVENTS=SD/"events.jsonl"; ACTIONS=SD/"actions.jsonl"
BUSINESSES=WORK/"businesses"
ACTIVE=os.getenv("AI_HOUSE_ACTIVE_HOURS","09:00-23:00")
USAGE="Usage: python worker/house.py {status|ls|pending|approve <id>|deny <id>|answer <id> <choice>|stop|start|watch|budget|outbox}"

def read_json(path,default):
 try:return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,ValueError,TypeError):return default

def room_list():
 data=read_json(ROOMS,{})
 rooms=data.get("rooms",[]) if isinstance(data,dict) else []
 return rooms if isinstance(rooms,list) else []

def room_state(room):
 p=Path(str(room.get("state_file","")))
 if not p.is_absolute():p=WORK/p
 return read_json(p,{})

def business(state):
 b=state.get("business")
 return str(b.get("name","") if isinstance(b,dict) else "") or "(no business)"

def active_hours():
 try:
  start,end=ACTIVE.split("-",1);now=datetime.now();minute=now.hour*60+now.minute
  def mins(value):
   h,m=value.strip().split(":");return int(h)*60+int(m)
  a,b=mins(start),mins(end)
  return a<=minute<b if a<b else minute>=a or minute<b
 except (ValueError,TypeError):return False

def status():
 control=read_json(CONTROL,{"running":True})
 print("House: "+("running" if control.get("running",True) else "stopped"))
 print("Inside active hours: "+("yes" if active_hours() else "no")+" ("+ACTIVE+")")
 for room in room_list():
  state=room_state(room)
  print(str(room.get("id","?"))+" | "+str(room.get("status","active"))+" | "+business(state))
 print("Pending approvals: "+str(len(list_requests(WORK,pending_only=True))))

def ls():
 for room in room_list():
  state=room_state(room);tasks=((state.get("roadmap") or {}).get("tasks") or []);counts=defaultdict(int)
  for task in tasks:counts[str(task.get("status","unknown"))]+=1
  summary=", ".join(k+"="+str(counts[k]) for k in sorted(counts)) or "no tasks"
  print(str(room.get("id","?"))+" | "+business(state)+" | "+summary)

def pending():
 items=list_requests(WORK,pending_only=True)
 if not items:print("No pending approvals.")
 for item in items:print(str(item.get("id",""))+" | "+str(item.get("room",""))+" | "+str(item.get("question","")))

def answer_cmd(request_id,choice):
 item=answer(WORK,request_id,choice);print("Answered "+item["id"]+": "+str(item["choice"]))

def control(running):
 SD.mkdir(parents=True,exist_ok=True);tmp=CONTROL.with_suffix(".tmp")
 tmp.write_text(json.dumps({"running":running,"updated_at":datetime.now().astimezone().isoformat()},indent=2),encoding="utf-8")
 tmp.replace(CONTROL);print("House "+("started." if running else "stopped."))

def watch():
 print("Watching new events (Ctrl+C to stop).");offset=EVENTS.stat().st_size if EVENTS.exists() else 0
 try:
  while True:
   try:
    with EVENTS.open("r",encoding="utf-8",errors="replace") as stream:
     stream.seek(offset)
     while True:
      line=stream.readline()
      if not line:offset=stream.tell();break
      offset=stream.tell()
      try:
       item=json.loads(line);at=item.get("at","");room=item.get("room","");event=item.get("event","event")
       fields={k:v for k,v in item.items() if k not in ("at","room","event")}
       print(str(at)+" | "+str(room)+" | "+str(event)+" | "+json.dumps(fields,ensure_ascii=False),flush=True)
      except ValueError:print(line.rstrip(),flush=True)
   except OSError:pass
   time.sleep(.25)
 except KeyboardInterrupt:print("\nStopped watching.")

def budget():
 totals=defaultdict(float)
 try:lines=ACTIONS.read_text(encoding="utf-8",errors="replace").splitlines()
 except OSError:lines=[]
 for line in lines:
  try:
   item=json.loads(line);totals[str(item.get("business","") or "(no business)")]+=float(item.get("cost_usd",0) or 0)
  except (ValueError,TypeError,AttributeError):continue
 if not totals:print("No recorded business spend.")
 for name in sorted(totals):print(name+" | $"+("{:.6f}".format(totals[name])))

def outbox():
 found=[];blocked={".ai-house",".git","node_modules",".venv","venv"}
 if BUSINESSES.is_dir():
  for business_dir in BUSINESSES.iterdir():
   if not business_dir.is_dir():continue
   for path in business_dir.rglob("*"):
    try:
     if not path.is_file() or any(part in blocked for part in path.parts):continue
     resolved=path.resolve();resolved.relative_to(WORK);stat=resolved.stat()
     found.append((stat.st_mtime,business_dir.name,str(resolved.relative_to(WORK)),stat.st_size))
    except (OSError,ValueError):continue
 found.sort(reverse=True)
 for modified,name,path,size in found[:20]:
  stamp=datetime.fromtimestamp(modified).astimezone().isoformat(timespec="minutes")
  print(name+" | "+path+" | "+str(size)+" bytes | "+stamp)
 if not found:print("No finished files found.")

def main(argv=None):
 args=list(sys.argv[1:] if argv is None else argv)
 if not args:print(USAGE);return 1
 cmd=args[0]
 try:
  if cmd=="status" and len(args)==1:status()
  elif cmd=="ls" and len(args)==1:ls()
  elif cmd=="pending" and len(args)==1:pending()
  elif cmd=="approve" and len(args)==2:answer_cmd(args[1],"yes")
  elif cmd=="deny" and len(args)==2:answer_cmd(args[1],"no")
  elif cmd=="answer" and len(args)==3:answer_cmd(args[1],args[2])
  elif cmd=="stop" and len(args)==1:control(False)
  elif cmd=="start" and len(args)==1:control(True)
  elif cmd=="watch" and len(args)==1:watch()
  elif cmd=="budget" and len(args)==1:budget()
  elif cmd=="outbox" and len(args)==1:outbox()
  else:print(USAGE);return 1
 except (OSError,ValueError,KeyError,TypeError) as error:
  print("Error: "+str(error),file=sys.stderr);return 1
 return 0

if __name__=="__main__":raise SystemExit(main())
