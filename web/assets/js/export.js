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
function fileName(ext){
  const city=S.plan.city.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")||"trip";
  return `${city}-${S.plan.date}-flashplanner.${ext}`;
}
function downloadBlob(blob,name){
  const url=URL.createObjectURL(blob),a=document.createElement("a");
  a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),0);
}
function downloadCalendar(){
  if(!S.plan)return;
  const plans=S.days||[S.plan],blob=new Blob([itineraryCalendar(plans)],{type:"text/calendar;charset=utf-8"});
  downloadBlob(blob,fileName("ics"));
}

/* ============ itinerary image ============ */
function wrapLines(ctx,text,width){
  const lines=[];let line="";
  for(const word of text.split(" ")){
    const next=line?`${line} ${word}`:word;
    if(line&&ctx.measureText(next).width>width){lines.push(line);line=word;}
    else line=next;
  }
  return lines.concat(line);
}
// One entry per block of text: an optional time and rail dot on the left, wrapped text on the right.
function imageRows(plans){
  const rows=[],many=plans.length>1;
  plans.forEach((p,d)=>{
    const endsAtStart=p.end_location.lat===p.hotel.lat&&p.end_location.lng===p.hotel.lng,sm=p.summary;
    rows.push({text:many?`Day ${d+1} · ${p.date}`:p.date,size:20,weight:700,gap:d?36:0,head:true});
    rows.push({time:fmt(p.depart??p.start),dot:"H",text:`Leave ${p.hotel.name}`,weight:700,gap:14});
    planStops(p).forEach((st,i)=>{
      rows.push({text:legText(st.leg),muted:true,size:14,gap:10});
      rows.push({time:fmt(st.begin),dot:String(i+1),text:st.name,weight:700,gap:10});
      rows.push({text:`Until ${fmt(st.leave)} · ${hm(st.visit.minutes)}`,muted:true,size:14,gap:2});
    });
    rows.push({text:legText(p.back),muted:true,size:14,gap:10});
    rows.push({time:fmt(p.end),dot:endsAtStart?"H":"E",text:`Finish at ${p.end_location.name}`,weight:700,gap:10});
    rows.push({text:`${sm.stops} stop${sm.stops===1?"":"s"}, ${sm.walk_km.toFixed(1)} km walking, ${hm(sm.moving)} getting around.`+
      (sm.cost!=null?` About ${money(sm.cost,p.currency)} per person.`:""),muted:true,size:14,gap:16});
  });
  return rows;
}
async function itineraryCanvas(plans){
  await document.fonts.ready;
  const W=720,PAD=40,TIME=PAD+76,RAIL=PAD+100,TEXT=PAD+124,SCALE=2;
  const color={ink:cssVar("--ink"),muted:cssVar("--muted"),blue:cssVar("--blue"),line:cssVar("--line"),panel:cssVar("--panel"),onBlue:cssVar("--on-blue")};
  const font=(weight,size)=>`${weight} ${size}px Archivo, system-ui, sans-serif`;
  const canvas=document.createElement("canvas"),ctx=canvas.getContext("2d");
  // Lay out first so the canvas can be sized to fit, then draw.
  let y=PAD+96;
  const rows=imageRows(plans).map(r=>{
    const size=r.size||16,lh=Math.round(size*1.4);
    ctx.font=font(r.weight||400,size);
    const lines=wrapLines(ctx,r.text,W-PAD-(r.head?PAD:TEXT));
    y+=r.gap;const top=y;y+=lines.length*lh;
    return {...r,size,lh,lines,top};
  });
  const H=y+PAD+28;
  canvas.width=W*SCALE;canvas.height=H*SCALE;ctx.scale(SCALE,SCALE);
  ctx.fillStyle=color.panel;ctx.fillRect(0,0,W,H);
  ctx.textBaseline="top";
  ctx.fillStyle=color.blue;ctx.font=font(700,14);ctx.fillText("FLASHPLANNER",PAD,PAD);
  ctx.fillStyle=color.ink;ctx.font=font(700,30);
  ctx.fillText(plans.length>1?`${plans.length} days in ${plans[0].city}`:`Your day in ${plans[0].city}`,PAD,PAD+26);
  // The rail joins each day's dots, so draw it before them.
  let prev=null;
  rows.forEach(r=>{
    if(r.head)prev=null;
    if(!r.dot)return;
    const cy=r.top+r.lh/2;
    if(prev!=null){ctx.strokeStyle=color.line;ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(RAIL,prev);ctx.lineTo(RAIL,cy);ctx.stroke();}
    prev=cy;
  });
  rows.forEach(r=>{
    ctx.font=font(r.weight||400,r.size);ctx.fillStyle=r.muted?color.muted:color.ink;
    r.lines.forEach((line,i)=>ctx.fillText(line,r.head?PAD:TEXT,r.top+i*r.lh+2));
    if(!r.dot)return;
    const cy=r.top+r.lh/2;
    ctx.textAlign="right";ctx.fillStyle=color.muted;ctx.font=font(400,14);ctx.fillText(r.time,TIME,cy-8);
    ctx.fillStyle=color.blue;ctx.beginPath();ctx.arc(RAIL,cy,12,0,Math.PI*2);ctx.fill();
    ctx.textAlign="center";ctx.fillStyle=color.onBlue;ctx.font=font(700,12);ctx.fillText(r.dot,RAIL,cy-7);
    ctx.textAlign="left";
  });
  ctx.fillStyle=color.muted;ctx.font=font(400,12);
  ctx.fillText("Planned with FlashPlanner · places from Google Maps",PAD,H-PAD);
  return canvas;
}
// Phones get the share sheet; elsewhere the PNG downloads.
async function saveImage(){
  if(!S.plan)return;
  const canvas=await itineraryCanvas(S.days||[S.plan]);
  const blob=await new Promise(done=>canvas.toBlob(done,"image/png"));
  const file=new File([blob],fileName("png"),{type:"image/png"});
  if(matchMedia("(pointer:coarse)").matches&&navigator.canShare?.({files:[file]})){
    try{await navigator.share({files:[file],title:`FlashPlanner plan for ${S.plan.city}`});return;}
    catch(err){if(err.name==="AbortError")return;}
  }
  downloadBlob(blob,file.name);
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
