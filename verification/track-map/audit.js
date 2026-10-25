// Run in the browser console on the dashboard page served against
// dashboard.verify_replay. All geometry is measured from the rendered SVG; this
// exercises the actual application, transport and clock. Checkpoints default to
// the Suzuka 2025 recording; pass others for a different recording.
const SUZUKA_CHECKPOINTS=[3523.5,3600,3630,3648.5];
window.trackAudit = async function(name='desktop',checkpoints=SUZUKA_CHECKPOINTS) {
 const results={viewport:{width:innerWidth,height:innerHeight},runs:[]};
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const post=(url,body)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const control=(action,speed)=>post('/api/replay/control',{action,speed});
 const distance=(p,a,b)=>{const dx=b.x-a.x,dy=b.y-a.y,f=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy||1)));return Math.hypot(p.x-a.x-dx*f,p.y-a.y-dy*f)};
 function inspect(run){
  const svg=document.querySelector('.track-map svg'),tower=document.querySelector('.timing');if(!svg)return;
  run.frames++;
  const moment=Number(svg.dataset.presentationTime);
  run.firstMoment??=moment;run.lastMoment=moment;
  if(svg.dataset.presentationTime!==tower.dataset.presentationTime)run.errors.push('Clock mismatch');
  const points=[...svg.querySelector('polyline').points].map(p=>new DOMPoint(p.x,p.y).matrixTransform(svg.getScreenCTM()));
  const cars=[...svg.querySelectorAll('.car-marker')],labels=cars.map(g=>g.querySelector('rect').getBoundingClientRect());
  // Every check below is per marker, so an empty map would otherwise pass.
  run.minMarkers=Math.min(run.minMarkers??Infinity,cars.length);
  cars.forEach((g,i)=>{
   const p=new DOMPoint(0,0).matrixTransform(g.getScreenCTM());
   const error=Math.min(...points.slice(1).map((b,j)=>distance(p,points[j],b)));
   run.maxPixelError=Math.max(run.maxPixelError,error);
   if(error>1)run.errors.push(`Off circuit: ${g.dataset.driverNumber} ${error}`);
   const n=g.dataset.driverNumber,along=Number(g.dataset.lapDistance),previous=run.previous?.[n];
   const poly=svg.querySelector('polyline').points;
   const length=[...poly].slice(1).reduce((sum,p,j)=>sum+Math.hypot(p.x-poly[j].x,p.y-poly[j].y),0);
   if(previous&&moment>previous.time&&moment-previous.time<2){
    const delta=((along-previous.along+length/2)%length+length)%length-length/2;
    run.maxLapStep=Math.max(run.maxLapStep||0,Math.abs(delta));
    if(Math.abs(delta)>length*.05)run.errors.push(`Branch jump: ${n}`);
   }
   run.previous??={};run.previous[n]={along,time:moment};
   const row=tower.querySelector(`tr[data-driver-number="${g.dataset.driverNumber}"]`);
   const code=row?.querySelector('button').textContent,position=row?.querySelector('td').textContent;
   // Tags show the driver code (racing number without one); official position lives in
   // the tower row, whose button falls back to the name instead.
   const tag=g.querySelector('text').textContent;
   if(!row||(tag!==code&&tag!==n))run.errors.push(`Identity mismatch ${g.dataset.driverNumber}`);
   run.positions??={};
   if(run.positions[n]!==position){run.positionChanges??=[];run.positionChanges.push({number:n,position,time:moment});run.positions[n]=position}
   const a=labels[i];labels.slice(i+1).forEach(b=>{if(a.left<b.right-.5&&a.right>b.left+.5&&a.top<b.bottom-.5&&a.bottom>b.top+.5)run.errors.push(`Label overlap: ${g.dataset.driverNumber}`)});
  });
 }
 // Suzuka: the position change at 3523.924 is SAINZ/HULKENBERG. 3600 is a
 // compact field at the crossing/hairpin. Additional lap/corner checkpoints.
 for(const at of checkpoints)for(const speed of [1,2,5]){
  await post(`/api/verify/checkpoint/${at}`,{});await wait(650);
  await control('speed',speed);await control('resume');
  const run={at,speed,frames:0,maxPixelError:0,errors:[]};results.runs.push(run);
  const end=performance.now()+3000;
  while(performance.now()<end){inspect(run);await new Promise(requestAnimationFrame)}
  await control('pause');await wait(350);
  const frozen=document.querySelector('.track-map svg')?.outerHTML;
  await wait(500);
  if(frozen!==document.querySelector('.track-map svg')?.outerHTML)run.errors.push('Pause did not freeze map');
  if(!(run.minMarkers>0))run.errors.push('No markers drawn');
  run.errors=[...new Set(run.errors)];
  await post('/api/verify/results/'+name,results);
 }
 await post(`/api/verify/checkpoint/${checkpoints[1]??checkpoints[0]}`,{});await wait(500);
 const car=document.querySelector('.car-marker');car.focus();car.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await wait(50);
 const row=document.querySelector(`.timing tr[data-driver-number="${car.dataset.driverNumber}"] button`);
 results.keyboardSelection=row.getAttribute('aria-pressed')==='true';
 // Select a different driver from the tower so the check cannot pass on the earlier choice.
 const marker=n=>document.querySelector(`.car-marker[data-driver-number="${n}"]`);
 const other=[...document.querySelectorAll('.car-marker')].map(g=>g.dataset.driverNumber).find(n=>n!==car.dataset.driverNumber);
 document.querySelector(`.timing tr[data-driver-number="${other}"] button`).click();await wait(50);
 results.towerSelection=marker(other)?.getAttribute('aria-pressed')==='true'&&marker(car.dataset.driverNumber)?.getAttribute('aria-pressed')==='false';
 // The selected driver is remembered across restarts while that car is in the session.
 await control('restart');await wait(1500);
 results.restartKeptSelection=marker(other)?.getAttribute('aria-pressed')==='true';
 await post(`/api/verify/checkpoint/${checkpoints[1]??checkpoints[0]}`,{});await wait(500);
 await post('/api/verify/results/'+name,results);
 console.log('TRACK AUDIT SAVED',name,results);return results;
};

