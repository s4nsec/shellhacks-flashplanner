/* ============ map: Google Maps if a browser key is set, else a simple SVG ============ */
function decodePolyline(str){
  let i=0,lat=0,lng=0;const out=[];
  while(i<str.length){
    for(const k of [0,1]){let b,shift=0,res=0;do{b=str.charCodeAt(i++)-63;res|=(b&31)<<shift;shift+=5;}while(b>=32);
      const d=(res&1)?~(res>>1):(res>>1);if(k===0)lat+=d;else lng+=d;}
    out.push([lat/1e5,lng/1e5]);
  }
  return out;
}
function legPath(from,to,L){return L.polyline?decodePolyline(L.polyline):[[from.lat,from.lng],[to.lat,to.lng]];}
function legsOf(p){
  const legs=[];let prev=p.hotel;
  p.completed.forEach(st=>{legs.push({path:legPath(prev,st,st.leg),mode:st.leg.mode,done:true});prev=st;});
  if(p.here)prev=p.here;
  p.stops.forEach(st=>{legs.push({path:legPath(prev,st,st.leg),mode:st.leg.mode,done:false});prev=st;});
  legs.push({path:legPath(prev,p.end_location,p.back),mode:p.back.mode,done:false});
  return legs;
}
const MapView={
  kind:null,map:null,overlays:[],
  async init(cfg){
    if(cfg.mapsKey){
      try{await loadGoogleMaps(cfg.mapsKey);this.kind="google";this.mapId=cfg.mapId;
        this.ensure({lat:25,lng:-30},2);$("#mapEmpty").hidden=true;  // the whole world until a city is picked
        $("#mapNote").textContent="Map data from Google";return;}catch(e){console.warn(e);}
    }
    this.kind="svg";
    $("#gmap").innerHTML=`<svg id="svgmap" role="group" aria-label="Route sketch"></svg>`;
    $("#mapNote").textContent=cfg.mapsKey?"Google map failed to load, showing a sketch.":"Add GOOGLE_MAPS_BROWSER_KEY for a real map.";
  },
  draw(p){
    if(!this.kind){
      this.kind="svg";
      $("#gmap").innerHTML=`<svg id="svgmap" role="group" aria-label="Route sketch"></svg>`;
    }
    $("#mapEmpty").hidden=true;
    if(this.kind==="google")this.drawGoogle(p);
    else this.fit();
  },
  ensure(center,zoom=13){
    this.map??=new google.maps.Map($("#gmap"),{center,zoom,mapId:this.mapId,disableDefaultUI:true,zoomControl:true,zoomControlOptions:{position:google.maps.ControlPosition.RIGHT_CENTER},fullscreenControl:false,gestureHandling:"greedy"});
    return this.map;
  },
  // Show the picked city or start point while the trip is being set up.
  preview({viewport=null,point=null}){
    if(this.kind!=="google")return;
    const map=this.ensure(point||{lat:0,lng:0});
    if(viewport)this.bounds=viewport;
    else if(point){this.bounds=new google.maps.LatLngBounds(point,point);
      this.previewPin&&(this.previewPin.map=null);
      this.previewPin=new google.maps.marker.AdvancedMarkerElement({map,position:point,content:this.pin("hotel","H"),title:"Start"});}
    this.fit();
    if(point&&!viewport)map.setZoom(15);
  },
  // Keep the route in the part of the map the sheet doesn't cover.
  fit(){
    const cover=Sheet.cover();
    if(this.kind==="google"&&this.map&&this.bounds)this.map.fitBounds(this.bounds,{top:72,left:32,right:32,bottom:cover+24});
    else if(this.kind==="svg"&&S.plan){$("#gmap").style.bottom=cover+"px";this.drawSvg(S.plan);this.select(S.sel);}  // redraw so pins keep their size
  },
  // Highlight one stop's pin and bring it into view above the sheet.
  select(i){
    if(this.kind==="google"){
      (this.markers||[]).forEach((m,j)=>{m.content.classList.toggle("sel",j===i);m.zIndex=j===i?30:10;});
      const m=(this.markers||[])[i];
      if(m&&this.map){this.map.panTo(m.position);this.map.panBy(0,Math.round(Sheet.cover()/2));}
    }else $$("#svgmap .svgpin").forEach(g=>g.classList.toggle("sel",Number(g.dataset.i)===i));
  },
  pin(cls,text){const d=document.createElement("div");d.className="pin "+cls;d.textContent=text||"";return d;},
  drawGoogle(p){
    this.ensure({lat:p.hotel.lat,lng:p.hotel.lng});
    this.previewPin&&(this.previewPin.map=null);
    this.overlays.forEach(o=>{o.setMap?o.setMap(null):(o.map=null);});this.overlays=[];
    const {AdvancedMarkerElement}=google.maps.marker,bounds=new google.maps.LatLngBounds();
    const col={walk:cssVar("--green"),transit:cssVar("--blue"),ride:cssVar("--violet")};
    legsOf(p).forEach(l=>{
      const path=l.path.map(([a,b])=>({lat:a,lng:b}));path.forEach(q=>bounds.extend(q));
      const opts={map:this.map,path,strokeColor:col[l.mode],strokeOpacity:l.done?.35:.95,strokeWeight:5};
      if(l.mode==="walk")Object.assign(opts,{strokeOpacity:0,icons:[{icon:{path:google.maps.SymbolPath.CIRCLE,fillColor:col.walk,fillOpacity:l.done?.35:1,strokeOpacity:0,scale:2.6},offset:"0",repeat:"10px"}]});
      this.overlays.push(new google.maps.Polyline(opts));
    });
    const add=(pos,el,title,z,onClick)=>{const m=new AdvancedMarkerElement({map:this.map,position:pos,content:el,title,zIndex:z,gmpClickable:Boolean(onClick)});
      if(onClick)m.addListener("click",onClick);this.overlays.push(m);bounds.extend(pos);return m;};
    p.others.forEach(o=>add({lat:o.lat,lng:o.lng},this.pin("other"),o.name,1));
    add({lat:p.hotel.lat,lng:p.hotel.lng},this.pin("hotel","H"),p.hotel.name,5);
    if(p.end_location.lat!==p.hotel.lat||p.end_location.lng!==p.hotel.lng)add({lat:p.end_location.lat,lng:p.end_location.lng},this.pin("hotel","E"),p.end_location.name,6);
    let n=0;this.markers=p.completed.concat(p.stops).map((st,i)=>add({lat:st.lat,lng:st.lng},this.pin(st.done?"done":st.new?"new":"",st.done?"✓":String(++n)),`Stop ${i+1}: ${st.name}`,10,()=>openStop(i)));
    if(p.completed.length||p.shifted||p.here){const at=p.here||(p.completed.length?p.completed[p.completed.length-1]:p.hotel);add({lat:at.lat,lng:at.lng},this.pin("here"),"You are here",20);}
    this.bounds=bounds;this.fit();
  },
  drawSvg(p){
    const pts=[p.hotel,p.end_location,...(p.here?[p.here]:[]),...p.completed,...p.stops,...p.others].map(q=>[q.lat,q.lng]);
    legsOf(p).forEach(l=>pts.push(...l.path));
    let minLat=Math.min(...pts.map(q=>q[0])),maxLat=Math.max(...pts.map(q=>q[0])),minLng=Math.min(...pts.map(q=>q[1])),maxLng=Math.max(...pts.map(q=>q[1]));
    const kx=Math.cos((minLat+maxLat)/2*Math.PI/180),padLat=(maxLat-minLat)*.08+.002,padLng=(maxLng-minLng)*.08+.002/kx;
    minLat-=padLat;maxLat+=padLat;minLng-=padLng;maxLng+=padLng;
    const W=800,H=Math.round(Math.min(1.2,Math.max(.6,(maxLat-minLat)/((maxLng-minLng)*kx)))*W);
    const sx=W/((maxLng-minLng)*kx),sy=H/(maxLat-minLat),s=Math.min(sx,sy);
    const P=(lat,lng)=>[((lng-minLng)*kx*s+(W-(maxLng-minLng)*kx*s)/2).toFixed(1),((maxLat-lat)*s+(H-(maxLat-minLat)*s)/2).toFixed(1)];
    const col={walk:"var(--green)",transit:"var(--blue)",ride:"var(--violet)"};
    let h=`<rect width="${W}" height="${H}" fill="var(--land)"/>`;
    p.others.forEach(o=>{const [x,y]=P(o.lat,o.lng);h+=`<circle cx="${x}" cy="${y}" r="5" fill="var(--muted)" opacity=".5"><title>${esc(o.name)}</title></circle>`;});
    legsOf(p).forEach(l=>{h+=`<polyline points="${l.path.map(q=>P(q[0],q[1]).join(",")).join(" ")}" fill="none" stroke="${col[l.mode]}" stroke-width="${l.mode==="walk"?5:4.5}" stroke-linecap="round" stroke-linejoin="round"${l.mode==="walk"?' stroke-dasharray="0.5 9"':""} opacity="${l.done?.3:.95}"/>`;});
    const box=$("#gmap"),k=Math.max(1,1/Math.min(box.clientWidth/W,box.clientHeight/H||1)).toFixed(2),at=(x,y)=>`transform="translate(${x} ${y}) scale(${k})"`;  // pins stay about 26px on screen
    const term=(q,label,name)=>{const [x,y]=P(q.lat,q.lng);return `<g ${at(x,y)}><title>${esc(name)}</title><rect x="-12" y="-12" width="24" height="24" rx="5" fill="var(--ink)"/><text y="4.5" text-anchor="middle" style="font:800 13px var(--sans);fill:var(--panel)">${label}</text></g>`;};
    h+=term(p.hotel,"H",p.hotel.name);
    if(p.end_location.lat!==p.hotel.lat||p.end_location.lng!==p.hotel.lng)h+=term(p.end_location,"E",p.end_location.name);
    let n=0;p.completed.concat(p.stops).forEach((st,i)=>{const [x,y]=P(st.lat,st.lng);
      h+=`<g class="svgpin" ${at(x,y)} data-i="${i}" role="button" tabindex="0" aria-label="Stop ${i+1}: ${esc(st.name)}"><circle class="halo" r="19" fill="var(--gold)" opacity="0"/><circle r="13" fill="${st.done?"var(--muted)":"var(--panel)"}" stroke="${st.new?"var(--gold)":st.done?"var(--muted)":"var(--ink)"}" stroke-width="3.5"/><text y="4.5" text-anchor="middle" style="font:800 12.5px var(--sans);fill:${st.done?"var(--panel)":"var(--ink)"}">${st.done?"✓":++n}</text></g>`;});
    if(p.completed.length||p.shifted||p.here){const here=p.here||(p.completed.length?p.completed[p.completed.length-1]:p.hotel);const [x,y]=P(here.lat,here.lng);h+=`<g ${at(x,y)}><circle cx="13" cy="-13" r="7" fill="var(--gold)" stroke="var(--panel)" stroke-width="2"/></g>`;}
    const kmPx=s/111.2;h+=`<g transform="translate(24 ${H-24})"><rect y="-6" width="${kmPx.toFixed(1)}" height="6" fill="var(--ink)"/><text y="-12" style="font:600 13px var(--sans);fill:var(--muted)">1 km</text></g>`;
    const svg=$("#svgmap");svg.setAttribute("viewBox",`0 0 ${W} ${H}`);svg.innerHTML=h;
  }
};
function loadGoogleMaps(key){
  return new Promise((resolve,reject)=>{
    window.__flashPlannerMaps=()=>resolve();
    window.gm_authFailure=()=>{MapView.kind="svg";$("#gmap").innerHTML=`<svg id="svgmap"></svg>`;
      $("#mapNote").textContent="The Maps browser key was rejected. Check its API and referrer restrictions.";if(S.plan)MapView.draw(S.plan);};
    const s=document.createElement("script");
    s.src=`https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&loading=async&libraries=marker,geometry&callback=__flashPlannerMaps`;
    s.async=true;s.onerror=()=>reject(new Error("Maps JavaScript API failed to load"));
    document.head.appendChild(s);
  });
}

// The sketch map's stop pins work like the Google ones: click or Enter opens the stop.
$("#gmap").addEventListener("click",e=>{const g=e.target.closest(".svgpin");if(g)openStop(Number(g.dataset.i));});
$("#gmap").addEventListener("keydown",e=>{const g=e.target.closest(".svgpin");if(g&&(e.key==="Enter"||e.key===" ")){e.preventDefault();openStop(Number(g.dataset.i));}});
