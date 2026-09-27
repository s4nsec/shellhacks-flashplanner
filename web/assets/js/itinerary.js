/* ============ rendering ============ */
function renderAll(){
  setStory(S.plan.story||"");
  renderDayTabs();renderItin();
  const maps=$("#mapsBtn"),stops=planStops(S.plan);
  maps.href=googleMapsUrl(S.plan);maps.setAttribute("aria-disabled","false");
  maps.title=stops.length>9?"Google Maps supports up to 9 waypoints; this link includes the first 9.":"Open this route in Google Maps";
  $("#icsBtn").disabled=false;
  $("#copyBtn").disabled=!S.plan;
  renderHeading();Tune.chips();renderLive();
  showView("results",false);
  // A re-plan from a stop's detail (Keep in plan) comes back to that stop.
  const again=S.detailId!=null?planStops(S.plan).findIndex(st=>st.id===S.detailId):-1;
  S.sel=again>=0?again:null;
  Sheet.open();
  MapView.draw(S.plan);
  if(again>=0)openStop(again);
  else{closeStop();$("#resultsTitle").setAttribute("tabindex","-1");$("#resultsTitle").focus({preventScroll:true});}
}
// A short title and one glanceable line; the full summary sits in the sheet body.
function renderHeading(){
  const p=S.plan,sm=p.summary,many=S.days&&S.days.length>1;
  $("#resultsTitle").textContent=many?`Day ${S.activeDay+1} in ${p.city}`:`Your day in ${p.city}`;
  $("#glance").textContent=`${sm.stops} stop${sm.stops===1?"":"s"} · back ${fmt(p.end)} · ${sm.walk_km.toFixed(1)} km walk`;
}
function renderDayTabs(){
  const box=$("#dayTabs"),many=S.days&&S.days.length>1;box.hidden=!many;
  if(!many){box.innerHTML="";return;}
  box.innerHTML=S.days.map((p,i)=>`<button type="button" data-day="${i}" aria-pressed="${i===S.activeDay}">Day ${i+1} · ${esc(p.date)}</button>`).join("");
}
$("#dayTabs").addEventListener("click",e=>{const b=e.target.closest("button[data-day]");if(!b)return;S.activeDay=Number(b.dataset.day);S.plan=S.days[S.activeDay];S.detailId=null;S.sid=S.plan.session_id;renderAll();});
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
  rows.push(`<li class="term"><span class="tm">${fmt(p.depart??p.start)}</span><span class="rail"><span class="dot">H</span></span><div class="body"><div class="nm">${esc(p.hotel.name)}</div><div class="meta">Leave</div></div></li>`);
  let n=0;
  p.completed.forEach((st,i)=>{rows.push(legRow(st.leg,true));if(heads.has(i))rows.push(zoneRow(heads.get(i),true));rows.push(stopRow(st,i,++n));});
  if(p.completed.length||p.shifted||p.here)rows.push(`<li class="now"><span class="tm">${fmt(p.now)}</span><span class="rail"><span class="dot"></span></span><div class="body"><div class="nm">You are here</div><div class="meta">${p.shifted?"Running behind the original plan":"Re-planning from this point"}</div></div></li>`);
  p.stops.forEach((st,i)=>{rows.push(legRow(st.leg,false));const k=p.completed.length+i;if(heads.has(k))rows.push(zoneRow(heads.get(k),false));rows.push(stopRow(st,k,++n));});
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
  if(p.cuts.length)cuts+=`<details class="cuts"><summary>${p.cuts.length} place${p.cuts.length>1?"s":""} left out</summary><ul>${p.cuts.map(c=>`<li>${S.sid?`<button class="putback" data-id="${esc(c.id)}"${NO_PUTBACK.includes(c.why)?" disabled":""}>Add back</button>`:""}${esc(c.name)}<span>${esc(c.why)}</span></li>`).join("")}</ul></details>`;
  cuts+=`<p class="attrib">Places, ratings and reviews from Google Maps. Travel times from the Google Routes API.</p>`;
  $("#cuts").innerHTML=cuts;
}
