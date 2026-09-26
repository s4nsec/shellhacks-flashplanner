/* ============ results sheet: drags over the map on phones, a side panel on desktop ============ */
// Three heights, like a maps app: "peek" shows the heading, "half" shares the screen
// with the map, "full" is for reading the whole day. The grip also works by keyboard.
const Sheet={
  el:$("#sheet"),grip:$("#sheetGrip"),snap:"half",drag:null,
  wide:matchMedia("(min-width: 900px)"),
  ORDER:["peek","half","full"],
  heights(){
    const vh=window.innerHeight,peek=Math.min(vh*.4,$(".sheet-head").offsetHeight+28);
    return {peek,half:Math.max(peek,Math.round(vh*.5)),full:vh-56};
  },
  // How much of the map the sheet hides, so the route can be fitted above it.
  cover(){
    if(this.wide.matches||$("#resultsView").hidden)return 0;
    const h=this.heights();return this.snap==="full"?h.half:h[this.snap];
  },
  set(snap,{refit=true}={}){
    this.snap=snap;this.el.dataset.snap=snap;
    if(this.wide.matches)this.el.style.removeProperty("height");
    else this.el.style.height=this.heights()[snap]+"px";
    this.grip.setAttribute("aria-expanded",String(snap==="full"));
    this.grip.setAttribute("aria-label",snap==="full"?"Show less of the itinerary":"Show more of the itinerary");
    if(refit)MapView.fit();
  },
  open(){this.set(this.wide.matches?"full":"half",{refit:false});$("#sheetBody").scrollTop=0;},
  release(){this.drag=null;this.el.classList.remove("dragging");},
  step(dir){const i=this.ORDER.indexOf(this.snap);this.set(this.ORDER[Math.max(0,Math.min(2,i+dir))]);},
  start(e){
    if(this.wide.matches||e.button>0||!e.target.closest(".sheet-grip,.sheet-head")||e.target.closest("button:not(#sheetGrip),a,[role=group],.share-menu"))return;
    this.drag={y:e.clientY,h:this.el.offsetHeight,t:performance.now(),moved:false,id:e.pointerId};
    this.el.classList.add("dragging");
  },
  move(e){
    const d=this.drag;if(!d||e.pointerId!==d.id)return;
    const dy=e.clientY-d.y;if(Math.abs(dy)>4&&!d.moved){d.moved=true;this.el.setPointerCapture(e.pointerId);}
    if(!d.moved)return;
    const h=this.heights();this.el.style.height=Math.max(h.peek,Math.min(h.full,d.h-dy))+"px";
  },
  end(e){
    const d=this.drag;if(!d||e.pointerId!==d.id)return;this.release();
    if(!d.moved)return;
    this.justDragged=true;setTimeout(()=>{this.justDragged=false;},0);
    // A quick flick moves one step; otherwise settle on the nearest height.
    const now=this.el.offsetHeight,v=(now-d.h)/Math.max(1,performance.now()-d.t);
    if(Math.abs(v)>.6){this.step(v>0?1:-1);return;}
    const h=this.heights();
    this.set(this.ORDER.reduce((a,b)=>Math.abs(h[b]-now)<Math.abs(h[a]-now)?b:a));
  }
};
Sheet.el.addEventListener("pointerdown",e=>Sheet.start(e));
Sheet.el.addEventListener("pointermove",e=>Sheet.move(e));
Sheet.el.addEventListener("pointerup",e=>Sheet.end(e));
Sheet.el.addEventListener("pointercancel",e=>Sheet.end(e));
Sheet.grip.addEventListener("click",()=>{if(Sheet.justDragged)return;Sheet.set(Sheet.snap==="full"?"peek":Sheet.ORDER[Sheet.ORDER.indexOf(Sheet.snap)+1]);});
Sheet.grip.addEventListener("keydown",e=>{
  if(e.key==="ArrowUp"){e.preventDefault();Sheet.step(1);}
  else if(e.key==="ArrowDown"){e.preventDefault();Sheet.step(-1);}
});
Sheet.wide.addEventListener("change",()=>{Sheet.open();MapView.fit();});
window.addEventListener("resize",()=>{if(!$("#resultsView").hidden)Sheet.set(Sheet.snap,{refit:false});});
