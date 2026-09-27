/* ============ start ============ */
(async()=>{
  let cfg={mapsKey:"",missing:[]};
  try{const r=await fetch("/api/config");cfg=await r.json();}
  catch{console.warn("Can't reach the server. Start it with: uvicorn server.main:app");}
  if(cfg.missing&&cfg.missing.length)console.warn(`Missing ${cfg.missing.join(" and ")} in .env; use Demo for judging without keys`);
  await MapView.init(cfg);
})();
$("#planBtn").addEventListener("click",planDay);
Wizard.go(0,{focus:false});
$("#city").addEventListener("input",()=>{if($("#city").value.trim())formError();});
$("#demoBtn").addEventListener("click",loadDemo);
$("#icsBtn").addEventListener("click",downloadCalendar);
$("#copyBtn").addEventListener("click",copyPlan);
$("#imageBtn").addEventListener("click",saveImage);
$("#cuts").addEventListener("click",e=>{const b=e.target.closest(".putback");if(b)replan("include",30,null,b.dataset.id);});
