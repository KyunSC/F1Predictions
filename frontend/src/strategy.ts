import type {Driver,StrategySummary} from './types'
const code=(number:string|null,drivers:Driver[])=>{const d=drivers.find(x=>x.number===number);return d?.code||d?.name||number}
const NAMES:Record<string,string>={green:'Green flag',sc:'Safety car',vsc:'Virtual safety car',red:'Red flag'}
const COMPOUNDS=['SOFT','MEDIUM','HARD','INTERMEDIATE','WET']
export const strategyCell=(d:Driver)=>d.strategy?.label??'—'
export const strategyClass=(d:Driver)=>`call ${d.strategy?.call??'none'}`
export function strategyTitle(d:Driver,drivers:Driver[]){
 const s=d.strategy;if(!s)return undefined
 return s.reason+(s.stack?` · Double stack: queues behind ${code(s.stack,drivers)}`:'')
}
export const neutralised=(summary?:StrategySummary)=>summary?.condition==='sc'||summary?.condition==='vsc'
export function strategyHeadline(summary:StrategySummary|undefined,drivers:Driver[]){
 if(!summary?.condition)return summary?.reason||'Pit strategy unavailable'
 const name=NAMES[summary.condition]
 if(!neutralised(summary))return summary.reason?`${name} · ${summary.reason}`:`${name} · stops cost ${summary.loss?.toFixed(1)??'—'} s`
 const cost=summary.saving!=null&&summary.saving>0?`stops cost ${summary.loss?.toFixed(1)} s, ${summary.saving.toFixed(1)} s less than under green`:summary.reason||'no cheaper stop'
 const names=(numbers?:string[])=>(numbers||[]).map(n=>code(n,drivers)).join(', ')
 const boxes=names(summary.boxes),maybes=names(summary.maybes)
 return `${name} · ${cost} · ${boxes?`Box: ${boxes}`:maybes?`Could box: ${maybes}`:'Nobody should box'}`
}
export function tyreLifeNote(summary?:StrategySummary){
 const lives=summary?.lives||{};const dry=COMPOUNDS.filter(c=>lives[c]&&!['INTERMEDIATE','WET'].includes(c))
 if(!dry.length)return ''
 const parts=dry.map(c=>`${c[0]}${c.slice(1).toLowerCase()} ${lives[c].laps}${lives[c].basis==='race'?'*':''}`)
 const learned=dry.some(c=>lives[c].basis==='race')
 return `Expected tyre life (laps): ${parts.join(' · ')}${learned?' · * from stints completed in this race':' · defaults until 3 stints per compound finish'}`
}
// Box calls first, then the cars to watch, then the rest in running order.
const ORDER:Record<string,number>={box:0,consider:1,window:2,in_pit:3,stay_out:4,no_stop:5}
export const strategyRows=(drivers:Driver[])=>drivers.filter(d=>d.strategy).map((d,i)=>({d,i})).sort((a,b)=>ORDER[a.d.strategy!.call]-ORDER[b.d.strategy!.call]||a.i-b.i).map(x=>x.d)
