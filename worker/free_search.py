"""Parse DuckDuckGo HTML results for a no-key search fallback."""
from html.parser import HTMLParser
from urllib.parse import urlparse,parse_qs,unquote
class _Results(HTMLParser):
 def __init__(self):
  super().__init__();self.items=[];self.current=None;self.capture=None;self.snippet_depth=0
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs);classes=set(str(attrs.get("class","")).split())
  if tag=="a" and "result__a" in classes:
   url=str(attrs.get("href",""));parsed=urlparse(url)
   if parsed.netloc.endswith("duckduckgo.com") and parsed.path=="/l/":url=unquote(parse_qs(parsed.query).get("uddg",[""])[0])
   self.current={"title":"","url":url,"content":""};self.capture="title"
  elif self.items and ("result__snippet" in classes or "result__body" in classes) and tag in ("a","div","td"):
   self.capture="snippet";self.snippet_depth=1
  elif self.capture=="snippet" and tag in ("a","div","td"):self.snippet_depth+=1
 def handle_endtag(self,tag):
  if self.current and self.capture=="title" and tag=="a":
   self.items.append(self.current);self.current=None;self.capture=None
  elif self.capture=="snippet" and tag in ("a","div","td"):
   self.snippet_depth-=1
   if self.snippet_depth<=0:self.capture=None
 def handle_data(self,data):
  value=" ".join(str(data).split())
  if not value:return
  if self.current and self.capture=="title":self.current["title"]=(self.current["title"]+" "+value).strip()
  elif self.capture=="snippet" and self.items:self.items[-1]["content"]=(self.items[-1].get("content","")+" "+value).strip()[:700]
def parse_results(html,limit=5):
 parser=_Results();parser.feed(str(html));output=[];seen=set()
 for item in parser.items:
  url=str(item.get("url","")).strip()
  if not url.startswith(("http://","https://")) or url in seen:continue
  seen.add(url);output.append({"title":item.get("title","")[:300],"url":url,"content":item.get("content","")[:700],"published_date":None})
  if len(output)>=max(1,int(limit)):break
 return output
