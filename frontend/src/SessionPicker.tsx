'use client'
import {useEffect,useState} from 'react'
import {defaultSelection,eventOption,initialYear,latestSession,sessionOption,type Selection} from './archive'
import type {ArchiveCatalog,ArchiveJob,Snapshot} from './types'
const detail=async(response:Response)=>{try{const body=await response.json();return String(body.detail??response.statusText)}catch{return response.statusText||`HTTP ${response.status}`}}
const message=(e:unknown)=>e instanceof Error?e.message:String(e)
// Year → event → session from F1's archive index. Loading imports the session if needed and
// replays it; progress and errors arrive with the snapshot's `archive` job.
export function SessionPicker({session,archive,disabled,close}:{session?:Snapshot['session'];archive?:ArchiveJob|null;disabled:boolean;close:()=>void}){
 const [year,setYear]=useState<number|null>(null),[catalog,setCatalog]=useState<ArchiveCatalog|null>(null)
 const [selection,setSelection]=useState<Selection>({event:null,session:null})
 const [loading,setLoading]=useState(true),[error,setError]=useState(''),[requested,setRequested]=useState<ArchiveJob|null>(null)
 useEffect(()=>{
  let cancelled=false;setLoading(true);setError('')
  fetch(`/api/archive${year==null?'':`?year=${year}`}`).then(async r=>{if(!r.ok)throw Error(await detail(r));return await r.json() as ArchiveCatalog}).then(next=>{
   if(cancelled)return
   // The first request returns the current season; open on the replay's own season instead.
   const replayYear=year==null?initialYear(session,next.years):null
   if(replayYear!=null&&replayYear!==next.year){setYear(replayYear);return}
   setCatalog(next);setSelection(defaultSelection(next,session));setLoading(false)
  }).catch(e=>{if(!cancelled){setError(message(e));setLoading(false)}})
  return()=>{cancelled=true}
 },[year])
 const job=requested&&archive?.id===requested.id?archive:requested
 useEffect(()=>{if(job?.status===null&&session?.Key===job.key)close()},[job?.status,job?.key,session?.Key])
 const event=catalog?.events.find(e=>e.key===selection.event),chosen=event?.sessions.find(s=>s.key===selection.session)
 const importing=job?.status==='importing'||job?.status===null
 const load=async()=>{
  if(!catalog||!chosen)return
  setError('');setRequested(null)
  try{const response=await fetch('/api/archive/load',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({year:catalog.year,key:chosen.key})});if(!response.ok)throw Error(await detail(response));setRequested(await response.json())}
  catch(e){setError(message(e))}
 }
 const cached=catalog?.events.flatMap(e=>e.sessions).find(s=>s.key===job?.key)?.cached
 const status=importing?`${cached?'Loading':'Downloading'} ${job!.label}…`:loading?'Loading the archive index…':''
 const locked=disabled||loading||importing
 return <section className="picker" aria-label="Change session">
  <div className="picker-fields">
   <label>Year<select aria-label="Year" value={catalog?.year??''} disabled={locked} onChange={e=>setYear(Number(e.target.value))}>{catalog?.years.slice().reverse().map(y=><option key={y} value={y}>{y}</option>)}</select></label>
   <label>Event<select aria-label="Event" value={selection.event??''} disabled={locked||!catalog?.events.length} onChange={e=>{const next=catalog?.events.find(x=>x.key===Number(e.target.value));setSelection({event:next?.key??null,session:latestSession(next)})}}>{catalog?.events.map(e=><option key={e.key} value={e.key}>{eventOption(e,catalog.events)}</option>)}</select></label>
   <label>Session<select aria-label="Session" value={selection.session??''} disabled={locked||!event} onChange={e=>setSelection({...selection,session:Number(e.target.value)})}>{selection.session==null&&<option value="" disabled>No archived sessions</option>}{event?.sessions.map(s=><option key={s.key} value={s.key} disabled={!s.available}>{sessionOption(s)}</option>)}</select></label>
  </div>
  <div className="picker-actions"><span role="status">{status}</span><button onClick={close}>Cancel</button><button className="primary" disabled={locked||!chosen?.available} onClick={load}>Load</button></div>
  {(error||job?.status==='error')&&<div role="alert" className="notice">{error||`Could not load ${job!.label}: ${job!.error}`}</div>}
 </section>
}
