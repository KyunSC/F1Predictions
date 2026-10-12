import type {Standing} from './types'
// Points are whole numbers except after half-points races.
export const formatPoints=(n:number)=>Number.isInteger(n)?String(n):n.toFixed(1)
export const pointsGained=(s:Standing)=>s.points_gained>0?`+${formatPoints(s.points_gained)}`:''
export const movement=(s:Standing)=>!s.positions_gained?'':s.positions_gained>0?`▲${s.positions_gained}`:`▼${-s.positions_gained}`
export const standingLabel=(s:Standing)=>s.code||s.name||`#${s.number}`
export const standingDetail=(s:Standing)=>`${s.current_position==null?'Unranked':`P${s.current_position}`} before · ${formatPoints(s.current_points)} pts`
