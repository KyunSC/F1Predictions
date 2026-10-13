// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest'
import {isInteractive,replayKey,store,stored} from './controls'
const replay={label:'Recorded replay',paused:false,speed:1,position:10,duration:100,ended:false}
afterEach(()=>{vi.restoreAllMocks();localStorage.clear()})
it('maps keys to replay commands',()=>{
 expect(replayKey(' ',replay)).toEqual({action:'pause'})
 expect(replayKey(' ',{...replay,paused:true})).toEqual({action:'resume'})
 expect(replayKey(' ',{...replay,ended:true})).toBeNull()
 expect(replayKey('r',replay)).toEqual({action:'restart'})
 expect(replayKey('R',replay)).toEqual({action:'restart'})
 expect(replayKey('5',replay)).toEqual({action:'speed',speed:5})
 expect(replayKey('1',replay)).toBeNull()
 expect(replayKey('3',replay)).toBeNull()
 expect(replayKey('x',replay)).toBeNull()
})
it('leaves keys typed into controls alone',()=>{
 document.body.innerHTML='<button id="b">Go</button><select id="s"></select><svg><g id="car" role="button"></g></svg><div id="d"><span id="t"></span></div><input id="range" type="range"><input id="text">'
 for(const id of ['b','s','car','text'])expect(isInteractive(document.getElementById(id))).toBe(true)
 expect(isInteractive(document.getElementById('t'))).toBe(false)
 expect(isInteractive(document.getElementById('range'))).toBe(false)
 expect(isInteractive(window)).toBe(false)
 expect(isInteractive(null)).toBe(false)
})
it('stores per-viewer settings and survives blocked storage',()=>{
 store('pitwall.selected','63');expect(stored('pitwall.selected')).toBe('63')
 store('pitwall.selected',null);expect(stored('pitwall.selected')).toBeNull()
 vi.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw Error('blocked')})
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw Error('blocked')})
 expect(()=>store('pitwall.selected','1')).not.toThrow()
 expect(stored('pitwall.selected')).toBeNull()
})
