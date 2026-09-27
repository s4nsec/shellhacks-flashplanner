/* ============ start day: what's next, and one-tap changes while you're out ============ */
const LIVE_ACTIONS=[["done","Done","Finished the next stop"],["late","30 min late","Running 30 minutes late"],
  ["rain","Raining","It started raining"],["tired","Tired","Feeling tired, slow the day down"],["skip","Skip it","Skip the next stop"]];
function renderLive(){
  const box=$("#liveBar"),p=S.plan;
  $("#tuneChips").hidden=S.live;
  if(!S.sid||!p){box.innerHTML="";return;}
  if(!S.live){
    box.innerHTML=p.stops.length?`<button type="button" class="primary start-day" id="startDay">Start day</button>`:"";
    return;
  }
  const st=p.stops[0];
  const next=st?`<p class="next-name"><span class="next-tag">Next</span> ${esc(st.name)}</p>
      <p class="next-meta">Leave by ${fmt(st.arrive-st.leg.min)} · ${legText(st.leg)}</p>`
    :`<p class="next-name"><span class="next-tag">Last leg</span> Head to ${esc(p.end_location.name)}</p><p class="next-meta">${legText(p.back)} · arrive ${fmt(p.end)}</p>`;
  box.innerHTML=`<div class="next-card"><div class="next-head">${next}</div><button type="button" class="text-btn" id="endLive">End</button></div>
    <div class="live-actions" role="group" aria-label="Something changed">${LIVE_ACTIONS.map(([ev,label,full])=>
      `<button type="button" class="tchip" data-live="${ev}" aria-label="${full}"${!st&&ev!=="rain"&&ev!=="tired"&&ev!=="late"?" disabled":""}>${label}</button>`).join("")}
      <button type="button" class="tchip" id="liveMore" aria-expanded="${S.askOpen?"true":"false"}" aria-controls="liveAsk">Other…</button></div>
    <form class="live-ask" id="liveAsk"${S.askOpen?"":" hidden"}><label for="liveText" class="sr-only">Tell us what changed</label>
      <input type="text" id="liveText" placeholder="What changed?" autocomplete="off">
      <button type="submit" class="secondary">Update</button></form>`;
}
$("#liveBar").addEventListener("click",e=>{
  if(e.target.closest("#startDay")){S.live=true;renderLive();$("#liveBar .next-name")?.setAttribute("tabindex","-1");$("#liveBar .next-name")?.focus();return;}
  if(e.target.closest("#endLive")){S.live=false;renderLive();$("#startDay")?.focus();return;}
  if(e.target.closest("#liveMore")){S.askOpen=!S.askOpen;renderLive();if(S.askOpen)$("#liveText").focus();else $("#liveMore").focus();return;}
  const b=e.target.closest("[data-live]");
  if(b)replan(b.dataset.live,30);
});
// Free text goes through Gemini, which picks the closest re-plan (late, rain, tired, skip…).
$("#liveBar").addEventListener("submit",async e=>{
  e.preventDefault();
  const text=$("#liveText").value.trim();if(!text||S.busy)return;
  const pre={key:"interpret",status:"run",title:"Understand what changed",call:"gemini.interpret_event(text)",source:"server/gemini.py: interpret_event()"};
  try{
    const t0=performance.now(),r=await postJSON("/api/interpret",{session_id:S.sid,text});
    replan(r.reason,r.delay_minutes,{...pre,status:"ok",ms:Math.round(performance.now()-t0),result:`Treating it as “${r.reason}”${r.reason==="late"?` by ${r.delay_minutes} min`:""}.`});
  }catch(err){$("#liveText").value="";$("#liveText").placeholder=err.message;}
});
