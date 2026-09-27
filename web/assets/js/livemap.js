/* ============ planning on the map: candidate places drop in as the server finds them ============ */
// "found" places appear as faint dots; the "shortlist" the planner keeps turns solid.
// The finished plan replaces them (MapView.draw clears every overlay).
const LiveMap={
  places:new Map(),
  reset(){
    this.places.clear();
    if(MapView.kind==="google"){MapView.overlays.forEach(o=>{o.setMap?o.setMap(null):(o.map=null);});MapView.overlays=[];}
    else if($("#svgmap"))$("#svgmap").innerHTML="";
    $("#liveCount").textContent="";
  },
  add(list,stage){
    const short=stage==="shortlist";
    list.forEach(p=>{const had=this.places.get(p.id);
      if(had){had.short=had.short||short;had.el?.classList.toggle("short",had.short);}
      else this.places.set(p.id,{...p,short,el:null});});
    const n=[...this.places.values()].filter(p=>p.short).length;
    $("#liveCount").textContent=short?`${n} places made the shortlist`:`${this.places.size} places found`;
    $("#mapEmpty").hidden=true;
    MapView.kind==="google"?this.drawGoogle():this.drawSvg();
  },
  drawGoogle(){
    const bounds=new google.maps.LatLngBounds(),map=MapView.ensure({lat:0,lng:0});
    let delay=0;
    this.places.forEach(p=>{
      bounds.extend({lat:p.lat,lng:p.lng});
      if(p.el)return;
      p.el=MapView.pin("cand"+(p.short?" short":""));p.el.style.animationDelay=`${Math.min(delay+=25,900)}ms`;
      MapView.overlays.push(new google.maps.marker.AdvancedMarkerElement({map,position:{lat:p.lat,lng:p.lng},content:p.el,title:p.name}));
    });
    MapView.bounds=bounds;MapView.fit();
  },
  drawSvg(){
    const svg=$("#svgmap"),pts=[...this.places.values()];if(!svg||!pts.length)return;
    $("#gmap").style.bottom=Sheet.cover()+"px";
    const lat=pts.map(p=>p.lat),lng=pts.map(p=>p.lng),kx=Math.cos((Math.min(...lat)+Math.max(...lat))/2*Math.PI/180);
    const x0=Math.min(...lng),y1=Math.max(...lat),w=Math.max(...lng)-x0||.01,h=y1-Math.min(...lat)||.01;
    const W=800,H=Math.round(Math.min(1.2,Math.max(.6,h/(w*kx)))*W),s=Math.min(W*.9/(w*kx),H*.9/h);
    const box=$("#gmap"),k=Math.max(1,1/Math.min(box.clientWidth/W,box.clientHeight/H||1)).toFixed(2);
    svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
    svg.innerHTML=`<rect width="${W}" height="${H}" fill="var(--land)"/>`+pts.map((p,i)=>{
      const x=((p.lng-x0)*kx*s+(W-w*kx*s)/2).toFixed(1),y=((y1-p.lat)*s+(H-h*s)/2).toFixed(1);
      return `<circle class="cand${p.short?" short":""}" cx="${x}" cy="${y}" r="${(p.short?7:4)*k}" style="animation-delay:${Math.min(i*25,900)}ms"><title>${esc(p.name)}</title></circle>`;}).join("");
  }
};
