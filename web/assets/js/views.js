/* ============ views ============ */
const VIEW_IDS={setup:"#setupView",loading:"#loadingView",results:"#resultsView"};
function showView(name,focus=true){
  S.view=name;
  Object.entries(VIEW_IDS).forEach(([key,id])=>$(id).hidden=key!==name);
  if(name==="loading")$("#loadingTraceSlot").appendChild($("#tracePanel"));
  if(name==="results")$("#resultsTraceSlot").appendChild($("#tracePanel"));
  document.body.dataset.view=name;
  if(name!=="results")Sheet.release();
  window.scrollTo({top:0,behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});
  if(focus){
    const target=name==="setup"?"#setupTitle":name==="loading"?"#loadingTitle":"#resultsTitle";
    $(target).setAttribute("tabindex","-1");$(target).focus({preventScroll:true});
  }
}
function updateTicket(){
  const city=$("#city").value.trim()||"Pick a city",days=Math.max(1,Number($("#days").value)||1);
  $("#ticketCity").textContent=city;
  $("#ticketTiming").textContent=days>1?`${days} days`:`${$("#tStart").value||"10:00"}–${$("#tEnd").value||"19:00"}`;
  $("#ticketMode").textContent=MODE_TXT[S.mode].replace("Walk + ","");
  const vibe=[...S.likes].slice(0,3).map(x=>x[0].toUpperCase()+x.slice(1));
  $("#ticketVibe").textContent=vibe.length?vibe.join(" · "):"Open to surprises";
}
$("#loadingTraceSlot").appendChild($("#tracePanel"));
$("#tripForm").addEventListener("input",updateTicket);
$("#tripForm").addEventListener("change",updateTicket);
$("#editTripBtn").addEventListener("click",()=>showView("setup"));
$("#loadingBack").addEventListener("click",()=>{if(!S.busy)showView("setup");});
$("#brandHome").addEventListener("click",e=>{e.preventDefault();if(!S.busy)showView("setup");});

