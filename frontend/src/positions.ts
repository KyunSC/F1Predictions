import {useEffect, useState} from 'react'
import type {Snapshot} from './types'
export type Sample={x:number;y:number;z:number;source_timestamp:number;presentation_timestamp:number;status:string|number}
export type Stream={current?:Snapshot;presentation_timestamp?:number;timing_history?:(Snapshot&{presentation_timestamp:number})[];diagnostics?:{coordinate_packets:number;decoded_samples:number;driver_coverage:string[];missing_drivers:string[];rejected:Record<string,number>;gaps_over_5s:Record<string,number>};session_identity:string;generation:number;sequence:number;available:boolean;reason:string|null;age_seconds:number|null;presentation_clock:number;connection:string;synthetic:boolean;samples:Record<string,Sample[]>;replay:Snapshot['replay']}
export function transform(x:number,y:number,rotation:number):[number,number]{const a=rotation*Math.PI/180;return [x*Math.cos(a)-y*Math.sin(a),-(x*Math.sin(a)+y*Math.cos(a))]}
export function presentationClock(s:Stream,elapsed:number,online:boolean){return s.presentation_clock+(online&&s.connection!=='reconnecting'&&s.connection!=='connecting'&&!s.replay?.paused&&!s.replay?.ended?Math.min(elapsed,.6)*(s.replay?.speed||1):0)}
export function marker(samples:Sample[],time:number,reduced=false){
 const previous=samples.filter(s=>s.presentation_timestamp<=time).at(-1)
 if(!previous)return null
 const age=Math.max(0,time-previous.presentation_timestamp)
 if(age>15)return null
 const next=samples.find(s=>s.presentation_timestamp>time)
 if(reduced||!next||next.presentation_timestamp-previous.presentation_timestamp>2)return {...previous,age,stale:age>5}
 const f=(time-previous.presentation_timestamp)/(next.presentation_timestamp-previous.presentation_timestamp)
 return {...previous,x:previous.x+(next.x-previous.x)*f,y:previous.y+(next.y-previous.y)*f,age,stale:age>5}
}
export function usePositions(){
 const [value,setValue]=useState<{stream:Stream;received:number}|null>(null),[online,setOnline]=useState(false)
 useEffect(()=>{let disposed=false;let socket:WebSocket;let retry:ReturnType<typeof setTimeout>;const connect=()=>{socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/positions`);socket.onmessage=e=>{setOnline(true);setValue({stream:JSON.parse(e.data),received:performance.now()})};socket.onclose=()=>{setOnline(false);if(!disposed)retry=setTimeout(connect,2000)};socket.onerror=()=>socket.close()};connect();return()=>{disposed=true;clearTimeout(retry);socket?.close()}},[])
 return {value,online}
}
// Reject obvious coordinate-frame mismatch. OffTrack points remain untouched.
export function aligned(outline:[number,number][],samples:Record<string,Sample[]>){
 const onTrack=Object.values(samples).map(s=>s.at(-1)).filter(s=>s&&(s.status==='OnTrack'||s.status===0)) as Sample[]
 if(!onTrack.length)return true
 const xs=outline.map(p=>p[0]),ys=outline.map(p=>p[1]);const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys)
 const margin=Math.max(maxX-minX,maxY-minY)*.1
 return onTrack.some(s=>s.x>=minX-margin&&s.x<=maxX+margin&&s.y>=minY-margin&&s.y<=maxY+margin)
}

export function timingAt(stream:Stream,time:number){
 return stream.timing_history?.filter(frame=>frame.presentation_timestamp<=time&&frame.generation===stream.generation&&frame.session_identity===stream.session_identity).at(-1)
}
// One clock and one transport drive both the tower and the map. Current health
// and replay controls remain outside the delayed presentation state.
export function usePresentation(){
 const {value,online}=usePositions()
 const [clock,setClock]=useState({time:0,identity:''})
 useEffect(()=>{
  if(!value||!online)return
  let id:number
  const tick=()=>{setClock({time:Math.min(value.stream.presentation_clock,presentationClock(value.stream,(performance.now()-value.received)/1000,online)-1),identity:value.stream.session_identity});id=requestAnimationFrame(tick)}
  tick();return()=>cancelAnimationFrame(id)
 },[value,online])
 const stream=value?.stream
 const time=stream&&clock.identity!==stream.session_identity?stream.presentation_clock-1:clock.time
 const current=stream?.current
 const frame=stream?timingAt(stream,time):undefined
 const data=current?{...current,...frame,connection:current.connection,replay:current.replay,drivers:frame?.drivers||[],messages:frame?.messages||[],laps:frame?.laps||{},track:frame?.track||{},weather:frame?.weather||{}}:null
 return {stream,online,time,data}
}
