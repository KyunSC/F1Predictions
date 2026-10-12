import type {ArchiveCatalog,ArchiveEvent,ArchiveSession,Snapshot} from './types'
export type Selection={event:number|null;session:number|null}
export const sessionOption=(s:ArchiveSession)=>s.name+(!s.available?' · Not archived yet':s.cached?' · downloaded':'')
// Index order is chronological within a meeting, so the last available session is the latest.
export const latestSession=(event?:ArchiveEvent)=>event?.sessions.filter(s=>s.available).at(-1)?.key??null
export function initialYear(session:Snapshot['session']|undefined,years:number[]){
 const year=Number(session?.StartDate?.slice(0,4));return years.includes(year)?year:null
}
// The replay on screen if it is in this season, else its meeting by name, else the newest archived session.
export function defaultSelection(catalog:ArchiveCatalog,session?:Snapshot['session']):Selection{
 const current=catalog.events.find(e=>e.sessions.some(s=>s.key===session?.Key))
 if(current)return {event:current.key,session:session!.Key!}
 const named=initialYear(session,catalog.years)===catalog.year?catalog.events.find(e=>e.event===session?.Meeting?.Name):undefined
 if(named)return {event:named.key,session:latestSession(named)}
 const newest=catalog.events.flatMap(e=>e.sessions.filter(s=>s.available).map(s=>({event:e.key,session:s.key,start:s.start_utc||''})))
  .reduce<{event:number;session:number;start:string}|null>((best,s)=>!best||s.start>best.start?s:best,null)
 return newest?{event:newest.event,session:newest.session}:{event:catalog.events[0]?.key??null,session:null}
}
// 2026 has two "Pre-Season Testing" meetings; a repeated name gets its first day's date.
export function eventOption(event:ArchiveEvent,events:ArchiveEvent[]){
 const repeated=events.filter(e=>e.event===event.event).length>1,date=event.sessions[0]?.start_utc?.slice(0,10)
 return repeated&&date?`${event.event} · ${date}`:event.event
}
