function itineraryText(p){
  const lines=[
    `FlashPlanner plan for ${p.city} (${p.date})`,
    `${fmt(p.depart??p.start)} leave ${p.hotel.name}; finish at ${p.end_location.name} around ${fmt(p.end)}`,
    `${p.summary.stops} stops, ${p.summary.walk_km.toFixed(1)} km walking, ${hm(p.summary.moving)} moving`,
    ""
  ];
  let n=1;
  p.completed.concat(p.stops).forEach(st=>{
    lines.push(`${n}. ${fmt(st.begin)}-${fmt(st.leave)} ${st.name} (${hm(st.visit.minutes)})`);
    lines.push(`   ${legText(st.leg)} from previous stop`);
    if(st.reason)lines.push(`   Why: ${st.reason}`);
    n+=1;
  });
  lines.push(`Final leg to ${p.end_location.name}: ${legText(p.back)}; arrive ${fmt(p.end)}`);
  if(p.cuts.length){
    lines.push("", "Left out:");
    p.cuts.slice(0,5).forEach(c=>lines.push(`- ${c.name}: ${c.why}`));
  }
  return lines.join("\n");
}
function planStops(p){return p.completed.concat(p.stops);}
function mapsPoint(place){
  const lat=Number(place.lat),lng=Number(place.lng);
  return Number.isFinite(lat)&&Number.isFinite(lng)?`${lat},${lng}`:place.name;
}
function googleMapsUrl(p){
  const params=new URLSearchParams({api:"1",origin:mapsPoint(p.hotel),destination:mapsPoint(p.end_location)});
  const waypoints=planStops(p).slice(0,9).map(mapsPoint);
  if(waypoints.length)params.set("waypoints",waypoints.join("|"));
  if(p.trip.getting_around==="walk")params.set("travelmode","walking");
  else if(p.trip.getting_around==="ride")params.set("travelmode","driving");
  return `https://www.google.com/maps/dir/?${params}`;
}
function icsEscape(value){
  return String(value??"").replace(/\\/g,"\\\\").replace(/\r?\n/g,"\\n").replace(/([,;])/g,"\\$1");
}
function icsStamp(date,minutes){
  const [year,month,day]=date.split("-").map(Number);
  const d=new Date(Date.UTC(year,month-1,day,0,minutes));
  const two=n=>String(n).padStart(2,"0");
  return `${d.getUTCFullYear()}${two(d.getUTCMonth()+1)}${two(d.getUTCDate())}T${two(d.getUTCHours())}${two(d.getUTCMinutes())}00`;
}
function icsUtcStamp(date=new Date()){
  const two=n=>String(n).padStart(2,"0");
  return `${date.getUTCFullYear()}${two(date.getUTCMonth()+1)}${two(date.getUTCDate())}T${two(date.getUTCHours())}${two(date.getUTCMinutes())}${two(date.getUTCSeconds())}Z`;
}
function icsFold(line){
  const encoder=new TextEncoder(),parts=[];let chunk="";
  for(const char of line){
    const prefix=parts.length?" ":"";
    if(chunk&&encoder.encode(prefix+chunk+char).length>75){parts.push(prefix+chunk);chunk=char;}
    else chunk+=char;
  }
  parts.push((parts.length?" ":"")+chunk);
  return parts.join("\r\n");
}
function itineraryCalendar(plans){
  const first=plans[0],stamp=icsUtcStamp(),lines=[
    "BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//FlashPlanner//Trip Plan//EN","CALSCALE:GREGORIAN","METHOD:PUBLISH",
    `X-WR-CALNAME:${icsEscape(`FlashPlanner - ${first.city}`)}`
  ];
  plans.forEach(p=>planStops(p).forEach((st,index)=>{
    const rawId=String(st.id||st.name).replace(/[^A-Za-z0-9.-]/g,"-");
    const details=[`Travel from previous stop: ${legText(st.leg)}`];
    if(st.reason)details.push(`Why: ${st.reason}`);
    lines.push("BEGIN:VEVENT",`UID:${p.date}-${index+1}-${rawId}@flashplanner.local`,`DTSTAMP:${stamp}`,
      `DTSTART:${icsStamp(p.date,st.begin)}`,`DTEND:${icsStamp(p.date,st.leave)}`,
      `SUMMARY:${icsEscape(st.name)}`,`LOCATION:${icsEscape(`${st.name} (${st.lat}, ${st.lng})`)}`,
      `GEO:${st.lat};${st.lng}`,`DESCRIPTION:${icsEscape(details.join("\n"))}`);
    if(st.maps_uri)lines.push(`URL:${st.maps_uri}`);
    lines.push("END:VEVENT");
  }));
  lines.push("END:VCALENDAR");
  return lines.map(icsFold).join("\r\n")+"\r\n";
}
function downloadCalendar(){
  if(!S.plan)return;
  const plans=S.days||[S.plan],blob=new Blob([itineraryCalendar(plans)],{type:"text/calendar;charset=utf-8"});
  const url=URL.createObjectURL(blob),a=document.createElement("a");
  const city=S.plan.city.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")||"trip";
  a.href=url;a.download=`${city}-${S.plan.date}-flashplanner.ics`;document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),0);
}
async function copyPlan(){
  if(!S.plan)return;
  const text=(S.days||[S.plan]).map(itineraryText).join("\n\n"),btn=$("#shareBtn"),old="Share";  // the menu closes on click, so the Share button shows the result
  try{
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(text);
    else{
      const ta=document.createElement("textarea");ta.value=text;ta.style.position="fixed";ta.style.opacity="0";
      document.body.appendChild(ta);ta.select();document.execCommand("copy");ta.remove();
    }
    btn.textContent="Copied";
  }catch{
    btn.textContent="Copy failed";
  }
  $("#shareLive").textContent=btn.textContent;
  setTimeout(()=>{btn.textContent=old;$("#shareLive").textContent="";},1200);
}


/* ============ share menu ============ */
function toggleShare(open){
  const btn=$("#shareBtn"),menu=$("#shareMenu");
  open??=menu.hidden;menu.hidden=!open;btn.setAttribute("aria-expanded",String(open));
  if(open)menu.querySelector("a[aria-disabled=false],button:not(:disabled)")?.focus();
}
$("#shareBtn").addEventListener("click",()=>toggleShare());
$("#shareMenu").addEventListener("click",e=>{if(e.target.closest("a,button"))toggleShare(false);});
document.addEventListener("click",e=>{if(!e.target.closest(".share"))toggleShare(false);});
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("#shareMenu").hidden){toggleShare(false);$("#shareBtn").focus();}});
