"""Owner-only Discord mobile command center for AI House."""
import asyncio
import json
import logging
import os
import queue
import re
import threading
import time
from datetime import datetime
from pathlib import Path

_LOG=logging.getLogger(__name__)
_ALERTS=queue.Queue()
_START_LOCK=threading.Lock()
_STARTED=False
_ALERT_LOCK=threading.Lock()
_COOLDOWN_SECONDS=1800
_RETRY_DELAYS=(30,60,120,300)
_SECRET_RE=re.compile(r"(?:sk-|sb_|tvly-|AIza|nvapi-|gsk_)[A-Za-z0-9_-]*|[A-Za-z0-9_-]{40,}")

def redact(text):
 value=str(text)
 for name in ("DISCORD_BOT_TOKEN","DISCORD_CHANNEL_ID","DISCORD_OWNER_ID"):
  secret=os.getenv(name,"")
  if secret:value=value.replace(secret,"[redacted]")
 return _SECRET_RE.sub("[redacted]",value)

def _alert_state_path(workspace):
 return Path(workspace).resolve()/".ai-house"/"discord_alert_state.json"

def enqueue_alert(workspace,kind,text):
 try:
  kind=str(kind);path=_alert_state_path(workspace);now=time.time()
  with _ALERT_LOCK:
   try:
    state=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state,dict):state={}
   except Exception:state={}
   previous=float(state.get(kind,0) or 0)
   if now-previous<_COOLDOWN_SECONDS:return
   state[kind]=now;path.parent.mkdir(parents=True,exist_ok=True)
   tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(state,ensure_ascii=False),encoding="utf-8");tmp.replace(path)
  _ALERTS.put((str(workspace),kind,redact(str(text)[:1800])))
 except Exception:return

def _alert_state(workspace):
 path=_alert_state_path(workspace)
 try:
  data=json.loads(path.read_text(encoding="utf-8"))
  return data if isinstance(data,dict) else {}
 except Exception:return {}

def _save_alert_state(workspace,data):
 path=_alert_state_path(workspace);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8");tmp.replace(path)

def _mark_alert_sent(workspace,kind):
 try:
  with _ALERT_LOCK:
   state=_alert_state(workspace);sent=state.setdefault("_sent",{})
   if not isinstance(sent,dict):sent={}
   sent[str(kind)]=time.time();state["_sent"]=sent;_save_alert_state(workspace,state)
 except Exception:return

def _was_alert_sent(workspace,kind):
 try:return float(_alert_state(workspace).get("_sent",{}).get(str(kind),0) or 0)>0
 except Exception:return False

def _needs_alert_delivery(workspace,kind,created_at):
 try:
  sent=float(_alert_state(workspace).get("_sent",{}).get(str(kind),0) or 0)
  created=datetime.fromisoformat(str(created_at).replace("Z","+00:00")).timestamp()
  return sent<created
 except Exception:return True

def parse_approval_alert(message):
 match=re.search(r"!approve\s+([0-9a-fA-F]+).*?!deny\s+([0-9a-fA-F]+)",str(message),re.S)
 return match.group(1) if match and match.group(1)==match.group(2) else None

def parse_brief_alert(message):
 match=re.search(r"!brief\s+([0-9a-fA-F]+)",str(message))
 return match.group(1) if match else None

def start_discord_bot(workspace,command_handler,chat_handler=None):
 global _STARTED
 token=os.getenv("DISCORD_BOT_TOKEN","").strip()
 if not token:return
 with _START_LOCK:
  if _STARTED:return
  _STARTED=True
 thread=threading.Thread(target=_thread_main,args=(str(workspace),command_handler,chat_handler,token),name="ai-house-discord",daemon=True)
 thread.start()

def _thread_main(workspace,command_handler,chat_handler,token):
 delays=iter(_RETRY_DELAYS)
 while True:
  try:
   asyncio.run(_bot_session(workspace,command_handler,chat_handler,token))
   _LOG.error("discord_bot_error connection ended")
  except Exception as exc:_LOG.error("discord_bot_error %s",type(exc).__name__)
  time.sleep(next(delays,300))

