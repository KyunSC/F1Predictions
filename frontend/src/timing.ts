import type {Driver,Prediction,Snapshot} from './types'
import {lapSeconds} from './pitRejoin'
const running=(d?:Driver)=>{const n=Number(d?.position);return d&&Number.isInteger(n)&&n>0?n:null}
// Racing number of the overall fastest best lap; the earlier car in the list wins a tie.
export function fastestLap(drivers:Driver[]){
 let number:string|null=null,best=Infinity
 for(const d of drivers){const s=lapSeconds(d.best_lap);if(s!==null&&s<best){best=s;number=d.number}}
 return number
}
// Running position against the predicted pace rank; positive change means ahead of the prediction.
export function paceDelta(p:Prediction,d?:Driver){
 if(d?.retired)return {label:'OUT',change:0,title:'Retired'}
 const position=running(d)
 if(position===null)return null
 const change=p.pace_rank-position
 return {label:`P${position}${!change?'':change>0?` ▲${change}`:` ▼${-change}`}`,change,
  title:`Running P${position}, ${!change?'level with':`${Math.abs(change)} place${Math.abs(change)===1?'':'s'} ${change>0?'ahead of':'behind'}`} pace rank ${p.pace_rank}`}
}
// Pace rank against the final classification, both re-ranked over the drivers present in each.
export function predictionScore(predictions:Prediction[],drivers:Driver[]){
 const rows=predictions.flatMap(p=>{const position=running(drivers.find(d=>d.number===p.racing_number));return position===null?[]:[{p,position}]})
 if(rows.length<3)return null
 const predicted=[...rows].sort((a,b)=>a.p.pace_rank-b.p.pace_rank),actual=[...rows].sort((a,b)=>a.position-b.position)
 const n=rows.length,squares=predicted.reduce((sum,row,i)=>sum+(i-actual.indexOf(row))**2,0)
 const podium=predicted.slice(0,3).filter(row=>actual.slice(0,3).includes(row)).length
 return {spearman:1-6*squares/(n*(n*n-1)),podium,winner:predicted[0]===actual[0],drivers:n}
}
const TRACK:Record<string,string>={'2':'Yellow','4':'SC','5':'Red flag','6':'VSC','7':'VSC ending'}
export function tabTitle(data:Snapshot|null){
 if(!data)return 'Pitwall · Local F1 timing'
 const {CurrentLap:lap,TotalLaps:total}=data.laps,leader=data.drivers.find(d=>d.position==='1')
 const parts=[lap?`L${lap}${total?`/${total}`:''}`:'',leader?`${leader.code||leader.name||leader.number} leads`:'',TRACK[String(data.track.Status)]||''].filter(Boolean)
 return [...(parts.length?parts:[data.session.Meeting?.Name||'Local F1 timing']),'Pitwall'].join(' · ')
}
