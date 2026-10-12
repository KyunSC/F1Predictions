import type {Driver,PitLoss,PitRejoin} from './types'
import {lapDelta,type Projected} from './projection'
const code=(number:string|null,drivers:Driver[])=>{const d=drivers.find(x=>x.number===number);return d?.code||d?.name||number}
const UNDER:Record<string,string>={sc:' under SC',vsc:' under VSC'}
const change=(lost:number|null)=>!lost?'':lost>0?` ▼${lost}`:` ▲${-lost}`
export const rejoinCell=(d:Driver)=>d.in_pit?'IN PIT':d.pit_rejoin?`P${d.pit_rejoin.position}${change(d.pit_rejoin.positions_lost)}`:'—'
function neighbours(r:PitRejoin,drivers:Driver[]){
 const parts:string[]=[]
 if(r.ahead!==null&&r.gap_ahead!==null)parts.push(`${r.gap_ahead.toFixed(1)} s behind ${code(r.ahead,drivers)}`)
 if(r.behind!==null&&r.gap_behind!==null)parts.push(`${r.gap_behind.toFixed(1)} s ahead of ${code(r.behind,drivers)}`)
 return parts
}
export const rejoinTitle=(d:Driver,drivers:Driver[])=>d.pit_rejoin?[`Rejoins P${d.pit_rejoin.position}`,...neighbours(d.pit_rejoin,drivers)].join(', '):undefined
export function rejoinSummary(d:Driver,drivers:Driver[]){
 if(d.in_pit)return 'In the pit lane now'
 if(!d.pit_rejoin)return 'If pitted now: no projection'
 const near=neighbours(d.pit_rejoin,drivers)
 return `If pitted now: ${rejoinCell(d)}${near.length?' · '+near.join(', '):''}`
}
export function lapSeconds(text?:string){
 const match=/^(?:(\d+):)?(\d+(?:\.\d+)?)$/.exec(String(text??'').trim())
 return match?Number(match[1]??0)*60+Number(match[2]):null
}
// Sign of travel along the outline from the car's recent projected samples (0 if unknown).
export const travelDirection=(samples:Projected[],length:number)=>Math.sign(samples.slice(1).reduce((sum,s,i)=>sum+lapDelta(samples[i].distance,s.distance,length),0))
// Approximate on-track rejoin point: the car moved back by the pit loss at its current lap pace.
export function ghostDistance(distance:number,direction:number,loss:number|null|undefined,lap:number|null,length:number){
 if(!direction||loss==null||!lap||lap<=0)return null
 return distance-direction*loss*length/lap
}
export function pitLossNote(loss:PitLoss|undefined,trackStatus?:string){
 if(!loss)return 'Pit loss unavailable'
 if(loss.reason||loss.seconds===null)return loss.reason||'Pit loss unavailable'
 const races=loss.races??0
 const basis=loss.basis==='circuit'?`${loss.label||'Circuit'} median (${races} race${races===1?'':'s'})`:`${loss.basis} (new circuit)`
 const assumed=(loss.condition??'green')==='green'&&['4','6','7'].includes(String(trackStatus))
 return `Pit loss ${loss.seconds.toFixed(1)} s${UNDER[loss.condition??'']??''} · ${basis}${assumed?' · no SC/VSC history, assumes green-flag pit loss':''}`
}
