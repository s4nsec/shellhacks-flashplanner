/* ============ stops: short rows in the list, full detail on tap, linked to the map pins ============ */
const TRAVEL_MODE={walk:"walking",transit:"transit",ride:"driving"};
function stopTags(st){
  const t=[],slot={breakfast:"Breakfast slot",lunch:"Lunch slot",dinner:"Dinner slot",break:"Coffee break",golden:"Golden hour",appointment:"Fixed time"};
  if(st.new)t.push({text:"New",cls:"new"});
  if(!st.done&&st.locked&&!st.fixed)t.push({text:st.must?"Must-see":"Kept",cls:""});
  Object.entries(slot).forEach(([k,text])=>{if(st.notes.includes(k))t.push({text,cls:"gold"});});
  if(st.notes.includes("rain"))t.push({text:st.setting==="outdoor"?"Outdoors":st.setting==="covered"?"Covered":"Indoors",cls:"rain"});
  if(st.venue&&!st.done&&S.sid)t.push({text:"What's on",cls:"link",go:"whatsOn"});
  return t;
}
// The planner's kind for each place, as a category people recognize. "other" has none.
const CATEGORY={sight:"Sight",museum:"Museum",meal:"Food",snack:"Café & snacks",market:"Market",park:"Park",
  viewpoint:"Viewpoint",shopping:"Shopping",nightlife:"Nightlife"};
