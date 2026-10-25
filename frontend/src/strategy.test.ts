import {expect,it} from 'vitest'
import {neutralised,strategyCell,strategyClass,strategyHeadline,strategyRows,strategyTitle,tyreLifeNote} from './strategy'
import type {Driver,StrategyCall,StrategySummary} from './types'
const call=(c:StrategyCall['call'],label:string,extra:Partial<StrategyCall>={}):StrategyCall=>({call:c,label,reason:'Medium 18/22 laps',window:null,stops:1,compound:'MEDIUM',age:18,life:22,stack:null,...extra})
const driver=(number:string,code:string,strategy?:StrategyCall|null):Driver=>({number,code,name:code,team:'',color:'',strategy})
const drivers=[driver('1','VER',call('stay_out','L27–34')),driver('4','NOR',call('box','BOX',{stack:'81'})),driver('81','PIA',call('box','BOX')),driver('44','HAM',call('no_stop','TO END')),driver('16','LEC',null)]
const lives={SOFT:{laps:15,basis:'default' as const,stints:0},MEDIUM:{laps:18,basis:'race' as const,stints:4},HARD:{laps:30,basis:'default' as const,stints:1},INTERMEDIATE:{laps:25,basis:'default' as const,stints:0}}
const sc:StrategySummary={condition:'sc',saving:10,loss:12,green_loss:22,boxes:['81','4'],lives,reason:null}
it('formats the timing-tower cell',()=>{
 expect(strategyCell(drivers[0])).toBe('L27–34');expect(strategyCell(drivers[4])).toBe('—')
 expect(strategyClass(drivers[1])).toBe('call box');expect(strategyClass(drivers[4])).toBe('call none')
 expect(strategyTitle(drivers[1],drivers)).toBe('Medium 18/22 laps · Double stack: queues behind PIA')
 expect(strategyTitle(drivers[0],drivers)).toBe('Medium 18/22 laps');expect(strategyTitle(drivers[4],drivers)).toBeUndefined()
})
it('headlines the track condition and who should box',()=>{
 expect(neutralised(sc)).toBe(true);expect(neutralised({...sc,condition:'green'})).toBe(false)
 expect(strategyHeadline(sc,drivers)).toBe('Safety car · stops cost 12.0 s, 10.0 s less than under green · Box: PIA, NOR')
 expect(strategyHeadline({...sc,condition:'vsc',boxes:[]},drivers)).toBe('Virtual safety car · stops cost 12.0 s, 10.0 s less than under green · Nobody should box')
 expect(strategyHeadline({...sc,saving:null,reason:'No Safety car pit-loss history; calls assume the green-flag loss.'},drivers)).toBe('Safety car · No Safety car pit-loss history; calls assume the green-flag loss. · Box: PIA, NOR')
 expect(strategyHeadline({...sc,condition:'green',saving:null,loss:22,boxes:[]},drivers)).toBe('Green flag · stops cost 22.0 s')
 expect(strategyHeadline({...sc,condition:'red',reason:'Red flag: free tyre change.'},drivers)).toBe('Red flag · Red flag: free tyre change.')
 expect(strategyHeadline({condition:null,boxes:[],lives:{},reason:'Pit strategy is shown only in races.'},[])).toBe('Pit strategy is shown only in races.')
 expect(strategyHeadline(undefined,[])).toBe('Pit strategy unavailable')
})
it('notes where tyre life comes from',()=>{
 expect(tyreLifeNote(sc)).toBe('Expected tyre life (laps): Soft 15 · Medium 18* · Hard 30 · * from stints completed in this race')
 expect(tyreLifeNote({...sc,lives:{SOFT:lives.SOFT}})).toBe('Expected tyre life (laps): Soft 15 · defaults until 3 stints per compound finish')
 expect(tyreLifeNote(undefined)).toBe('')
})
it('lists box calls first',()=>{
 expect(strategyRows(drivers).map(d=>d.code)).toEqual(['NOR','PIA','VER','HAM'])
})
