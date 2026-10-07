import {useEffect,useRef,useState} from 'react'
import type {Driver} from './types'
import {aligned,marker,presentationClock,transform,usePositions} from './positions'
type Geometry={session_identity:string;available:boolean;reason:string;outline:[number,number][];rotation:number;attribution:string;provenance:string;synthetic:boolean}
export function TrackMap({drivers,selected,select,reset}:{drivers:Driver[];selected:string|null;select:(n:string)=>void;reset:()=>void}){
 const {value,online}=usePositions(),[geometry,setGeometry]=useState<Geometry|null>(null),[error,setError]=useState(''),[clock,setClock]=useState(0),[reduced,setReduced]=useState(false)
 const frozen=useRef(0), identity=value?.stream.session_identity
 useEffect(()=>{const query=matchMedia('(prefers-reduced-motion: reduce)');const update=()=>setReduced(query.matches);update();query.addEventListener('change',update);return()=>query.removeEventListener('change',update)},[])
 useEffect(()=>{reset();setGeometry(null);setError('');if(!identity)return;const controller=new AbortController();fetch('/api/track-map',{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('Geometry request failed');return r.json()}).then(g=>{if(controller.signal.aborted)return;if(g.session_identity===identity)setGeometry(g);else setError('Session changed; waiting for geometry')}).catch(e=>{if(e.name!=='AbortError')setError(String(e))});return()=>controller.abort()},[identity])
 useEffect(()=>{if(!value||!online)return;let id:number;const tick=()=>{const t=presentationClock(value.stream,(performance.now()-value.received)/1000,online);frozen.current=t;setClock(t);id=requestAnimationFrame(tick)};tick();return()=>cancelAnimationFrame(id)},[value,online])
 const stream=value?.stream, time=(online?clock:frozen.current)-1
 const geometryCurrent=geometry!==null&&geometry.session_identity===identity&&geometry.available
 const points=geometryCurrent?geometry!.outline.map(([x,y])=>transform(x,y,geometry!.rotation)):[]
 const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const minX=Math.min(...xs),minY=Math.min(...ys),width=Math.max(...xs)-minX,height=Math.max(...ys)-minY,pad=Math.max(width,height)*.08
 const alignment=geometryCurrent?aligned(geometry!.outline,stream?.samples||{}):true
 const marks=Object.entries(stream?.samples||{}).map(([n,s])=>({n,p:marker(s,time,reduced),d:drivers.find(d=>d.number===n)})).filter(m=>m.p!==null)
 const chosen=marks.find(m=>m.n===selected),driver=drivers.find(d=>d.number===selected)
 const status=!online||stream?.connection==='connecting'||stream?.connection==='reconnecting'?'Disconnected · frozen':stream?.replay?`Replay${stream.synthetic?' · synthetic demo':''}${stream.replay.paused?' · paused':stream.replay.ended?' · finished':''}`:'Live coordinates'
 return <section className="panel track-map"><div className="panel-heading"><h2>Track map</h2><span>{status}</span></div><p className="description">{stream?.synthetic?'Synthetic coordinates':'Actual coordinates'} · Track location differs from race position (lapped cars and pit stops). · 1s display buffer{reduced?' · reduced motion':''}</p>
 {!stream?.available&&<p role="status" className="description">Track map unavailable: {stream?.reason||'Awaiting coordinates'}</p>}
 {(!geometryCurrent||!alignment)?<p role="status" className="empty">{!alignment?'Track map unavailable: coordinates do not align with circuit geometry':error||geometry?.reason?`Track map unavailable: ${error||geometry?.reason}`:!online?'Track map unavailable: position stream disconnected':'Loading circuit geometry…'}</p>:<>
 {(stream?.age_seconds!=null&&stream.age_seconds>5)&&<p role="status" className="description">Position stream stale</p>}
 <svg aria-label="Circuit and driver coordinates" viewBox={`${minX-pad} ${minY-pad} ${width+pad*2} ${height+pad*2}`}>
 <polyline points={points.map(p=>p.join(',')).join(' ')} fill="none" stroke="#697486" strokeWidth={Math.max(width,height)*.012} strokeLinejoin="round"/>
 {marks.sort((a,b)=>Number(a.n===selected)-Number(b.n===selected)).map(({n,p,d})=>{const [x,y]=transform(p!.x,p!.y,geometry!.rotation);const radius=Math.max(width,height)*.012;return <g key={n} role="button" tabIndex={0} aria-label={`Select ${d?.name||n}`} aria-pressed={selected===n} onClick={()=>select(n)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(n)}}} className="car-marker" opacity={p!.stale?.45:1} transform={`translate(${x} ${y})`}><circle r={radius*(selected===n?1.5:1)} fill={`#${/^[0-9a-f]{6}$/i.test(d?.color||'')?d!.color:'888888'}`} stroke={selected===n?'#fff':'#10131b'} strokeWidth={radius*.3}/><text x={radius*1.6} y={radius*.5} fontSize={radius*1.8} fill="white" stroke="#10131b" strokeWidth={radius*.4} paintOrder="stroke">{d?.code||n}</text></g>})}
 </svg><p className="description">{geometry!.attribution}{geometry!.synthetic?' · Synthetic coordinates and outline, not measured data':''}</p></>}
 {stream?.diagnostics&&<details className="description"><summary>Replay coordinate diagnostics</summary><p>{stream.diagnostics.coordinate_packets} packets · {stream.diagnostics.decoded_samples} decoded samples · {stream.diagnostics.driver_coverage.length} numbers · geometry {geometryCurrent&&alignment?'available':'unavailable'}</p><p>Missing drivers: {stream.diagnostics.missing_drivers.join(', ')||'none'} · Rejected: {JSON.stringify(stream.diagnostics.rejected)} · Gaps over 5s: {JSON.stringify(stream.diagnostics.gaps_over_5s)}</p></details>}
 <div className="panel-note" aria-live="polite">{selected?`${driver?.name||selected} · P${driver?.position||'—'} · coordinate age ${chosen?chosen.p!.age.toFixed(1)+'s':'unavailable'}`:'Select a car or a driver in the timing tower.'}</div></section>
}
