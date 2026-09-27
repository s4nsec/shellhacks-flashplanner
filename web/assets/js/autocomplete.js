/* ============ location suggestions (Places API via the browser key) ============ */
// All three fields fall back to plain text: with no browser key, a failed request,
// or no pick, the server looks up whatever was typed.
const PLACE_AC={lib:null,biasCity:null,bias:null};
async function placesLib(){
  if(MapView.kind!=="google")return null;
  try{PLACE_AC.lib??=await google.maps.importLibrary("places");}catch(e){console.warn(e);return null;}
  return PLACE_AC.lib;
}
async function cityBias(lib){
  const city=$("#city").value.trim();
  if(!city)return null;
  if(PLACE_AC.biasCity!==city){  // cache the lookup itself, so overlapping searches share it
    PLACE_AC.biasCity=city;
    PLACE_AC.bias=lib.Place.searchByText({textQuery:city,fields:["viewport"],maxResultCount:1})
      .then(r=>r.places[0]?.viewport||null)
      .catch(e=>{console.warn(e);if(PLACE_AC.biasCity===city)PLACE_AC.biasCity=null;return null;});  // retry next time
  }
  return PLACE_AC.bias;  // a bias, not a restriction, so places outside the city still show
}
function placeAutocomplete({inputId,listId,pickedId=null,liveId,stateKey=null,prefix,announcement,withOffset=false,citiesOnly=false}){
  const ac={input:$(inputId),list:$(listId),picked:pickedId?$(pickedId):null,live:$(liveId),items:[],active:-1,seq:0,pick:0,timer:0,token:null};
  const announce=t=>{ac.live.textContent=t;};
  const clear=()=>{if(stateKey)S[stateKey]=null;if(ac.picked)ac.picked.textContent="";};
  const open=()=>{ac.list.hidden=false;ac.input.setAttribute("aria-expanded","true");};
  const close=()=>{ac.seq++;clearTimeout(ac.timer);ac.list.hidden=true;ac.active=-1;
    ac.input.setAttribute("aria-expanded","false");ac.input.removeAttribute("aria-activedescendant");};
  const message=t=>{ac.items=[];ac.active=-1;ac.list.innerHTML=`<li class="ac-msg">${esc(t)}</li>`;open();announce(t);};
  const cityCountry=p=>{
    const city=p.mainText?.text||p.text?.text||"",parts=(p.secondaryText?.text||"").split(",");
    const country=parts.at(-1)?.trim()||"";return {city,country,label:[city,country].filter(Boolean).join(", ")};};
  const render=()=>{ac.active=-1;
    ac.list.innerHTML=ac.items.map((p,i)=>{const cc=cityCountry(p),main=citiesOnly?cc.city:(p.mainText?.text||p.text?.text),secondary=citiesOnly?cc.country:p.secondaryText?.text;
      return `<li role="option" id="${prefix}Opt${i}" data-i="${i}" aria-selected="false"><b>${esc(main)}</b>${secondary?`<small>${esc(secondary)}</small>`:""}</li>`;}).join("");
    open();announce(`${ac.items.length} suggestion${ac.items.length===1?"":"s"}. Use the arrow keys to choose.`);};
  const fetchSuggestions=async q=>{
    const seq=++ac.seq,lib=await placesLib();
    if(!lib||seq!==ac.seq)return;
    message("Searching…");
    try{
      ac.token??=new lib.AutocompleteSessionToken();
      const req={input:q,sessionToken:ac.token};
      if(citiesOnly)req.includedPrimaryTypes=["(cities)"];
      else{const bias=await cityBias(lib);if(bias)req.locationBias=bias;}
      const {suggestions}=await lib.AutocompleteSuggestion.fetchAutocompleteSuggestions(req);
      if(seq!==ac.seq)return;
      ac.items=suggestions.map(x=>x.placePrediction).filter(Boolean).slice(0,6);
      ac.items.length?render():message("No matches. We'll search for what you typed.");
    }catch(e){console.warn(e);if(seq===ac.seq)message("Suggestions aren't available. We'll search for what you typed.");}
  };
  const move=d=>{
    if(ac.list.hidden||!ac.items.length)return;
    ac.active=(ac.active+d+ac.items.length)%ac.items.length;
    $$(`${listId} [role=option]`).forEach((li,i)=>li.setAttribute("aria-selected",String(i===ac.active)));
    ac.input.setAttribute("aria-activedescendant",`${prefix}Opt${ac.active}`);
    $(`#${prefix}Opt${ac.active}`).scrollIntoView({block:"nearest"});
  };
  const pick=async i=>{
    const pred=ac.items[i];if(!pred)return;
    const cc=cityCountry(pred),label=citiesOnly?cc.label:(pred.mainText?.text||pred.text?.text||""),pickId=++ac.pick;
    ac.input.value=label;clear();close();
    try{
      const place=pred.toPlace(),fields=["displayName","formattedAddress"];
      if(citiesOnly)fields.push("addressComponents");else fields.push("location");
      if(citiesOnly)fields.push("viewport");
      if(withOffset)fields.push("utcOffsetMinutes");
      await place.fetchFields({fields});
      ac.token=null;
      if(pickId!==ac.pick||ac.input.value!==label||(!citiesOnly&&!place.location))return;
      if(citiesOnly){
        const country=place.addressComponents?.find(c=>c.types?.includes("country"))?.longText||cc.country;
        ac.input.value=[place.displayName||cc.city,country].filter(Boolean).join(", ");
        PLACE_AC.biasCity=null;PLACE_AC.bias=null;StartAC.clear();EndAC.clear();announce(`${announcement} ${ac.input.value}`);
        if(place.viewport)MapView.preview({viewport:place.viewport});return;
      }
      const selected={place_id:place.id,name:place.displayName||label,lat:place.location.lat(),lng:place.location.lng()};
      if(withOffset)selected.utc_offset_minutes=place.utcOffsetMinutes??null;
      S[stateKey]=selected;ac.picked.textContent=place.formattedAddress||"";
      if(stateKey==="startPlace")MapView.preview({point:{lat:selected.lat,lng:selected.lng}});
      announce(`${announcement} ${selected.name}`);
    }catch(e){console.warn(e);announce("Couldn't load that place. We'll search for what you typed.");}
  };
  ac.input.addEventListener("input",()=>{clear();clearTimeout(ac.timer);ac.items=[];ac.pick++;
    const q=ac.input.value.trim();if(q.length<3){ac.token=null;close();return;}ac.timer=setTimeout(()=>fetchSuggestions(q),250);});
  ac.input.addEventListener("keydown",e=>{
    if(e.key==="ArrowDown"){e.preventDefault();if(ac.list.hidden&&ac.items.length)open();move(1);}
    else if(e.key==="ArrowUp"){e.preventDefault();move(-1);}
    else if(e.key==="Enter"&&!ac.list.hidden&&ac.active>=0){e.preventDefault();pick(ac.active);}
    else if(e.key==="Escape"&&!ac.list.hidden){e.preventDefault();close();}
  });
  ac.input.addEventListener("blur",close);
  ac.list.addEventListener("mousedown",e=>e.preventDefault());
  ac.list.addEventListener("click",e=>{const li=e.target.closest("[role=option]");if(li)pick(Number(li.dataset.i));});
  return {clear,close};
}
const CityAC=placeAutocomplete({inputId:"#city",listId:"#cityList",liveId:"#cityLive",
  prefix:"city",announcement:"City selected:",citiesOnly:true});
const StartAC=placeAutocomplete({inputId:"#startLoc",listId:"#startLocList",pickedId:"#startLocPicked",liveId:"#startLocLive",
  stateKey:"startPlace",prefix:"startLoc",announcement:"Starting at",withOffset:true});
const EndAC=placeAutocomplete({inputId:"#endLoc",listId:"#endLocList",pickedId:"#endLocPicked",liveId:"#endLocLive",
  stateKey:"endPlace",prefix:"endLoc",announcement:"Finishing at"});
$("#city").addEventListener("input",()=>{PLACE_AC.biasCity=null;PLACE_AC.bias=null;StartAC.clear();EndAC.clear();});  // picks belong to the old city

