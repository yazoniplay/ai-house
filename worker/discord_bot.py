"""Discord gateway bridge for the local AI House engine."""
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
  kind=str(kind)
  path=_alert_state_path(workspace)
  now=time.time()
  with _ALERT_LOCK:
   try:
    state=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state,dict):state={}
   except Exception:state={}
   previous=float(state.get(kind,0) or 0)
   if now-previous<_COOLDOWN_SECONDS:return
   state[kind]=now
   path.parent.mkdir(parents=True,exist_ok=True)
   tmp=path.with_suffix(".tmp")
   tmp.write_text(json.dumps(state,ensure_ascii=False),encoding="utf-8")
   tmp.replace(path)
  _ALERTS.put((str(workspace),kind,redact(str(text)[:1800])))
 except Exception:
  return

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
  except Exception as exc:
   _LOG.error("discord_bot_error %s",type(exc).__name__)
  time.sleep(next(delays,300))

async def _bot_session(workspace,command_handler,chat_handler,token):
 import discord
 channel_id=os.getenv("DISCORD_CHANNEL_ID","").strip()
 owner_id=os.getenv("DISCORD_OWNER_ID","").strip()
 intents=discord.Intents.default()
 intents.message_content=True
 client=discord.Client(intents=intents)
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
     except Exception:
      _ALERTS.put(item);break
    try:await channel.send(redact(message)[:1900])
    except Exception:
     _ALERTS.put(item);break
 @client.event
 async def on_ready():
  _LOG.info("discord_bot_ready")
 @client.event
 async def on_message(message):
  if message.author.bot or message.author.id==client.user.id:return
  if str(message.author.id)!=owner_id or str(message.channel.id)!=channel_id:return
  content=str(message.content or "")
  try:
   if content.startswith("!"):
    result=await asyncio.to_thread(command_handler,content)
   elif chat_handler is not None:
    async with message.channel.typing():
     result=await asyncio.to_thread(chat_handler,content)
   else:return
   reply=redact(str(result or ""))[:1900]
   if reply:await message.reply(reply,mention_author=False)
  except Exception as exc:
   safe=redact("Request failed ("+type(exc).__name__+")")[:1900]
   try:await message.reply(safe,mention_author=False)
   except Exception:_LOG.error("discord_bot_error message_reply %s",type(exc).__name__)
 drain_task=asyncio.create_task(drain_alerts())
 try:
  await client.start(token,reconnect=False)
 finally:
  drain_task.cancel()
  try:await drain_task
  except asyncio.CancelledError:pass
  await client.close()
