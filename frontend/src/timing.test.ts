import {expect,it} from 'vitest'
import {fastestLap,paceDelta,predictionScore,tabTitle} from './timing'
import type {Driver,Prediction,Snapshot} from './types'
const driver=(number:string,code:string,extra:Partial<Driver>={}):Driver=>({number,code,name:code,team:'',color:'',...extra})
const prediction=(racing_number:string,pace_rank:number):Prediction=>({racing_number,driver:racing_number,name:racing_number,pace_rank,predicted_pace_ratio:1,missing_features:{}})
it('finds the overall fastest best lap',()=>{
 expect(fastestLap([driver('1','VER',{best_lap:'1:36.900'}),driver('63','RUS',{best_lap:'1:36.815'}),driver('16','LEC',{best_lap:'98.1'})])).toBe('63')
 expect(fastestLap([driver('1','VER',{best_lap:'1:36.815'}),driver('63','RUS',{best_lap:'1:36.815'})])).toBe('1')
 expect(fastestLap([driver('1','VER'),driver('63','RUS',{best_lap:''})])).toBeNull()
})
it('compares running position with pace rank',()=>{
 expect(paceDelta(prediction('1',5),driver('1','VER',{position:'3'}))).toEqual({label:'P3 ▲2',change:2,title:'Running P3, 2 places ahead of pace rank 5'})
 expect(paceDelta(prediction('1',2),driver('1','VER',{position:'3'}))?.label).toBe('P3 ▼1')
 expect(paceDelta(prediction('1',3),driver('1','VER',{position:'3'}))?.title).toBe('Running P3, level with pace rank 3')
 expect(paceDelta(prediction('1',3),driver('1','VER',{retired:true,position:'20'}))?.label).toBe('OUT')
 expect(paceDelta(prediction('1',3),driver('1','VER'))).toBeNull()
 expect(paceDelta(prediction('1',3))).toBeNull()
})
it('scores the pace ranking against the final classification',()=>{
 const drivers=[driver('1','VER',{position:'2'}),driver('63','RUS',{position:'1'}),driver('16','LEC',{position:'3'}),driver('81','PIA',{position:'4'}),driver('44','HAM')]
 const predictions=[prediction('1',1),prediction('63',2),prediction('16',3),prediction('81',5),prediction('44',4),prediction('99',6)]
 // Ranks over the four classified drivers: predicted VER RUS LEC PIA, actual RUS VER LEC PIA.
 expect(predictionScore(predictions,drivers)).toEqual({spearman:1-6*2/(4*15),podium:3,winner:false,drivers:4})
 expect(predictionScore(predictions.slice(0,2),drivers)).toBeNull()
 const perfect=predictionScore([prediction('63',1),prediction('1',2),prediction('16',3)],drivers)
 expect(perfect).toEqual({spearman:1,podium:3,winner:true,drivers:3})
})
it('summarises the session in the tab title',()=>{
 const data={laps:{CurrentLap:23,TotalLaps:62},drivers:[driver('63','RUS',{position:'2'}),driver('1','VER',{position:'1'})],track:{Status:'4'},session:{Meeting:{Name:'Singapore Grand Prix'}}} as unknown as Snapshot
 expect(tabTitle(data)).toBe('L23/62 · VER leads · SC · Pitwall')
 expect(tabTitle({...data,track:{Status:'1'}})).toBe('L23/62 · VER leads · Pitwall')
 expect(tabTitle({...data,laps:{},drivers:[],track:{}})).toBe('Singapore Grand Prix · Pitwall')
 expect(tabTitle(null)).toBe('Pitwall · Local F1 timing')
})
