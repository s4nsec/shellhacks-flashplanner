/* ============ plan & replan ============ */
async function planDay(){
  if(!$("#city").value.trim()&&!$("#msg").value.trim()){
    formError("Add the city you’re visiting before we build your route.");
    return;
  }
  formError();
  if(S.busy)return;setBusy(true);traceReset();showView("loading");
  S.days=null;S.activeDay=0;
  try{
    const text=$("#msg").value.trim();
    if(!text){undoNotes();S.lastParsed=null;}
    else if(text!==S.lastParsed){
      traceStep({key:"parse",status:"run",title:"Read your extra notes",call:"gemini.generate_content(notes, schema=ParsedTrip)",source:"server/gemini.py: parse_trip()"});
      const t0=performance.now();const p=await postJSON("/api/parse",{message:text,city:$("#city").value.trim()});
      const used=applyNotes(p);S.lastParsed=text;
      const any=Object.keys(used).length;
      traceStep({key:"parse",status:"ok",ms:Math.round(performance.now()-t0),
        result:any?"Added from your notes where your settings were blank or silent:":"Your settings already cover everything in the notes, so they win.",
        detail:any?JSON.stringify(used,null,2):undefined});
    }
    const body=readForm();
    if(!body.city){formError("Add the city you’re visiting before we build your route.");return;}
    setStory(`Planning your day in ${body.city}…`);
    await stream("/api/plan",body,handleEvent);
  }catch(err){failRunning();setStory(err.message,true);}
  finally{setBusy(false);}
}
async function loadDemo(){
  if(S.busy)return;setBusy(true);traceReset();showView("loading");
  S.days=null;S.activeDay=0;
  try{
    traceStep({key:"demo",status:"run",title:"Load judge demo",call:"GET /api/demo",source:"server/main.py: demo_plan()"});
    const t0=performance.now();
    const r=await fetch("/api/demo");
    if(!r.ok)throw new Error(await errorText(r));
    S.plan=await r.json();S.sid=null;
    traceStep({key:"demo",status:"ok",result:"Loaded a static Montreal plan for no-key judging.",ms:Math.round(performance.now()-t0)});
    renderAll();
  }catch(err){failRunning();setStory(err.message,true);}
  finally{setBusy(false);}
}
function cityNow(p){  // the city's date and minutes after midnight, by this device's clock
  const d=new Date(Date.now()+p.utc_offset*60000);
  return {date:d.toISOString().slice(0,10),min:d.getUTCHours()*60+d.getUTCMinutes()};
}
const planIsToday=p=>!!p&&!p.demo&&p.utc_offset!=null&&cityNow(p).date===p.date;
function devicePosition(){
  if(!navigator.geolocation)return Promise.resolve(null);
  return new Promise(res=>navigator.geolocation.getCurrentPosition(
    g=>res({lat:g.coords.latitude,lng:g.coords.longitude}),()=>res(null),{timeout:8000,maximumAge:60000}));
}
async function replan(event,delay=30,preStep=null,placeId=null){
  if(S.busy||!S.sid)return;setBusy(true);traceReset();showView("loading");
  try{
    if(preStep)traceStep(preStep);
    const body={session_id:S.sid,event,delay_minutes:delay,place_id:placeId,client_time:new Date().toISOString()};
    if(planIsToday(S.plan)&&USES_POSITION.includes(event))Object.assign(body,await devicePosition());
    await stream("/api/replan",body,handleEvent);
  }catch(err){failRunning();setStory(err.message,true);}
  finally{setBusy(false);}
}
function handleEvent(e){
  if(e.type==="step")traceStep(e);
  else if(e.type==="plan"){
    if(e.multi_day){S.days=e.days;S.activeDay=0;S.plan=S.days[0];}
    else{S.plan=e;if(S.days)S.days[S.activeDay]=e;}
    S.sid=S.plan.session_id;renderAll();
  }
  else if(e.type==="error"){failRunning();setStory(e.message,true);}
}

