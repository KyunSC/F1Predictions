import {useEffect,useMemo,useRef,useState} from 'react'
import type {Driver} from './types'
import {aligned,transform,type Stream} from './positions'
import {atDistance,circuit,Projector,projectedMarker,placeLabels,labelOffsets,type LabelOffset} from './projection'
import {ghostDistance,lapSeconds,rejoinSummary,travelDirection} from './pitRejoin'
type Geometry={session_identity:string;available:boolean;reason:string;outline:[number,number][];rotation:number;attribution:string;provenance:string;synthetic:boolean;pending?:boolean}
export function TrackMap({stream,online,time,drivers,selected,select,reset,pitLoss}:{stream?:Stream;online:boolean;time:number;drivers:Driver[];selected:string|null;select:(n:string)=>void;reset:()=>void;pitLoss?:number|null}){
 const [geometry,setGeometry]=useState<Geometry|null>(null),[error,setError]=useState(''),[reduced,setReduced]=useState(false)
 const svg=useRef<SVGSVGElement>(null),offsets=useRef(new Map<string,LabelOffset>()),[viewport,setViewport]=useState({width:700,height:340})
 const identity=stream?.session_identity
 useEffect(()=>{const query=matchMedia('(prefers-reduced-motion: reduce)');const update=()=>setReduced(query.matches);update();query.addEventListener('change',update);return()=>query.removeEventListener('change',update)},[])
 useEffect(()=>{reset();offsets.current=new Map();setGeometry(null);setError('');if(!identity)return;const controller=new AbortController();let retry:ReturnType<typeof setTimeout>|undefined
 // A pending outline is being traced from car coordinates; ask again until it is ready.
 const load=()=>fetch('/api/track-map',{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('Geometry request failed');return r.json()}).then(g=>{if(controller.signal.aborted)return;if(g.session_identity===identity){setGeometry(g);if(g.pending)retry=setTimeout(load,3000)}else setError('Session changed; waiting for geometry')}).catch(e=>{if(e.name!=='AbortError')setError(String(e))})
 load();return()=>{controller.abort();clearTimeout(retry)}},[identity])
 const geometryCurrent=geometry!==null&&geometry.session_identity===identity&&geometry.available
 const points=geometryCurrent?geometry!.outline.map(([x,y])=>transform(x,y,geometry!.rotation)):[]
 const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const minX=Math.min(...xs),minY=Math.min(...ys),width=Math.max(...xs)-minX,height=Math.max(...ys)-minY,pad=Math.max(width,height)*.08
 const alignment=geometryCurrent?aligned(geometry!.outline,stream?.samples||{}):true
 const projector=useMemo(()=>geometry?.available?new Projector(circuit(geometry.outline)):null,[geometry,identity,stream?.generation])
 const histories=useMemo(()=>Object.entries(stream?.samples||{}).map(([n,s])=>({n,s:projector?.history(n,s)||[]})),[stream,projector])
 const marks=histories.map(({n,s})=>({n,p:projector?projectedMarker(s,time,projector.track,reduced):null,d:drivers.find(d=>d.number===n)})).filter(m=>m.p!==null)
 useEffect(()=>{if(!svg.current||typeof ResizeObserver==='undefined')return;const observer=new ResizeObserver(entries=>{const {width,height}=entries[0].contentRect;setViewport({width,height})});observer.observe(svg.current);return()=>observer.disconnect()},[geometryCurrent])
 const viewWidth=Math.max(width+pad*2,(height+pad*2)*(viewport.width-20)/(viewport.height-20)),viewHeight=Math.max(height+pad*2,(width+pad*2)*(viewport.height-20)/(viewport.width-20))
 const left=minX-(viewWidth-width)/2,top=minY-(viewHeight-height)/2
 const size=Math.max(width,height),scale=Math.min((viewport.width-20)/(width+pad*2),(viewport.height-20)/(height+pad*2)),font=Math.max(size*.018,11/scale),radius=Math.max(size*.008,5/scale)
 // Code-only tags sit just above and right of their dot; a pack pushes them
 // elsewhere, and only then is a leader line drawn back to the car.
 const tagHeight=font*1.5,prefer={dx:radius*.3/tagHeight,dy:-(radius*1.4/tagHeight+1.2)}
 const anchors=marks.map(({n,p})=>{const [x,y]=transform(p!.x,p!.y,geometry?.rotation||0);return {number:n,x,y,width:font*3.1,height:tagHeight}})
 const labels=placeLabels(anchors,{left,right:left+viewWidth,top,bottom:top+viewHeight},anchors.map(({number,x,y})=>{const r=radius*(number===selected?1.4:1);return {number:"",x:x-r,y:y-r,width:r*2,height:r*2}}),offsets.current,prefer)
 offsets.current=labelOffsets(anchors,labels)
 const displaced=(n:string)=>{const o=offsets.current.get(n)!;return Math.hypot(o.dx-prefer.dx,o.dy-prefer.dy)>.5}
 const chosen=marks.find(m=>m.n===selected),driver=drivers.find(d=>d.number===selected)
 const ghostAt=chosen&&projector&&driver?.pit_rejoin?ghostDistance(chosen.p!.distance,travelDirection(histories.find(h=>h.n===selected)!.s.filter(s=>s.presentation_timestamp<=time),projector.track.length),pitLoss,lapSeconds(driver.last_lap)??lapSeconds(driver.best_lap),projector.track.length):null
 const ghost=ghostAt===null?null:transform(...atDistance(projector!.track,ghostAt),geometry?.rotation||0),ghostColor=`#${/^[0-9a-f]{6}$/i.test(driver?.color||'')?driver!.color:'888888'}`
 const status=!online||stream?.connection==='connecting'||stream?.connection==='reconnecting'?'Disconnected · frozen':stream?.replay?`Replay${stream.synthetic?' · synthetic demo':''}${stream.replay.paused?' · paused':stream.replay.ended?' · finished':''}`:'Live coordinates'
 return <section className="panel track-map"><div className="panel-heading"><h2>Track map</h2><span>{status}</span></div><p className="description">Approximate track-projected positions{stream?.synthetic?' · synthetic demo':''} · Pit-lane and off-track measurements also project onto the outline. Track location differs from race position. · 1s display buffer{reduced?' · reduced motion':''}</p>
 {!stream?.available&&<p role="status" className="description">Track map unavailable: {stream?.reason||'Awaiting coordinates'}</p>}
 {(!geometryCurrent||!alignment)?<p role="status" className="empty">{!alignment?'Track map unavailable: coordinates do not align with circuit geometry':!error&&geometry?.pending?geometry.reason:error||geometry?.reason?`Track map unavailable: ${error||geometry?.reason}`:!online?'Track map unavailable: position stream disconnected':'Loading circuit geometry…'}</p>:<>
 {(stream?.age_seconds!=null&&stream.age_seconds>5)&&<p role="status" className="description">Position stream stale</p>}
 <svg ref={svg} data-presentation-time={time} aria-label="Circuit and driver coordinates" viewBox={`${left} ${top} ${viewWidth} ${viewHeight}`}>
 <polyline points={[...points,points[0]].map(p=>p.join(',')).join(' ')} fill="none" stroke="#697486" strokeWidth={Math.max(width,height)*.012} strokeLinejoin="round"/>
 {marks.filter(({n})=>displaced(n)).map(({n,p})=>{const [x,y]=transform(p!.x,p!.y,geometry!.rotation),label=labels.find(l=>l.number===n)!,lx=Math.max(label.x,Math.min(label.x+label.width,x)),ly=Math.max(label.y,Math.min(label.y+label.height,y));return <line key={n} x1={x} y1={y} x2={lx} y2={ly} stroke="#8e9aab" strokeWidth={size*.0015} opacity={p!.stale?.45:.8} pointerEvents="none"/>})}
 {ghost&&<g role="img" aria-label={`${driver?.code||selected} rejoin point if pitted now`} className="pit-ghost" pointerEvents="none" transform={`translate(${ghost[0]} ${ghost[1]})`}><circle r={radius*1.4} fill="none" stroke={ghostColor} strokeWidth={radius*.35} strokeDasharray={`${radius*.7} ${radius*.45}`}/><text y={-radius*2.3} textAnchor="middle" fontSize={font*.8} fontWeight={700} fill="#fff">PIT P{driver!.pit_rejoin!.position}</text></g>}
 {marks.sort((a,b)=>Number(a.n===selected)-Number(b.n===selected)).map(({n,p,d})=>{const [x,y]=transform(p!.x,p!.y,geometry!.rotation);const label=labels.find(l=>l.number===n)!;const lx=label.x-x,ly=label.y-y,active=selected===n,color=`#${/^[0-9a-f]{6}$/i.test(d?.color||'')?d!.color:'888888'}`;return <g key={n} data-driver-number={n} data-lap-distance={p!.distance} role="button" tabIndex={0} aria-label={`Select ${d?.name||n}`} aria-pressed={active} onClick={()=>select(n)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(n)}}} className="car-marker" opacity={p!.stale?.45:1} transform={`translate(${x} ${y})`}>
  <circle r={radius*(active?1.4:1)} fill={active?'#fff':color} stroke={active?color:'#10131b'} strokeWidth={radius*(active?.5:.25)}/>
  <rect x={lx} y={ly} width={label.width} height={label.height} rx={font*.15} fill={active?color:'#10131b'} fillOpacity={active?1:.88}/>
  {!active&&<rect x={lx} y={ly+label.height-font*.16} width={label.width} height={font*.16} fill={color}/>}
  <text x={lx+label.width/2} y={ly+label.height*.7} textAnchor="middle" fontSize={font} fontWeight={700} letterSpacing={font*.04} fill="#fff">{d?.code||n}</text></g>})}
 </svg><p className="description">{geometry!.attribution}{geometry!.synthetic?' · Synthetic coordinates and outline, not measured data':''}</p></>}
 {stream?.diagnostics&&<details className="description"><summary>Replay coordinate diagnostics</summary><p>{stream.diagnostics.coordinate_packets} packets · {stream.diagnostics.decoded_samples} decoded samples · {stream.diagnostics.driver_coverage.length} numbers · geometry {geometryCurrent&&alignment?'available':'unavailable'}</p><p>Missing drivers: {stream.diagnostics.missing_drivers.join(', ')||'none'} · Rejected: {JSON.stringify(stream.diagnostics.rejected)} · Gaps over 5s: {JSON.stringify(stream.diagnostics.gaps_over_5s)}</p></details>}
 <div className="panel-note" aria-live="polite">{selected?`${driver?.name||selected} · P${driver?.position||'—'} · coordinate age ${chosen?chosen.p!.age.toFixed(1)+'s':'unavailable'}`:'Select a car or a driver in the timing tower.'}{driver&&<div className="pit-note">{rejoinSummary(driver,drivers)}{ghost?' · dashed ring marks the approximate on-track rejoin point':''}</div>}</div></section>
}
