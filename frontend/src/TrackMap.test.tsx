// @vitest-environment jsdom
import React from 'react'
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {App} from './main'
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
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('links keyboard marker selection and tower selection, clearing on restart',async()=>{
 render(<App/>);const positions=Socket.sockets.find(s=>s.url.endsWith('/ws/positions'))!,timing=Socket.sockets.find(s=>s.url.endsWith('/ws'))!
 act(()=>{timing.onopen?.();timing.emit({session:{},drivers:[{number:'44',name:'Lewis Hamilton',code:'HAM',color:'ff0000'}],predictions:[],messages:[],track:{},weather:{},laps:{},connection:{},replay});positions.emit(stream)})
 const marker=await screen.findByRole('button',{name:'Select Lewis Hamilton'})
 fireEvent.keyDown(marker,{key:'Enter'})
 expect(screen.getByRole('button',{name:'HAM'}).getAttribute('aria-pressed')).toBe('true')
 expect(marker.getAttribute('aria-pressed')).toBe('true')
 act(()=>positions.emit({...stream,session_identity:'restart',generation:2}))
 await waitFor(()=>expect(screen.getByRole('button',{name:'HAM'}).getAttribute('aria-pressed')).toBe('false'))
 fireEvent.click(screen.getByRole('button',{name:'HAM'}))
 expect(screen.getByText(/Lewis Hamilton · P/)).toBeTruthy()
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
