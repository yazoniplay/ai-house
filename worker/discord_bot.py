"""Owner-only Discord mobile command center for AI House."""
import asyncio
import json
import logging
import os
import queue
import re
import threading
import time
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

def parse_approval_alert(message):
 match=re.search(r"!approve\s+([0-9a-fA-F]+).*?!deny\s+([0-9a-fA-F]+)",str(message),re.S)
 return match.group(1) if match and match.group(1)==match.group(2) else None

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
  def __init__(self,request_id,options,owner):
   super().__init__(timeout=None)
   self.request_id=str(request_id);self.owner=str(owner)
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
    result=await asyncio.to_thread(command_handler,"!answer "+self.request_id+" "+str(index))
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
    await channel.send(content[:1800],view=view);return
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
      view=ChoiceView(request_id,["yes","no"],owner_id)
      client.add_view(view)
      await channel.send(redact(message)[:1700],view=view)
     else:await channel.send(redact(message)[:1900])
    except Exception:_ALERTS.put(item);break

 @client.event
 async def on_ready():
  _LOG.info("discord_bot_ready")
  try:
   pending_raw=await asyncio.to_thread(command_handler,"!pending-json")
   pending=json.loads(str(pending_raw))
   for request in pending if isinstance(pending,list) else []:
    if request.get("id") and request.get("options"):
     client.add_view(ChoiceView(request["id"],request["options"],owner_id))
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