async def _bot_session(workspace,command_handler,chat_handler,token):
 import discord
 channel_id=os.getenv("DISCORD_CHANNEL_ID","").strip()
 owner_id=os.getenv("DISCORD_OWNER_ID","").strip()
 intents=discord.Intents.default();intents.message_content=True
 client=discord.Client(intents=intents)

 class ChoiceView(discord.ui.View):
  def __init__(self,request_id,options,owner,answer_command="!answer"):
   super().__init__(timeout=None)
   self.request_id=str(request_id);self.owner=str(owner);self.answer_command=str(answer_command)
   for index,option in enumerate(list(options)[:5]):
    label=str(option).strip()[:80] or "Option "+str(index+1)
    button=discord.ui.Button(label=label,style=discord.ButtonStyle.primary if index==0 else discord.ButtonStyle.secondary,custom_id="aihouse:"+self.request_id+":"+str(index))
    button.callback=self._callback(index)
    self.add_item(button)
  def _callback(self,index):
   async def callback(interaction):
    if str(interaction.user.id)!=self.owner:
     await interaction.response.send_message("Only the AI House owner can answer this.",ephemeral=True);return
    await interaction.response.defer()
    result=await asyncio.to_thread(command_handler,self.answer_command+" "+self.request_id+" "+str(index))
    await interaction.message.edit(content=redact(str(result))[:1800],view=None)
    if chat_handler is not None and str(result).startswith("Answered "):
     follow=await asyncio.to_thread(chat_handler,"The owner answered request "+self.request_id+" with option "+str(index)+". Continue from that answer and ask another question only if necessary.")
     await send_payload(interaction.channel,follow)
   return callback

 async def send_payload(channel,payload):
  if isinstance(payload,dict):
   content=redact(str(payload.get("message") or payload.get("reply") or "Leader response"))[:1200]
   req=payload.get("request")
   if isinstance(req,dict) and req.get("id") and req.get("options"):
    content+="\n\nDecision needed: "+str(req.get("question",""))[:500]
    if req.get("summary"):content+="\n"+str(req.get("summary",""))[:400]
    view=ChoiceView(req["id"],req["options"],owner_id)
    client.add_view(view)
    await channel.send(content[:1800],view=view)
    if req.get("kind")=="leader_question":_mark_alert_sent(workspace,"leader_question:"+str(req["id"]))
    return
   await channel.send(content);return
  content=redact(str(payload or ""))[:1800]
  if content:await channel.send(content)

 async def drain_alerts():
  while not client.is_closed():
   await asyncio.sleep(2)
   while True:
    try:item=_ALERTS.get_nowait()
    except queue.Empty:break
    item_workspace,kind,message=item
    if str(Path(item_workspace).resolve())!=str(Path(workspace).resolve()):
     _ALERTS.put(item);break
    channel=client.get_channel(int(channel_id)) if channel_id.isdigit() else None
    if channel is None:
     try:channel=await client.fetch_channel(int(channel_id))
     except Exception:_ALERTS.put(item);break
    try:
     request_id=parse_approval_alert(message)
     if request_id:
      if _was_alert_sent(workspace,kind):continue
      view=ChoiceView(request_id,["yes","no"],owner_id,"!answer")
      client.add_view(view)
      await channel.send(redact(message)[:1700],view=view)
      _mark_alert_sent(workspace,kind)
     else:
      brief_id=parse_brief_alert(message)
      if brief_id:
       if _was_alert_sent(workspace,kind):continue
       raw_brief=await asyncio.to_thread(command_handler,"!brief-json "+brief_id)
       brief=json.loads(str(raw_brief))
       view=ChoiceView(brief_id,brief.get("options",[]),owner_id,"!brief-answer")
       client.add_view(view)
       await channel.send(redact(message)[:1700],view=view)
       _mark_alert_sent(workspace,kind)
      else:await channel.send(redact(message)[:1900])
    except Exception:_ALERTS.put(item);break

 @client.event
 async def on_ready():
  _LOG.info("discord_bot_ready")
  try:
   pending_raw=await asyncio.to_thread(command_handler,"!discord-pending-json")
   pending=json.loads(str(pending_raw))
   target=client.get_channel(int(channel_id)) if channel_id.isdigit() else None
   if target is None and channel_id.isdigit():
    try:target=await client.fetch_channel(int(channel_id))
    except Exception:target=None
   for request in pending if isinstance(pending,list) else []:
    if not request.get("id") or not request.get("options"):continue
    answer_command=request.get("answer_command","!answer")
    view=ChoiceView(request["id"],request["options"],owner_id,answer_command)
    client.add_view(view)
    req_id=str(request["id"]);req_kind=str(request.get("kind",""))
    if request.get("alert_kind")=="brief":
     alert_kind="brief:"+req_id
     content="Owner choice needed\n"+str(request.get("question",""))+"\n"+str(request.get("context",""))+"\n!brief "+req_id
    elif req_kind=="leader_question":
     alert_kind="leader_question:"+req_id
     content="Leader needs your decision\n"+str(request.get("question",""))+"\n"+str(request.get("summary",""))
    else:
     alert_kind=("desktop_approval:" if req_kind.startswith("desktop_action_") else "approval_needed:")+req_id
     content="AI House needs your approval\n"+str(request.get("question",""))+"\n"+str(request.get("summary",""))+"\n!approve "+req_id+"\n!deny "+req_id
     view=ChoiceView(req_id,["yes","no"],owner_id,"!answer");client.add_view(view)
    if target is not None and _needs_alert_delivery(workspace,alert_kind,request.get("created_at","")):
     await target.send(redact(content)[:1700],view=view)
     _mark_alert_sent(workspace,alert_kind)
   _LOG.info("discord_persistent_views_registered count=%s",len(pending) if isinstance(pending,list) else 0)
  except Exception as view_error:_LOG.error("discord_persistent_views_error %s",type(view_error).__name__)
 @client.event
 async def on_message(message):
  if message.author.bot or message.author.id==client.user.id:return
  if str(message.author.id)!=owner_id or str(message.channel.id)!=channel_id:return
  content=str(message.content or "")
  try:
   if content.startswith("!"):result=await asyncio.to_thread(command_handler,content)
   elif chat_handler is not None:
    async with message.channel.typing():result=await asyncio.to_thread(chat_handler,content)
   else:return
   await send_payload(message.channel,result)
  except Exception as exc:
   safe=redact("Request failed ("+type(exc).__name__+")")[:1900]
   try:await message.reply(safe,mention_author=False)
   except Exception:_LOG.error("discord_bot_error message_reply %s",type(exc).__name__)
 drain_task=asyncio.create_task(drain_alerts())
 try:await client.start(token,reconnect=False)
 finally:
  drain_task.cancel()
  try:await drain_task
  except asyncio.CancelledError:pass
  await client.close()
