import {expect,it} from 'vitest'
import {formatPoints,movement,pointsGained,standingDetail,standingLabel} from './standings'
import type {Standing} from './types'
const row=(extra:Partial<Standing>={}):Standing=>({number:'63',code:'RUS',position:3,points:244,current_position:2,current_points:236,points_gained:8,positions_gained:-1,...extra})
it('formats projected points and movement',()=>{
 expect(formatPoints(302)).toBe('302');expect(formatPoints(12.5)).toBe('12.5')
 expect(pointsGained(row())).toBe('+8');expect(pointsGained(row({points_gained:0}))).toBe('')
 expect(movement(row())).toBe('▼1');expect(movement(row({positions_gained:2}))).toBe('▲2')
 expect(movement(row({positions_gained:0}))).toBe('');expect(movement(row({positions_gained:null}))).toBe('')
})
it('labels drivers missing from this session by number',()=>{
 expect(standingLabel(row())).toBe('RUS');expect(standingLabel(row({code:null,name:null,number:'7'}))).toBe('#7')
 expect(standingDetail(row())).toBe('P2 before · 236 pts')
 expect(standingDetail(row({current_position:null,current_points:0}))).toBe('Unranked before · 0 pts')
})
