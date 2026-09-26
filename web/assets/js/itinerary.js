/* ============ rendering ============ */
function renderAll(){
  setStory(S.plan.story||"");
  renderDayTabs();renderItin();
  const maps=$("#mapsBtn"),stops=planStops(S.plan);
  maps.href=googleMapsUrl(S.plan);maps.setAttribute("aria-disabled","false");
  maps.title=stops.length>9?"Google Maps supports up to 9 waypoints; this link includes the first 9.":"Open this route in Google Maps";
  $("#icsBtn").disabled=false;
  $("#copyBtn").disabled=!S.plan;
  renderHeading();
  showView("results",false);
  Sheet.open();
  MapView.draw(S.plan);
  $("#resultsTitle").setAttribute("tabindex","-1");$("#resultsTitle").focus({preventScroll:true});
}
// A short title and one glanceable line; the full summary sits in the sheet body.
function renderHeading(){
  const p=S.plan,sm=p.summary,many=S.days&&S.days.length>1;
  $("#resultsTitle").textContent=many?`Day ${S.activeDay+1} in ${p.city}`:`Your day in ${p.city}`;
  $("#glance").textContent=`${sm.stops} stop${sm.stops===1?"":"s"} · back ${fmt(p.end)} · ${sm.walk_km.toFixed(1)} km walking`;
}
function renderDayTabs(){
  const box=$("#dayTabs"),many=S.days&&S.days.length>1;box.hidden=!many;
  if(!many){box.innerHTML="";return;}
  box.innerHTML=S.days.map((p,i)=>`<button type="button" data-day="${i}" aria-pressed="${i===S.activeDay}">Day ${i+1} · ${esc(p.date)}</button>`).join("");
}
$("#dayTabs").addEventListener("click",e=>{const b=e.target.closest("button[data-day]");if(!b)return;S.activeDay=Number(b.dataset.day);S.plan=S.days[S.activeDay];S.sid=S.plan.session_id;renderAll();});
function legText(L){
  if(L.mode==="walk")return `Walk ${L.min} min, ${L.km.toFixed(1)} km`;
  if(L.mode==="ride"){const f=L.fare;return `Ride ${L.min} min (incl. pickup)${f?`, est. $${f.low.toFixed(0)}–$${f.high.toFixed(0)}`:""}`;}
  return `Transit ${L.min} min`;
}
const NO_PUTBACK=["Closed that day","Its hours don't fit your time window"];  // forcing can't help these
function renderItin(){
  const p=S.plan,all=p.completed.concat(p.stops),heads=new Map();
  let prevZone=null;all.forEach((st,i)=>{if(p.blocks.length&&st.zone!==prevZone){
    const blk=all.slice(i);let n=0;while(n<blk.length&&blk[n].zone===st.zone)n++;
    heads.set(i,{zone:st.zone,from:st.begin,to:blk[n-1].leave,count:n});}prevZone=st.zone;});
  const rows=[];
  const legRow=(L,done)=>`<li class="leg${done?" done":""}" data-mode="${L.mode}"><span></span><span class="rail"></span><div class="tx">${legText(L)}</div></li>`;
  const zoneRow=(b,done)=>`<li class="zone${done?" done":""}"><span></span><span class="rail"></span><div class="zn"><b>${esc(b.zone)}</b><span>${fmt(b.from)} to ${fmt(b.to)}, ${b.count} stop${b.count>1?"s":""}</span></div></li>`;
  const stn=(st,num)=>{
    const tags=[];
    if(st.new)tags.push(`<span class="tag new">New</span>`);
    if(st.notes.includes("breakfast"))tags.push(`<span class="tag gold">Breakfast slot</span>`);
    if(!st.done&&st.locked&&!st.fixed)tags.push(`<span class="tag">${st.must?"Must-see":"Locked"}</span>`);
    if(st.notes.includes("lunch"))tags.push(`<span class="tag gold">Lunch slot</span>`);
    if(st.notes.includes("dinner"))tags.push(`<span class="tag gold">Dinner slot</span>`);
    if(st.notes.includes("break"))tags.push(`<span class="tag gold">Coffee break</span>`);
    if(st.notes.includes("golden"))tags.push(`<span class="tag gold">Golden hour</span>`);
    if(st.notes.includes("appointment"))tags.push(`<span class="tag gold">Fixed time</span>`);
    if(st.notes.includes("rain"))tags.push(`<span class="tag rain">${st.setting==="outdoor"?"Outdoors":st.setting==="covered"?"Covered":"Indoors"}</span>`);
    tags.push(`<span class="tag">${esc(st.kind)}</span>`);
    let meta=`${hm(st.visit.minutes)} here`;
    if(st.visit.extra>0)meta+=` (${st.visit.extra} min extra instead of waiting later)`;
    if(st.wait>0&&st.opens!=null)meta+=`, opens ${fmt(st.opens)} so ${st.wait} min wait`;
    else if(st.wait>0)meta+=`, ${st.wait} min wait`;
    if(st.rating)meta+=`. Rated ${st.rating.toFixed(1)} (${(st.count||0).toLocaleString()})`;
    if(st.price)meta+=`${st.rating?" · ":". "}${priceText(st.price)}`;
    const v=st.visit,quotes=(v.evidence||[]).filter(x=>x.quote),of=((v.evidence||[]).find(x=>x.of)||{}).of||quotes.length;
    const paced=v.minutes-(v.extra||0)!==v.base?`, adjusted for ${esc(p.trip.pace)} pace`:"";
    let rv="";
    if(!st.done){
      if(v.source==="reviews"&&quotes.length)rv=`<details class="rv"><summary>Reviewers suggest ${hm(v.base)} (${quotes.length} of ${of} reviews)${paced}</summary><ul>${quotes.map(q=>`<li>“${esc(q.quote)}”<cite>${q.uri?`<a href="${esc(q.uri)}" target="_blank" rel="noopener">${esc(q.author)}</a>`:esc(q.author)}, Google review</cite></li>`).join("")}</ul></details>`;
      else if(v.source==="gemini")rv=`<div class="rv">No review mentions time, so Gemini estimated ${hm(v.base)}${paced}</div>`;
      else rv=`<div class="rv">Typical visit length for a ${esc(st.kind)}${paced}</div>`;
    }
    const name=st.maps_uri?`<a href="${esc(st.maps_uri)}" target="_blank" rel="noopener">${esc(st.name)}</a>`:esc(st.name);
    return `<li class="stn${st.done?" done":""}${st.new?" new":""}"><span class="tm">${fmt(st.begin)}</span><span class="rail"><span class="dot">${st.done?"✓":num}</span></span><div class="body"><div class="nm">${st.done||!S.sid?"":`<button class="lock${st.locked?" on":""}" data-id="${esc(st.id)}" data-locked="${st.locked?1:0}"${st.must||st.fixed?" disabled":""} title="${st.fixed?"Fixed-time plan from your request":st.must?"Must-see from your request":st.locked?"Let re-plans drop this stop":"Keep this stop through re-plans"}">${st.locked?"🔒 Locked":"Lock"}</button>`}${name}</div><div class="meta">${meta}</div>${!st.done&&st.reason?`<div class="why">${esc(st.reason)}</div>`:""}${rv}<div class="tags">${tags.join("")}</div></div></li>`;
  };
  rows.push(`<li class="term"><span class="tm">${fmt(p.depart??p.start)}</span><span class="rail"><span class="dot">H</span></span><div class="body"><div class="nm">${esc(p.hotel.name)}</div><div class="meta">Leave</div></div></li>`);
  let n=0;
  p.completed.forEach((st,i)=>{rows.push(legRow(st.leg,true));if(heads.has(i))rows.push(zoneRow(heads.get(i),true));rows.push(stn(st,++n));});
  if(p.completed.length||p.shifted||p.here)rows.push(`<li class="now"><span class="tm">${fmt(p.now)}</span><span class="rail"><span class="dot"></span></span><div class="body"><div class="nm">You are here</div><div class="meta">${p.shifted?"Running behind the original plan":"Re-planning from this point"}</div></div></li>`);
  p.stops.forEach((st,i)=>{rows.push(legRow(st.leg,false));const k=p.completed.length+i;if(heads.has(k))rows.push(zoneRow(heads.get(k),false));rows.push(stn(st,++n));});
  rows.push(legRow(p.back,false));
  const endsAtStart=p.end_location.lat===p.hotel.lat&&p.end_location.lng===p.hotel.lng;
  rows.push(`<li class="term"><span class="tm">${fmt(p.end)}</span><span class="rail"><span class="dot">${endsAtStart?"H":"E"}</span></span><div class="body"><div class="nm">Finish at ${esc(p.end_location.name)}</div><div class="meta">${p.deadline-p.end>0?`${hm(p.deadline-p.end)} to spare`:"Right on time"}</div></div></li>`);
  $("#itin").innerHTML=rows.join("");
  const sm=p.summary;
  $("#summary").innerHTML=`<strong>${sm.stops} stops</strong>${p.blocks.length?` in ${sm.zones} neighborhood${sm.zones>1?"s":""}`:""}, ${sm.walk_km.toFixed(1)} km walking, ${hm(sm.moving)} getting around. ${MODE_TXT[p.trip.getting_around]}, ${esc(p.trip.pace)} pace.`+
    (sm.cost!=null?` About ${money(sm.cost,p.currency)} per person${p.budget!=null?` of your ${money(p.budget,p.currency)} budget`:""}.`:"")+
    (p.rain&&p.rain.length?` Rain likely ${p.rain.map(([a,b])=>`${fmt(a)} to ${fmt(b)}`).join(", ")}.`:p.forecast?" No rain in the forecast.":"");
  let cuts="";
  if(p.dropped&&p.dropped.length)cuts+=`<p class="dropped">Dropped in this re-plan: ${p.dropped.map(esc).join(", ")}</p>`;
  if(p.cuts.length)cuts+=`<details class="cuts"><summary>${p.cuts.length} places left out, and why</summary><ul>${p.cuts.map(c=>`<li>${S.sid?`<button class="putback" data-id="${esc(c.id)}"${NO_PUTBACK.includes(c.why)?" disabled":""}>Put it back</button>`:""}${esc(c.name)}<span>${esc(c.why)}</span></li>`).join("")}</ul></details>`;
  cuts+=`<p class="attrib">Places, ratings and reviews from Google Maps. Travel times from the Google Routes API.</p>`;
  $("#cuts").innerHTML=cuts;
}
