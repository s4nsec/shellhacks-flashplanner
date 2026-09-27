/* ============ form ============ */
function renderChips(){
  $("#chips").innerHTML=S.tags.map(t=>`<button type="button" class="chip" data-tag="${esc(t)}">${esc(t[0].toUpperCase()+t.slice(1))}</button>`).join("");
  syncForm();
}
function syncForm(){
  $$(".chip").forEach(c=>{const t=c.dataset.tag,st=S.likes.has(t)?"like":S.skips.has(t)?"skip":"";c.dataset.state=st;c.setAttribute("aria-pressed",String(st==="like"));});
  $$("#modeSeg button").forEach(b=>b.setAttribute("aria-pressed",b.dataset.mode===S.mode));
  $$("#styleSeg button").forEach(b=>b.setAttribute("aria-pressed",(b.dataset.blocks==="1")===S.blocks));
}
$("#chips").addEventListener("click",e=>{const c=e.target.closest(".chip");if(!c)return;const t=c.dataset.tag;
  if(S.likes.has(t))S.likes.delete(t);else if(S.skips.has(t))S.skips.delete(t);else S.likes.add(t);syncForm();});  // one tap on, one tap off
$("#modeSeg").addEventListener("click",e=>{const b=e.target.closest("button");if(b){S.mode=b.dataset.mode;syncForm();}});
$("#styleSeg").addEventListener("click",e=>{const b=e.target.closest("button");if(b){S.blocks=b.dataset.blocks==="1";syncForm();}});
// Typed interests become loved chips; one that is already a chip is just loved.
function addInterests(){
  const xs=splitList($("#moreInterests").value);if(!xs.length)return;
  xs.forEach(x=>{let t=S.tags.find(q=>norm(q)===norm(x));
    if(!t){t=x;S.tags.push(t);}S.skips.delete(t);S.likes.add(t);});
  $("#moreInterests").value="";renderChips();
}
$("#moreInterests").addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===","){e.preventDefault();addInterests();}});
$("#moreInterests").addEventListener("change",addInterests);
renderChips();

