"""Persistent cooldowns for exhausted external search providers."""
import json
from datetime import datetime, timezone, timedelta

def _utc(value=None):
 value=value or datetime.now(timezone.utc)
 if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
 return value.astimezone(timezone.utc)
def _month_reset(now):
 now=_utc(now);year=now.year+(1 if now.month==12 else 0);month=1 if now.month==12 else now.month+1
 return datetime(year,month,1,tzinfo=timezone.utc)
def classify_search_failure(error,now=None):
 message=str(error).lower();now=_utc(now)
 if "monthly" in message and any(x in message for x in ("limit","quota","credit","usage","exhaust")):return "monthly_exhausted",_month_reset(now)
 if any(x in message for x in ("402","payment required","credit exhausted","credits exhausted","out of credits","insufficient credits","billing limit","prepaid credits","pre-paid credits","credit balance")):return "credits_exhausted",_month_reset(now)
 if any(x in message for x in ("429","rate limit","quota","usage limit","daily limit","monthly limit","resource_exhausted")):return "quota_limited",datetime(now.year,now.month,now.day,tzinfo=timezone.utc)+timedelta(days=1)
 if any(x in message for x in ("401","403","unauthorized","invalid api key","authentication failed","forbidden")):return "configuration_error",now+timedelta(days=1)
 if any(x in message for x in ("timeout","timed out","connection error","temporarily unavailable","503","502","500")):return "temporary_failure",now+timedelta(minutes=20)
 return "temporary_failure",now+timedelta(minutes=30)
def load_state(path):
 try:data=json.loads(path.read_text(encoding="utf-8"))
 except (OSError,ValueError):data={}
 return data if isinstance(data,dict) else {}
def save_state(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8");tmp.replace(path)
def provider_ready(path,provider,now=None):
 item=load_state(path).get(provider,{})
 try:until=datetime.fromisoformat(str(item.get("retry_after","")).replace("Z","+00:00"))
 except (ValueError,TypeError):return True
 return _utc(now)>=_utc(until)
def mark_failure(path,provider,error,now=None):
 reason,until=classify_search_failure(error,now);data=load_state(path);data[provider]={"reason":reason,"error":str(error)[:300],"retry_after":until.isoformat(),"updated_at":_utc(now).isoformat()};save_state(path,data);return data[provider]
def mark_success(path,provider):
 data=load_state(path)
 if provider in data:data.pop(provider,None);save_state(path,data)
def next_retry(path,providers,now=None):
 now=_utc(now);data=load_state(path);times=[]
 for provider in providers:
  try:until=_utc(datetime.fromisoformat(str(data.get(provider,{}).get("retry_after","")).replace("Z","+00:00")))
  except (ValueError,TypeError):continue
  if until>now:times.append(until)
 return min(times) if times else now+timedelta(minutes=30)
