"""Normalize autonomous room missions and department leadership."""
ROOM_DEPARTMENTS={
 "coding":{"department":"Product Engineering","semi_leader":"Engineering Lead","role":"Computer nerd / senior software engineer","responsibilities":["turn the selected business problem into a useful product","delegate coding, architecture, UX and QA tasks","request desktop execution when a configured app materially helps"]},
 "studio":{"department":"Studio & Content","semi_leader":"Creative Producer","role":"Video producer and creative director","responsibilities":["own YouTube concept, script, visuals and finished video package","coordinate marketing assets with the Marketing Room","request Computer Room production work when an app is needed"]},
 "marketing":{"department":"Marketing & Growth","semi_leader":"Marketing Specialist","role":"Growth and campaign specialist","responsibilities":["own positioning, campaign strategy and channel plans","create landing copy, social drafts and campaign assets","request Computer Room work for design, editing or production"]},
 "computer":{"department":"Computer Room / Desktop Operations","semi_leader":"Desktop Operations Lead","role":"Computer nerd / desktop automation specialist","responsibilities":["execute immediate structured handoffs from other rooms","operate only configured app aliases in the AI House workspace","save tangible local deliverables and return completion evidence","pause for owner approval on risky actions"]}
}
def room_org_chart():
 return {key:{"department":value["department"],"semi_leader":value["semi_leader"],"role":value["role"],"responsibilities":list(value["responsibilities"])} for key,value in ROOM_DEPARTMENTS.items()}

def _text(value,fallback,limit=1200):
 value=" ".join(str(value or "").split()).strip()
 return (value or fallback)[:limit]
def default_room_plan(business,cycle=1):
 b=business if isinstance(business,dict) else {}
 name=_text(b.get("name"),"AI House selected opportunity",140);customer=_text(b.get("customer"),"the target customer",240);problem=_text(b.get("problem"),"a repeated customer workflow problem",800);solution=_text(b.get("solution"),"a focused solution to the customer problem",1200);product=(name+" Workflow Companion")[:160]
 return {"coding_product":{"title":product,"target_user":customer,"problem":problem,"brief":"Build a focused, usable first version around this internally selected opportunity. Core concept: "+solution+". Keep one excellent workflow, include setup instructions, tests, and a clear value proposition. AI House selected this concept from its current business research; no owner product selection is required.","success_metric":"At least 5 target users complete the core workflow and provide genuine feedback; do not fabricate usage."},"youtube":{"title":name+": solving "+problem[:90],"brief":"AI-selected original video concept for business cycle "+str(cycle)+". Audience: "+customer+". Explain the real problem, show a practical solution, cite current evidence from the business research, and deliver a complete original video package. Do not publish without the configured approval gate."},"marketing":{"title":name+" — launch campaign","brief":"AI-selected launch campaign for cycle "+str(cycle)+". Audience: "+customer+". Create truthful positioning, landing-page copy, channel-specific content drafts, a launch calendar, and measurable organic feedback experiments. No spam, fake testimonials, or unapproved outreach."},"computer":{"mission":"Create and save a polished local production asset for the AI-selected "+product+" concept, such as a presentation, visual mockup, or working draft in the configured desktop application. Work only in the dedicated AI House workspace. Do not publish, send, upload, purchase, delete, install, or change account/security settings."}}
def normalize_room_plan(business,generated=None,cycle=1):
 fallback=default_room_plan(business,cycle);source=generated if isinstance(generated,dict) else {};result={}
 for key in ("coding_product","youtube","marketing","computer"):
  raw=source.get(key) if isinstance(source.get(key),dict) else {};result[key]={}
  for field,value in fallback[key].items():result[key][field]=_text(raw.get(field),value,4000 if field in ("brief","mission") else 1600)
 result["computer"]["mission"]=("AI House-selected local mission: "+result["computer"]["mission"][:1800]+" Only use configured application aliases and save drafts inside the designated AI House workspace. Never publish, send, upload, purchase, delete, install, or modify account/security settings. Pause for owner approval if an action is classified as risky.")[:4000]
 return result