const addDays=(iso,n)=>{const d=new Date(iso+"T00:00Z");d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
// The day count comes from the From–To range, up to a week; a blank To is a one-day trip.
function tripDays(){
  const from=$("#date").value,to=$("#dateTo").value;
  if(!from||!to)return 1;
  return Math.max(1,Math.min(7,Math.round((Date.parse(to)-Date.parse(from))/864e5)+1));
}
function syncDayWindows(values=[]){
  const from=$("#date").value,n=tripDays();
  $("#dateTo").min=from;$("#dateTo").max=from?addDays(from,6):"";
  if(from&&$("#dateTo").value)$("#dateTo").value=addDays(from,n-1);
  if(n>1)showDateRange();  // a range from the notes needs the date fields visible
  const old=$$("#dayWindows .day-window").map(r=>({start_time:r.querySelector(".day-start").value,end_time:r.querySelector(".day-end").value}));
  if(n===1){$("#dayWindows").innerHTML="";return;}
  $("#dayWindows").innerHTML=Array.from({length:n},(_,i)=>{const w=values[i]||old[i]||{start_time:$("#tStart").value||"10:00",end_time:$("#tEnd").value||"19:00"};return `<div class="day-window"><b>Day ${i+1}</b><label>Start<input class="day-start" type="time" value="${esc(w.start_time)}"></label><label>Finish<input class="day-end" type="time" value="${esc(w.end_time)}"></label></div>`;}).join("");
}
$("#date").addEventListener("change",()=>syncDayWindows());
$("#dateTo").addEventListener("change",()=>syncDayWindows());

const norm=s=>s.toLowerCase().trim().replace(/s$/,"");
// Notes only fill what the settings leave open: blank fields, new interests, must-sees and bookings.
// What they added is remembered, so editing or clearing the notes takes it back out.
function undoNotes(){
  const a=S.fromNotes;S.fromNotes=null;S.appointments=[];S.meals=null;S.autoBreaks=true;
  if(!a)return;
  a.likes.forEach(t=>S.likes.delete(t));a.skips.forEach(t=>S.skips.delete(t));
  S.tags=S.tags.filter(t=>!a.added.includes(t));
  const drop=(id,xs)=>{const gone=new Set(xs.map(norm));$(id).value=splitList($(id).value).filter(x=>!gone.has(norm(x))).join(", ");};
  drop("#mustSee",a.must);
  if(a.wheelchair)$("#wheelchair").checked=false;
  if(a.diet)$("#diet").value="";
  if(a.days){$("#dateTo").value="";syncDayWindows();}
  renderChips();
}
function applyNotes(p){
  undoNotes();
  const a={likes:[],skips:[],added:[],must:[]},used={};
  const fill=(id,v,key)=>{if(!v||$(id).value.trim())return false;$(id).value=v;used[key]=v;return true;};
  fill("#city",p.city,"city");fill("#date",p.date,"date");
  if(fill("#startLoc",p.start_location,"start_location"))StartAC.clear();
  if(fill("#endLoc",p.end_location,"end_location"))EndAC.clear();
  if(p.budget!=null&&$("#budget").value===""){$("#budget").value=p.budget;used.budget=p.budget;}
  const known=new Set([...S.likes,...S.skips].map(norm));
  const addTags=(xs,set,tags,key)=>{
    xs.forEach(x=>{if(known.has(norm(x)))return;known.add(norm(x));let t=S.tags.find(q=>norm(q)===norm(x));
      if(!t){t=x;S.tags.push(t);a.added.push(t);}set.add(t);tags.push(t);});
    if(tags.length)used[key]=tags;};
  addTags(p.loves||[],S.likes,a.likes,"loves");
  addTags(p.skips||[],S.skips,a.skips,"skips");
  const must=splitList($("#mustSee").value);
  (p.must_see||[]).forEach(x=>{if(!must.some(m=>norm(m)===norm(x))){must.push(x);a.must.push(x);}});
  $("#mustSee").value=must.join(", ");
  if(a.must.length)used.must_see=a.must;
  S.appointments=p.appointments||[];
  if(S.appointments.length)used.appointments=S.appointments;
  a.wheelchair=Boolean(p.wheelchair_accessible)&&!$("#wheelchair").checked;
  if(a.wheelchair){$("#wheelchair").checked=true;used.wheelchair_accessible=true;}
  const diet=(p.dietary_preferences||[]).includes("vegan")?"vegan":
    (p.dietary_preferences||[]).includes("vegetarian")?"vegetarian":"";
  a.diet=diet&&!$("#diet").value;
  if(a.diet){$("#diet").value=diet;used.dietary_preferences=[diet];}
  a.days=(p.days||1)>1&&tripDays()===1;
  if(a.days){if(!$("#date").value)$("#date").value=new Date().toLocaleDateString("en-CA");
    $("#dateTo").value=addDays($("#date").value,p.days-1);syncDayWindows(p.day_windows||[]);
    used.days=p.days;if((p.day_windows||[]).length)used.day_windows=p.day_windows;}
  // Meals and the coffee break come only from the notes; Gemini defaults them to lunch, dinner and a break.
  if(Array.isArray(p.meals)){S.meals=p.meals;
    if(p.meals.map(m=>m.name+m.time).join()!=="lunch12:30,dinner19:00")used.meals=p.meals;}
  if(p.auto_breaks===false){S.autoBreaks=false;used.auto_breaks=false;}
  S.fromNotes=a;renderChips();
  return used;
}
function readForm(){
  const days=tripDays();
  return {city:$("#city").value.trim(),date:$("#date").value||null,
    start_time:$("#tStart").value||"10:00",end_time:$("#tEnd").value||"19:00",
    start_location:$("#startLoc").value.trim()||null,start_place:S.startPlace,
    end_location:$("#endLoc").value.trim()||null,end_place:S.endPlace,
    loves:[...S.likes],skips:[...S.skips],
    must_see:splitList($("#mustSee").value),appointments:S.appointments,days,
    day_windows:$$("#dayWindows .day-window").map(r=>({start_time:r.querySelector(".day-start").value,end_time:r.querySelector(".day-end").value})),
    wheelchair_accessible:$("#wheelchair").checked,
    dietary_preferences:$("#diet").value?[$("#diet").value]:[],
    pace:$("#pace").value,getting_around:S.mode,
    budget:$("#budget").value===""?null:Math.max(0,Math.round(Number($("#budget").value))),
    by_neighborhood:S.blocks,...(S.meals?{meals:S.meals}:{}),auto_breaks:S.autoBreaks!==false,notes:$("#msg").value.trim(),user_list:$("#userList").value.split("\n").map(x=>x.replace(/^\s*(\d+[.)]|[-*•])\s*/,"").trim()).filter(Boolean)};
}

