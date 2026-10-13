import type {Snapshot} from './types'
export type ReplayCommand={action:'pause'|'resume'|'restart'}|{action:'speed';speed:number}
// Space pauses or resumes, R restarts, 1/2/5 set the speed.
export function replayKey(key:string,replay:NonNullable<Snapshot['replay']>):ReplayCommand|null{
 if(key===' ')return replay.ended?null:{action:replay.paused?'resume':'pause'}
 if(key==='r'||key==='R')return {action:'restart'}
 if(['1','2','5'].includes(key)&&Number(key)!==replay.speed)return {action:'speed',speed:Number(key)}
 return null
}
// Keys typed into a control belong to that control, not to the replay shortcuts.
// A slider (the seek bar) uses only arrow, page and home/end keys, so shortcuts still apply there.
export const isInteractive=(target:EventTarget|null)=>typeof Element!=='undefined'&&target instanceof Element&&!!target.closest('input:not([type="range"]),select,textarea,button,a,[contenteditable="true"],[role="button"]')
// Browser storage is a per-viewer convenience: private windows can block it, so failures are ignored.
export function stored(key:string){try{return localStorage.getItem(key)}catch{return null}}
export function store(key:string,value:string|null){try{if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value)}catch{}}