window.trackFaultAudit=async function(at=3600,name='faults'){
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const post=(url,body={})=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const control=(action,speed)=>post('/api/replay/control',{action,speed});
 const map=()=>document.querySelector('.track-map svg')?.outerHTML;
 const tower=()=>document.querySelector('.timing')?.outerHTML;
 const results={};
 await post(`/api/verify/checkpoint/${at}`);await control('speed',1);await control('resume');await wait(500);
 await post('/api/verify/fault/disconnect');await wait(400);
 const frozenMap=map(),frozenTower=tower();await wait(1200);
 results.disconnectMapFrozen=map()===frozenMap;results.disconnectTowerFrozen=tower()===frozenTower;
 results.disconnectVisible=document.body.textContent.includes('Disconnected · frozen');
 await wait(3500);results.reconnected=!document.body.textContent.includes('Disconnected · frozen')&&map()!==frozenMap;
 await control('pause');await post(`/api/verify/checkpoint/${at}`);await control('speed',5);await post('/api/verify/fault/positions');await control('resume');
 await wait(1800);
 const stale=[...document.querySelectorAll('.car-marker')];results.staleFaded=stale.length>0&&stale.every(g=>g.getAttribute('opacity')==='0.45');
 results.staleCount=document.querySelectorAll('.car-marker').length;
 await wait(1600);results.hiddenAfter15Seconds=document.querySelectorAll('.car-marker').length===0;
 await wait(1200);results.freshCoordinatesReturn=document.querySelectorAll('.car-marker').length===results.staleCount&&results.staleCount>0;
 await control('pause');await post('/api/verify/results/'+name,results);await post(`/api/verify/checkpoint/${at}`);console.log('FAULT AUDIT',results);return results;
};
window.baselineAudit=async function(){
 const svg=document.querySelector('.track-map svg'),matrix=svg.getScreenCTM();
 const points=[...svg.querySelector('polyline').points].map(p=>new DOMPoint(p.x,p.y).matrixTransform(matrix));
 const cars=[...svg.querySelectorAll('.car-marker')].map(g=>{
  const p=new DOMPoint(0,0).matrixTransform(g.getScreenCTM());
  const pixelError=Math.min(...points.slice(1).map((b,i)=>{const a=points[i],dx=b.x-a.x,dy=b.y-a.y,f=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/(dx*dx+dy*dy||1)));return Math.hypot(p.x-a.x-dx*f,p.y-a.y-dy*f)}));
  return {driver:g.getAttribute('aria-label'),pixelError};
 });
 const frame=await fetch('/api/verify/frame').then(r=>r.json());
 const buffered=frame.timing_history.filter(h=>h.presentation_timestamp<=frame.presentation_timestamp).at(-1);
 const mismatches=frame.current.drivers.filter(d=>{const old=buffered.drivers.find(o=>o.number===d.number);return old.gap!==d.gap||old.position!==d.position}).map(d=>({number:d.number,code:d.code,current:d,buffered:buffered.drivers.find(o=>o.number===d.number)}));
 const result={at:frame.presentation_clock,bufferedAt:frame.presentation_timestamp,viewport:{width:innerWidth,height:innerHeight},cars,mismatches};
 await fetch('/api/verify/results/baseline',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(result)});console.log(result);
};
