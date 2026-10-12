import {expect,it} from 'vitest'
import {ghostDistance,lapSeconds,pitLossNote,rejoinCell,rejoinSummary,rejoinTitle,travelDirection} from './pitRejoin'
import type {Driver} from './types'
const driver=(number:string,code:string,extra:Partial<Driver>={}):Driver=>({number,code,name:code,team:'',color:'',...extra})
const rejoin={position:7,ahead:'4',gap_ahead:1.23,behind:'44',gap_behind:.8,positions_lost:3}
const drivers=[driver('4','NOR'),driver('44','HAM'),driver('1','VER',{pit_rejoin:rejoin})]
it('formats the rejoin cell',()=>{
 expect(rejoinCell(drivers[2])).toBe('P7 ▼3')
 expect(rejoinCell(driver('1','VER',{pit_rejoin:{...rejoin,positions_lost:-1}}))).toBe('P7 ▲1')
 expect(rejoinCell(driver('1','VER',{pit_rejoin:{...rejoin,positions_lost:0}}))).toBe('P7')
 expect(rejoinCell(driver('1','VER',{in_pit:true,pit_rejoin:null}))).toBe('IN PIT')
 expect(rejoinCell(driver('1','VER'))).toBe('—')
})
it('names the cars around the rejoin point',()=>{
 expect(rejoinTitle(drivers[2],drivers)).toBe('Rejoins P7, 1.2 s behind NOR, 0.8 s ahead of HAM')
 expect(rejoinTitle(driver('1','VER',{pit_rejoin:{...rejoin,position:1,ahead:null,gap_ahead:null}}),drivers)).toBe('Rejoins P1, 0.8 s ahead of HAM')
 expect(rejoinTitle(driver('1','VER'),drivers)).toBeUndefined()
})
it('summarises the selected driver',()=>{
 expect(rejoinSummary(drivers[2],drivers)).toBe('If pitted now: P7 ▼3 · 1.2 s behind NOR, 0.8 s ahead of HAM')
 expect(rejoinSummary(driver('1','VER',{in_pit:true,pit_rejoin:null}),drivers)).toBe('In the pit lane now')
 expect(rejoinSummary(driver('1','VER'),drivers)).toBe('If pitted now: no projection')
})
it('places the rejoin point behind the car at its lap pace',()=>{
 expect(lapSeconds('1:30.500')).toBe(90.5);expect(lapSeconds('58.2')).toBe(58.2);expect(lapSeconds('')).toBeNull();expect(lapSeconds(undefined)).toBeNull()
 const at=(distance:number)=>({x:0,y:0,z:0,source_timestamp:0,presentation_timestamp:0,status:'OnTrack',distance})
 expect(travelDirection([at(90),at(95),at(2)],100)).toBe(1)
 expect(travelDirection([at(2),at(98)],100)).toBe(-1)
 expect(travelDirection([at(5)],100)).toBe(0)
 // 22 s of a 90 s lap on a 900 m outline is 220 m behind, against the direction of travel.
 expect(ghostDistance(500,1,22,90,900)).toBe(280)
 expect(ghostDistance(500,-1,22,90,900)).toBe(720)
 expect(ghostDistance(500,0,22,90,900)).toBeNull()
 expect(ghostDistance(500,1,null,90,900)).toBeNull()
 expect(ghostDistance(500,1,22,null,900)).toBeNull()
})
it('describes the pit-loss basis',()=>{
 expect(pitLossNote({seconds:27.4,basis:'circuit',races:3,label:'Marina Bay'})).toBe('Pit loss 27.4 s · Marina Bay median (3 races)')
 expect(pitLossNote({seconds:23.12,basis:'all-tracks median',races:24})).toBe('Pit loss 23.1 s · all-tracks median (new circuit)')
 expect(pitLossNote({seconds:23.1,basis:'all-tracks median',races:24},'4')).toBe('Pit loss 23.1 s · all-tracks median (new circuit) · no SC/VSC history, assumes green-flag pit loss')
 expect(pitLossNote({seconds:12.04,basis:'all-tracks median',condition:'sc',races:20},'4')).toBe('Pit loss 12.0 s under SC · all-tracks median (new circuit)')
 expect(pitLossNote({seconds:15.5,basis:'circuit',condition:'vsc',races:1,label:'Monza'},'6')).toBe('Pit loss 15.5 s under VSC · Monza median (1 race)')
 expect(pitLossNote({seconds:null,basis:null,reason:'No pit-loss table loaded.'})).toBe('No pit-loss table loaded.')
 expect(pitLossNote(undefined)).toBe('Pit loss unavailable')
})