const tagHtml=ts=>ts.map(x=>x.go?`<button type="button" class="tag ${x.cls}" data-go="${x.go}">${esc(x.text)}</button>`:`<span class="tag ${x.cls}">${esc(x.text)}</span>`).join("");
// One line for the list: what it is, how long, how good, how pricey.
function stopGlance(st){
  const bits=[`${hm(st.visit.minutes)}`];
  if(CATEGORY[st.kind])bits.unshift(CATEGORY[st.kind]);
  if(st.wait>0)bits.push(`${st.wait} min wait`);
  if(st.rating)bits.push(`★ ${st.rating.toFixed(1)}`);
  if(st.price)bits.push(priceText(st.price));
  return bits.join(" · ");
}
function stopRow(st,i,num){
  return `<li class="stn${st.done?" done":""}${st.new?" new":""}${i===S.sel?" sel":""}" data-i="${i}"><span class="tm">${fmt(st.begin)}</span><span class="rail"><span class="dot">${st.done?"✓":num}</span></span><div class="body">`+
    `<button type="button" class="stop-open" data-i="${i}"><span class="nm">${esc(st.name)}</span><span class="meta">${stopGlance(st)}</span></button>`+
    `${st.done?"":`<div class="tags">${tagHtml(stopTags(st).slice(0,2))}</div>`}</div></li>`;
}
function visitNote(st){
  const p=S.plan,v=st.visit,quotes=(v.evidence||[]).filter(x=>x.quote),of=((v.evidence||[]).find(x=>x.of)||{}).of||quotes.length;
  const paced=v.minutes-(v.extra||0)!==v.base?`, adjusted for ${esc(p.trip.pace)} pace`:"";
  if(v.source==="reviews"&&quotes.length)return `<details class="rv"><summary>Reviewers suggest ${hm(v.base)} (${quotes.length} of ${of} reviews)${paced}</summary><ul>${quotes.map(q=>`<li>“${esc(q.quote)}”<cite>${q.uri?`<a href="${esc(q.uri)}" target="_blank" rel="noopener">${esc(q.author)}</a>`:esc(q.author)}, Google review</cite></li>`).join("")}</ul></details>`;
  if(v.source==="gemini")return `<p class="rv">No review mentions time, so Gemini estimated ${hm(v.base)}${paced}.</p>`;
  return `<p class="rv">Typical visit length for a ${esc(st.kind)}${paced}.</p>`;
}
function lockButton(st){
  if(st.done||!S.sid)return "";
  const why=st.fixed?"Fixed time from your request":st.must?"Must-see from your request":"";
  return `<button type="button" class="secondary lock${st.locked?" on":""}" data-id="${esc(st.id)}" data-locked="${st.locked?1:0}" aria-pressed="${Boolean(st.locked)}"${why?` disabled title="${why}"`:""}>${st.locked?"Kept in plan":"Keep in plan"}</button>`;
}
// Cinemas, theaters, concert halls: that day's listings, fetched when the stop opens.
const WHATS_ON=new Map();  // "date|place id" -> promise of {showings, sources}
function whatsOn(st){
  const key=`${S.plan.date}|${st.id}`;
  if(!WHATS_ON.has(key))WHATS_ON.set(key,fetch(`/api/whats-on?${new URLSearchParams({session_id:S.sid,place_id:st.id})}`)
    .then(async r=>{if(!r.ok)throw new Error(await errorText(r));return r.json();})
    .catch(err=>{WHATS_ON.delete(key);throw err;}));
  return WHATS_ON.get(key);
}
function whatsOnHtml(st,w){
  const fits=t=>t>=st.begin&&t<st.leave,any=w.showings.some(x=>x.times.some(fits));
  const src=w.sources.length?`<p class="rv">Found with Google Search: ${w.sources.slice(0,3).map(x=>`<a href="${esc(x.uri)}" target="_blank" rel="noopener">${esc(x.title||"source")}</a>`).join(", ")}</p>`:"";
  if(!w.showings.length)return `<p class="rv">No listings found for this day.</p>${src}`;
  return `<ul>${w.showings.map(x=>`<li><b>${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>`:esc(x.title)}</b>`+
    `${x.detail?`<span>${esc(x.detail)}</span>`:""}`+
    `${x.times.length?`<span class="times">${x.times.map(t=>`<time class="${fits(t)?"fit":""}">${fmt(t)}</time>`).join("")}</span>`:""}</li>`).join("")}</ul>`+
    `${any?`<p class="rv">Highlighted times start during your visit, ${fmt(st.begin)} to ${fmt(st.leave)}.</p>`:""}${src}`;
}
async function loadWhatsOn(st){
  const box=$("#whatsOn .wo-body");if(!box)return;
  try{const w=await whatsOn(st);if(box.isConnected)box.innerHTML=whatsOnHtml(st,w);}
  catch(err){if(box.isConnected)box.innerHTML=`<p class="rv">${esc(err.message)}</p>`;}
}
function renderStopDetail(i){
  const all=planStops(S.plan),st=all[i],prev=i?all[i-1]:(S.plan.here||S.plan.hotel);
  const facts=[["Time here",hm(st.visit.minutes)+(st.visit.extra>0?` (${st.visit.extra} min extra instead of waiting later)`:"")],
    ["Getting there",legText(st.leg)]];
  if(st.opens!=null&&st.wait>0)facts.push(["Opens",`${fmt(st.opens)}, so a ${st.wait} min wait`]);
  if(st.rating)facts.push(["Rating",`${st.rating.toFixed(1)} from ${(st.count||0).toLocaleString()} reviews`]);
  if(st.price)facts.push(["Price",priceText(st.price)]);
  const dir=new URLSearchParams({api:"1",origin:mapsPoint(prev),destination:mapsPoint(st),travelmode:TRAVEL_MODE[st.leg.mode]||"walking"});
  const place=st.maps_uri||`https://www.google.com/maps/search/?${new URLSearchParams({api:"1",query:`${st.name} ${S.plan.city}`})}`;
  $("#stopDetail").innerHTML=`
    <div class="detail-nav">
      <button type="button" class="text-btn" id="detailBack">All stops</button>
      <div class="detail-step"><button type="button" class="icon-btn" id="detailPrev" aria-label="Previous stop"${i?"":" disabled"}>‹</button><button type="button" class="icon-btn" id="detailNext" aria-label="Next stop"${i<all.length-1?"":" disabled"}>›</button></div>
    </div>
    <p class="eyebrow">Stop ${i+1} · ${fmt(st.begin)} to ${fmt(st.leave)}</p>
    <h2 id="stopName" tabindex="-1">${esc(st.name)}</h2>
    <p class="detail-kind">${[CATEGORY[st.kind],st.zone].filter(Boolean).map(esc).join(" · ")}</p>
    <div class="tags">${tagHtml(stopTags(st))}</div>
    ${st.reason?`<p class="why">${esc(st.reason)}</p>`:""}
    <dl class="facts">${facts.map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
    ${st.done?"":visitNote(st)}
    ${st.venue&&!st.done&&S.sid?`<section class="whats-on" id="whatsOn"><h3>What's on</h3><div class="wo-body"><p class="rv">Checking listings for this day…</p></div></section>`:""}
    <div class="detail-actions">
      <a class="primary" href="https://www.google.com/maps/dir/?${dir}" target="_blank" rel="noopener">Directions</a>
      <a class="secondary" href="${esc(place)}" target="_blank" rel="noopener">Open in Google Maps</a>
      ${lockButton(st)}
    </div>`;
  loadWhatsOn(st);
}
// Selecting a stop highlights its row and pin; opening it swaps the list for its detail.
function selectStop(i){
  S.sel=i;
  $$("#itin .stn").forEach(li=>li.classList.toggle("sel",Number(li.dataset.i)===i));
  MapView.select(i);
}
function openStop(i,{focus=true}={}){
  if(i==null||!planStops(S.plan)[i])return closeStop();
  selectStop(i);S.detailId=planStops(S.plan)[i].id;renderStopDetail(i);
  $("#dayList").hidden=true;$("#stopDetail").hidden=false;$("#sheetBody").scrollTop=0;
  if(Sheet.snap==="peek")Sheet.set("half");
  if(focus)$("#stopName").focus({preventScroll:true});
}
function closeStop(){
  const was=S.detailId;S.detailId=null;
  $("#stopDetail").hidden=true;$("#dayList").hidden=false;
  if(was!=null&&S.sel!=null){const b=$(`#itin .stop-open[data-i="${S.sel}"]`);if(b){b.scrollIntoView({block:"nearest"});b.focus({preventScroll:true});}}
}
// A tag that points at a section of the detail opens the stop and scrolls there.
const showSection=id=>{const el=document.getElementById(id);if(el)el.scrollIntoView({behavior:"smooth",block:"start"});};
$("#itin").addEventListener("click",e=>{
  const g=e.target.closest(".tag[data-go]");
  if(g){openStop(Number(g.closest(".stn").dataset.i));showSection(g.dataset.go);return;}
  const b=e.target.closest(".stop-open");if(b)openStop(Number(b.dataset.i));
});
$("#stopDetail").addEventListener("click",e=>{
  if(e.target.closest("#detailBack"))closeStop();
  else if(e.target.closest("#detailPrev"))openStop(S.sel-1);
  else if(e.target.closest("#detailNext"))openStop(S.sel+1);
  else if(e.target.closest(".tag[data-go]"))showSection(e.target.closest(".tag[data-go]").dataset.go);
  else{const b=e.target.closest(".lock");if(b)replan(b.dataset.locked==="1"?"unlock":"lock",30,null,b.dataset.id);}
});
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("#stopDetail").hidden&&$("#shareMenu").hidden&&!$("#tuneDialog").open&&!$("#resultsView").hidden)closeStop();});
