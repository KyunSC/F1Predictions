// @vitest-environment jsdom
import React from 'react'
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {App} from './App'
class Socket{
 static sockets:Socket[]=[]
 onmessage:((e:{data:string})=>void)|null=null
 onopen:(()=>void)|null=null
 onclose:(()=>void)|null=null
 onerror:(()=>void)|null=null
 constructor(public url:string){Socket.sockets.push(this)}
 close(){}
 emit(data:unknown){this.onmessage?.({data:JSON.stringify(data)})}
}
const replay={label:'Demo replay',paused:true,ended:false,speed:1,position:2,duration:120}
const stream={session_identity:'demo',generation:1,sequence:1,presentation_clock:2,available:true,synthetic:true,connection:'replay',replay,samples:{'44':[{x:1,y:1,z:0,source_timestamp:1,presentation_timestamp:1,status:'OnTrack'}]}}
beforeEach(()=>{
 Socket.sockets=[];vi.stubGlobal('WebSocket',Socket);vi.stubGlobal('React',React)
 vi.stubGlobal('requestAnimationFrame',()=>1);vi.stubGlobal('cancelAnimationFrame',()=>{})
 vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()}))
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({session_identity:'demo',available:true,outline:[[0,0],[2,1],[0,2]],rotation:0,synthetic:true,attribution:'Synthetic demo'})}))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear()})
it('links keyboard marker selection and tower selection, keeping it across restart and reload',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 const snapshot={session_identity:'demo',generation:1,presentation_timestamp:0,session:{},drivers:[{number:'44',name:'Lewis Hamilton',code:'HAM',color:'ff0000'}],predictions:[],messages:[],track:{},weather:{},laps:{},connection:{},replay}
 act(()=>positions.emit({...stream,current:snapshot,timing_history:[snapshot]}))
 const marker=await screen.findByRole('button',{name:'Select Lewis Hamilton'})
 fireEvent.keyDown(marker,{key:'Enter'})
 expect(screen.getByRole('button',{name:'HAM'}).getAttribute('aria-pressed')).toBe('true')
 expect(marker.getAttribute('aria-pressed')).toBe('true')
 act(()=>positions.emit({...stream,session_identity:'restart',generation:2,current:snapshot,timing_history:[{...snapshot,session_identity:'restart',generation:2}]}))
 await waitFor(()=>expect(screen.getByRole('button',{name:'HAM'}).getAttribute('aria-pressed')).toBe('true'))
 expect(screen.getByText(/Lewis Hamilton · P/)).toBeTruthy()
 cleanup();render(<App/>);const reloaded=Socket.sockets.filter(s=>s.url.endsWith('/ws/positions')).at(-1)!
 act(()=>reloaded.emit({...stream,current:snapshot,timing_history:[snapshot]}))
 await waitFor(()=>expect(screen.getByRole('button',{name:'HAM'}).getAttribute('aria-pressed')).toBe('true'))
 // A stored car that is not in this session is not shown as selected.
 cleanup();localStorage.setItem('pitwall.selected','99');render(<App/>)
 act(()=>Socket.sockets.filter(s=>s.url.endsWith('/ws/positions')).at(-1)!.emit({...stream,current:snapshot,timing_history:[snapshot]}))
 await waitFor(()=>expect(screen.getByRole('button',{name:'HAM'}).getAttribute('aria-pressed')).toBe('false'))
 expect(screen.getByText('Select a car or a driver in the timing tower.')).toBeTruthy()
})
it('drives the replay from the keyboard and the seek bar',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 const snapshot={session_identity:'demo',generation:1,presentation_timestamp:0,session:{},drivers:[],predictions:[],messages:[],track:{},weather:{},laps:{},connection:{},replay}
 act(()=>positions.emit({...stream,current:snapshot,timing_history:[snapshot]}));await screen.findByRole('button',{name:'Select 44'})
 const fetch=globalThis.fetch as ReturnType<typeof vi.fn>
 const posted=()=>fetch.mock.calls.filter(([url])=>url==='/api/replay/control').map(([,init])=>JSON.parse(init.body))
 await act(async()=>{fireEvent.keyDown(document.body,{key:' '})});expect(posted().at(-1)).toEqual({action:'resume'})
 await act(async()=>{fireEvent.keyDown(document.body,{key:'5'})});expect(posted().at(-1)).toEqual({action:'speed',speed:5})
 const count=posted().length
 await act(async()=>{fireEvent.keyDown(document.body,{key:'r',metaKey:true})})
 await act(async()=>{fireEvent.keyDown(screen.getByRole('button',{name:'Select 44'}),{key:' '})})
 expect(posted().length).toBe(count)
 const bar=screen.getByRole('slider',{name:'Seek replay'})
 fireEvent.change(bar,{target:{value:'60'}});await act(async()=>{fireEvent.pointerUp(bar)})
 expect(posted().at(-1)).toEqual({action:'seek',position:60})
})
it('exposes disconnect and recovers from a new socket without losing the map',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 act(()=>positions.emit(stream));await screen.findByRole('button',{name:'Select 44'})
 act(()=>positions.onclose?.());expect(screen.getByText('Disconnected · frozen')).toBeTruthy()
 act(()=>positions.emit(stream));expect(screen.getByText(/Replay · synthetic demo · paused/)).toBeTruthy()
 expect(screen.getByText(/reduced motion/)).toBeTruthy()
})
it('keeps overlapping markers separately keyboard-selectable',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 act(()=>positions.emit({...stream,samples:{...stream.samples,'1':stream.samples['44']}}))
 const first=await screen.findByRole('button',{name:'Select 1'}),second=screen.getByRole('button',{name:'Select 44'})
 fireEvent.keyDown(first,{key:' '});expect(first.getAttribute('aria-pressed')).toBe('true')
 fireEvent.keyDown(second,{key:'Enter'});expect(second.getAttribute('aria-pressed')).toBe('true');expect(first.getAttribute('aria-pressed')).toBe('false')
})
it('renders measured locations independently of official overtake and lapped standings',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 const snapshot={session_identity:'demo',generation:1,presentation_timestamp:0,session:{},drivers:[{number:'44',name:'Lewis Hamilton',code:'HAM',position:'2',gap:'+1 LAP'}],predictions:[],messages:[],track:{},weather:{},laps:{},connection:{},replay}
 act(()=>positions.emit({...stream,current:snapshot,timing_history:[snapshot]}))
 const car=await screen.findByRole('button',{name:'Select Lewis Hamilton'})
 const location=car.getAttribute('transform')
 fireEvent.click(car);expect(screen.getByText(/Lewis Hamilton · P2/)).toBeTruthy()
 const changed={...snapshot,presentation_timestamp:1.5,drivers:[{...snapshot.drivers[0],position:'1',gap:'LAP 2'}]}
 act(()=>positions.emit({...stream,current:changed,timing_history:[snapshot,changed]}))
 expect(screen.getByText(/Lewis Hamilton · P2/)).toBeTruthy()
 act(()=>positions.emit({...stream,presentation_clock:3,current:changed,timing_history:[snapshot,changed]}))
 expect(car.getAttribute('transform')).toBe(location)
 expect(screen.getByText(/Lewis Hamilton · P1/)).toBeTruthy()
})
it('shows the if-pitted-now rejoin and pit-loss basis in the timing tower',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 const drivers=[{number:'4',code:'NOR',position:'1',gap:'LAP 20'},{number:'44',name:'Lewis Hamilton',code:'HAM',position:'2',gap:'+3.000',pit_rejoin:{position:7,ahead:'4',gap_ahead:1.2,behind:null,gap_behind:null,positions_lost:5}},{number:'16',code:'LEC',position:'3',in_pit:true,pit_rejoin:null}]
 const snapshot={session_identity:'demo',generation:1,presentation_timestamp:0,session:{},drivers,predictions:[],messages:[],track:{},weather:{},laps:{},connection:{},replay,pit_loss:{seconds:27.4,basis:'circuit',races:3,label:'Marina Bay'}}
 act(()=>positions.emit({...stream,current:snapshot,timing_history:[snapshot]}))
 const cell=await screen.findByText('P7 ▼5')
 expect(cell.closest('tr')?.getAttribute('data-driver-number')).toBe('44')
 expect(cell.getAttribute('title')).toBe('Rejoins P7, 1.2 s behind NOR')
 expect(screen.getByText('IN PIT').closest('tr')?.getAttribute('data-driver-number')).toBe('16')
 expect(screen.getByText('Pit loss 27.4 s · Marina Bay median (3 races)')).toBeTruthy()
})
it('shows where a clicked driver would rejoin if they pitted now',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 const moving={...stream,samples:{'44':[{x:0,y:0,z:0,source_timestamp:0,presentation_timestamp:0,status:'OnTrack'},{x:1,y:.5,z:0,source_timestamp:1,presentation_timestamp:1,status:'OnTrack'}],'4':[{x:0,y:2,z:0,source_timestamp:1,presentation_timestamp:1,status:'OnTrack'}]}}
 const drivers=[{number:'4',code:'NOR',name:'Lando Norris',position:'1',gap:'LAP 20'},{number:'44',name:'Lewis Hamilton',code:'HAM',position:'2',gap:'+3.000',last_lap:'1:30.000',pit_rejoin:{position:3,ahead:'4',gap_ahead:19,behind:null,gap_behind:null,positions_lost:1}}]
 const snapshot={session_identity:'demo',generation:1,presentation_timestamp:0,session:{},drivers,predictions:[],messages:[],track:{},weather:{},laps:{},connection:{},replay,pit_loss:{seconds:22,basis:'circuit',races:3,label:'Marina Bay'}}
 act(()=>positions.emit({...moving,current:snapshot,timing_history:[snapshot]}))
 await screen.findByRole('button',{name:'Select Lewis Hamilton'})
 expect(screen.queryByText(/If pitted now/)).toBeNull()
 fireEvent.click(screen.getByRole('button',{name:'HAM'}))
 expect(screen.getByText(/If pitted now: P3 ▼1 · 19.0 s behind NOR/)).toBeTruthy()
 expect(screen.getByRole('img',{name:'HAM rejoin point if pitted now'})).toBeTruthy()
 expect(document.querySelector('tr[data-driver-number="4"]')?.className).toBe('rejoin-neighbour')
 fireEvent.click(screen.getByRole('button',{name:'NOR'}))
 expect(screen.queryByRole('img',{name:/rejoin point/})).toBeNull()
 expect(screen.getByText('If pitted now: no projection')).toBeTruthy()
})
it('switches between historical and live dashboards from the header',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 const snapshot={session_identity:'demo',generation:1,presentation_timestamp:0,session:{},drivers:[],predictions:[],messages:[],track:{},weather:{},laps:{},connection:{mode:'replay'},replay}
 act(()=>positions.emit({...stream,current:snapshot,timing_history:[snapshot]}))
 const historical=await screen.findByRole('button',{name:'Historical'}),live=screen.getByRole('button',{name:'Live'})
 expect(historical.getAttribute('aria-pressed')).toBe('true');expect((historical as HTMLButtonElement).disabled).toBe(true)
 fireEvent.click(live)
 await waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/mode',expect.objectContaining({method:'POST',body:JSON.stringify({mode:'live'})})))
})
it('retries a pending traced outline until it is ready',async()=>{
 vi.useFakeTimers({shouldAdvanceTime:true})
 const pending={session_identity:'demo',available:false,pending:true,reason:'No published outline for this circuit; tracing one once cars complete a lap',outline:[]}
 const traced={session_identity:'demo',available:true,outline:[[0,0],[2,1],[0,2]],rotation:0,synthetic:false,attribution:'Traced from 2026 car coordinates'}
 vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce({ok:true,json:async()=>pending}).mockResolvedValue({ok:true,json:async()=>traced}))
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!
 act(()=>positions.emit({...stream,synthetic:false}))
 expect(await screen.findByText(pending.reason)).toBeTruthy()
 await act(async()=>{vi.advanceTimersByTime(3000)})
 await screen.findByRole('button',{name:'Select 44'})
 expect(screen.getByText('Traced from 2026 car coordinates')).toBeTruthy()
 expect(fetch).toHaveBeenCalledTimes(2)
 vi.useRealTimers()
})
