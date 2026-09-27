/* ============ guided setup: one question at a time, everything pre-filled ============ */
const Wizard={
  step:0,LAST:1,
  titleSel(){return this.step?`.wstep[data-step="${this.step}"] .wstep-title`:"#setupTitle";},
  go(n,{focus=true}={}){
    this.step=Math.max(0,Math.min(this.LAST,n));
    $$(".wstep").forEach(w=>w.hidden=Number(w.dataset.step)!==this.step);
    const first=this.step===0,last=this.step===this.LAST;
    $("#stepBack").hidden=first;
    $("#planBtn").hidden=first;  // everything after the city is pre-filled
    $("#stepNext").hidden=last;
    $("#dayTitle").textContent=`Your day in ${$("#city").value.split(",")[0].trim()||"the city"}`;
    if(focus)$(this.titleSel()).focus({preventScroll:true});
    MapView.fit();
  },
  next(){
    if(this.step===0&&!$("#city").value.trim()){formError("Type the city you’re visiting.");return;}
    formError();this.go(this.step+1);
  }
};
$("#stepNext").addEventListener("click",()=>Wizard.next());
$("#stepBack").addEventListener("click",()=>Wizard.go(Wizard.step-1));
$("#tripForm").addEventListener("submit",e=>{e.preventDefault();Wizard.step===Wizard.LAST?planDay():Wizard.next();});
// Enter in the city box moves on once the suggestion list is closed.
$("#city").addEventListener("keydown",e=>{if(e.key==="Enter"&&$("#cityList").hidden){e.preventDefault();Wizard.next();}});

/* ---- when: Today leaves the date blank so the server uses the city's own today ---- */
function localDate(offset){const d=new Date();d.setDate(d.getDate()+offset);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;}
function setDay(kind){
  $$("#dayQuick button").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.day===kind)));
  $("#dateWrap").hidden=kind!=="pick";
  if(kind==="today")$("#date").value="";
  else if(kind==="tomorrow")$("#date").value=localDate(1);
  else{if(!$("#date").value)$("#date").value=localDate(0);$("#date").focus();}
}
$("#dayQuick").addEventListener("click",e=>{const b=e.target.closest("button[data-day]");if(b)setDay(b.dataset.day);});

/* ---- where: device location, and an optional different finish ---- */
$("#useLocation").addEventListener("click",async()=>{
  const btn=$("#useLocation");btn.disabled=true;btn.textContent="Finding you…";
  const pos=await devicePosition();btn.disabled=false;
  if(!pos){btn.textContent="Location unavailable, type an address";return;}
  $("#startLoc").value="My location";StartAC.clear();
  S.startPlace={name:"My location",lat:pos.lat,lng:pos.lng};
  $("#startLocPicked").textContent=`${pos.lat.toFixed(4)}, ${pos.lng.toFixed(4)}`;
  btn.textContent="Using your location";MapView.preview({point:pos});
});
$("#endToggle").addEventListener("click",()=>{
  const open=$("#endWrap").hidden;$("#endWrap").hidden=!open;$("#endToggle").setAttribute("aria-expanded",String(open));
  if(open)$("#endLoc").focus();else{$("#endLoc").value="";EndAC.clear();}
});

/* ---- fine-tune: the options that used to crowd the form, in one dialog ---- */
const TUNE_FIELDS=["#pace","#budget","#diet","#wheelchair","#userList","#msg"];
const Tune={
  snap:null,
  open(focusSel){
    this.snap={blocks:S.blocks,vals:TUNE_FIELDS.map(id=>{const el=$(id);return el.type==="checkbox"?el.checked:el.value;})};
    $("#tuneApply").textContent=S.view==="results"&&S.sid?"Update plan":"Done";
    $("#tuneDialog").showModal();
    (focusSel?$(focusSel):$("#styleSeg button[aria-pressed=true]")||$("#pace")).focus();
  },
  restore(){
    const s=this.snap;if(!s)return;S.blocks=s.blocks;
    TUNE_FIELDS.forEach((id,i)=>{const el=$(id);if(el.type==="checkbox")el.checked=s.vals[i];else el.value=s.vals[i];});
    syncForm();
  },
  chips(){
    const pace=$("#pace").value,budget=$("#budget").value,diet=$("#diet").value;
    const c=[["#styleSeg button[aria-pressed=true]",S.blocks?"By neighborhood":"Most stops",false],
      ["#pace",`Pace: ${pace[0].toUpperCase()+pace.slice(1)}`,pace!=="normal"],
      ["#budget",budget?`Budget: ${budget}`:"Budget",Boolean(budget)],
      ["#diet",diet?diet[0].toUpperCase()+diet.slice(1):"Diet",Boolean(diet)],
      ["#wheelchair","Accessible",$("#wheelchair").checked]];
    $("#tuneChips").innerHTML=c.map(([sel,label,on])=>`<button type="button" class="tchip${on?" on":""}" data-focus="${esc(sel)}">${esc(label)}</button>`).join("");
  }
};
$("#moreOptionsBtn").addEventListener("click",()=>Tune.open());
$("#tuneChips").addEventListener("click",e=>{const b=e.target.closest(".tchip");if(b)Tune.open(b.dataset.focus);});
$("#tuneDialog").addEventListener("close",()=>{
  if($("#tuneDialog").returnValue!=="apply"){Tune.restore();return;}
  Tune.chips();
  if(S.view==="results"&&S.sid)planDay();  // a new pace or budget needs a fresh plan
});
