/* ============ server calls ============ */
async function errorText(r){try{const j=await r.json();return j.detail||JSON.stringify(j);}catch{return `${r.status} ${r.statusText}`;}}
async function postJSON(url,body){
  const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(!r.ok)throw new Error(await errorText(r));
  return r.json();
}
async function stream(url,body,onEvent){
  const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(!r.ok)throw new Error(await errorText(r));
  const reader=r.body.getReader(),dec=new TextDecoder();let buf="";
  for(;;){
    const {value,done}=await reader.read();if(done)break;
    buf+=dec.decode(value,{stream:true});let i;
    while((i=buf.indexOf("\n"))>=0){const line=buf.slice(0,i).trim();buf=buf.slice(i+1);if(line)onEvent(JSON.parse(line));}
  }
  if(buf.trim())onEvent(JSON.parse(buf));
}

/* ============ trace ============ */
function traceReset(){
  $("#trace").innerHTML="";
  $("#loadingSummary").textContent="Opening the map and sharpening a pencil…";
  $("#loadingView").classList.remove("has-error");
  $("#loadingBack").disabled=true;
}
function traceStep(e){
  const ol=$("#trace");let li=ol.querySelector(`li[data-key="${e.key}"]`);
  if(!li){li=document.createElement("li");li.dataset.key=e.key;ol.appendChild(li);}
  if(e.title)li.dataset.title=e.title;if(e.call)li.dataset.call=e.call;if(e.source)li.dataset.source=e.source;
  li.className=e.status==="ok"?"ok":e.status==="fail"?"fail":"run";
  li.innerHTML=`<div class="t">${esc(li.dataset.title)}${e.ms!=null?`<small>${e.ms<1000?e.ms+" ms":(e.ms/1000).toFixed(1)+" s"}</small>`:""}</div>`+
    (li.dataset.call?`<code>${esc(li.dataset.call)}</code>`:"")+
    (e.result?`<div class="r">${esc(e.result)}</div>`:e.status==="run"?`<div class="r">Working…</div>`:"")+
    (e.detail?`<pre>${esc(e.detail)}</pre>`:"")+
    (li.dataset.source?`<div class="src">${esc(li.dataset.source)}</div>`:"");
  if(e.status==="run"&&e.title)$("#loadingSummary").textContent=e.title+"…";
  else if(e.status==="fail")$("#loadingSummary").textContent=e.result||"That step hit a snag.";
}
function failRunning(){ $$("#trace li.run").forEach(li=>{li.className="fail";}); }

function setStory(text,isError=false){  // status and errors show on the loading screen
  if(S.view==="loading")$("#loadingSummary").textContent=text;
  $("#loadingView").classList.toggle("has-error",isError);
}
function setBusy(b){
  S.busy=b;$("#planBtn").disabled=b;$("#demoBtn").disabled=b;
  $("#planBtn").textContent=b?"Planning…":"Plan my day";
  $("#loadingBack").disabled=b;
  $("#resumePlan").hidden=!(S.view==="setup"&&S.plan&&!b);
}
function formError(message=""){
  const box=$("#formError");box.textContent=message;box.hidden=!message;
  $("#city").setAttribute("aria-invalid",String(Boolean(message)));
  if(message){Wizard.step=0;showView("setup",false);$("#city").focus();}
}

