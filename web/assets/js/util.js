/* ============ helpers ============ */
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt=m=>{m=Math.round(m);const h=Math.floor(m/60)%24,mm=((m%60)+60)%60;return `${((h+11)%12)+1}:${String(mm).padStart(2,"0")} ${h>=12?"pm":"am"}`;};
const money=(n,cur)=>{try{return new Intl.NumberFormat(undefined,{style:"currency",currency:cur,maximumFractionDigits:0}).format(n);}catch{return `${cur} ${n}`.trim();}};
const priceText=pr=>{
  if(pr.level)return "$".repeat(pr.level);
  let low;try{low=new Intl.NumberFormat(undefined,{style:"currency",currency:pr.currency,currencyDisplay:"narrowSymbol",maximumFractionDigits:0}).format(pr.low);}catch{low=`$${pr.low}`;}
  return pr.high?`${low}–${pr.high}`:`${low}+`;
};
const hm=m=>{m=Math.round(m);const h=Math.floor(m/60),mm=m%60;return h?`${h}h ${String(mm).padStart(2,"0")}m`:`${mm} min`;};
const cssVar=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const splitList=s=>s.split(/[,\n]/).map(x=>x.trim()).filter(Boolean);
const PRESETS=["architecture","food","views","history","art","museums","nature","shopping","nightlife","coffee"];
const MODE_TXT={walk:"Walk only",transit:"Walk + transit",ride:"Walk + ride"};
const USES_POSITION=["rain","late","tired","skip","include"];

const S={likes:new Set(["architecture","food","views"]),skips:new Set(["museums"]),mode:"transit",blocks:true,
  tags:[...PRESETS],appointments:[],lastParsed:null,fromNotes:null,startPlace:null,endPlace:null,busy:false,plan:null,sid:null,
  days:null,activeDay:0,view:"setup",sel:null,detailId:null};

