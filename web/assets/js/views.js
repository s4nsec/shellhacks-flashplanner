/* ============ views ============ */
// The map stays put; setup, loading and results take turns in the card or sheet over it.
const VIEW_IDS={setup:"#setupView",loading:"#loadingView",results:"#resultsView"};
function showView(name,focus=true){
  S.view=name;
  Object.entries(VIEW_IDS).forEach(([key,id])=>$(id).hidden=key!==name);
  if(name==="loading")$("#loadingTraceSlot").appendChild($("#tracePanel"));
  if(name==="results")$("#resultsTraceSlot").appendChild($("#tracePanel"));
  document.body.dataset.view=name;
  if(name!=="results")Sheet.release();
  $(".map-legend").hidden=name!=="results";
  if(name==="setup")Wizard.go(Wizard.step,{focus:false});
  $("#resumePlan").hidden=!(name==="setup"&&S.plan&&!S.busy);
  if(focus){
    const target=name==="setup"?Wizard.titleSel():name==="loading"?"#loadingTitle":"#resultsTitle";
    $(target).setAttribute("tabindex","-1");$(target).focus({preventScroll:true});
  }
}
$("#loadingTraceSlot").appendChild($("#tracePanel"));
$("#editTripBtn").addEventListener("click",()=>showView("setup"));
$("#loadingBack").addEventListener("click",()=>{if(!S.busy)showView("setup");});
// Back from a finished plan is easy to hit by accident, so the plan stays one tap away.
$("#resumePlan").addEventListener("click",()=>{if(S.plan&&!S.busy){formError();renderAll();}});
$("#brandHome").addEventListener("click",e=>{e.preventDefault();if(!S.busy){Wizard.step=0;showView("setup");}});
