import {expect,it} from 'vitest'
import {circuit,project,Projector,projectedMarker,lapDelta,placeLabels} from './projection'
import type {Sample} from './positions'
const s=(t:number,x:number,y:number):Sample=>({x,y,z:0,presentation_timestamp:t,source_timestamp:t,status:'OnTrack'})
const square=circuit([[0,0],[100,0],[100,100],[0,100]])
it('projects off-track samples without mutating raw measurements',()=>{
 const raw=s(0,50,-20),p=project(raw,square)
 expect([p.x,p.y]).toEqual([50,0]);expect(raw.y).toBe(-20)
})
it('interpolates around corners rather than across their interior',()=>{
 const p=new Projector(square).history('1',[s(0,90,0),s(1,100,10)])
 const m=projectedMarker(p,.5,square)!
 expect([m.x,m.y]).toEqual([100,0])
})
it('wraps the finish line using the short arc',()=>{
 const p=new Projector(square).history('1',[s(0,0,10),s(1,10,0)])
 expect(projectedMarker(p,.5,square)?.distance).toBe(400)
 expect(lapDelta(390,10,400)).toBe(20)
})
it('uses preceding movement at a crossing and retains it across windows',()=>{
 const track=circuit([[-100,-100],[100,100],[-100,100],[100,-100]])
 const projector=new Projector(track)
 const initial=projector.history('1',[s(0,-20,-20),s(.5,-1,1)])
 expect(initial[1].distance).toBeCloseTo(Math.sqrt(20000))
 const next=projector.history('1',[s(.5,-1,1),s(1,10,10)])
 expect(lapDelta(initial[1].distance,next[1].distance,track.length)).toBeCloseTo(Math.sqrt(200))
})
it('resets branch continuity after gaps and does not interpolate across them',()=>{
 const p=new Projector(square).history('1',[s(0,0,0),s(6,100,100)])
 expect(p[1].distance).toBe(200)
 expect(projectedMarker(p,5.5,square)?.stale).toBe(true)
 expect(projectedMarker(p,5.5,square)?.distance).toBe(0)
 expect(projectedMarker(p,22,square)).toBeNull()
})
it('places twenty coincident labels without overlapping and inside bounds',()=>{
 const labels=placeLabels(Array.from({length:20},(_,i)=>({number:String(i),x:50,y:50,width:15,height:3})),{left:0,right:100,top:0,bottom:100})
 for(const a of labels){expect(a.x).toBeGreaterThanOrEqual(0);expect(a.x+a.width).toBeLessThanOrEqual(100)
 for(const b of labels.filter(b=>b!==a))expect(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y).toBe(false)}
})
it('keeps mobile-sized labels clear of a dense pack of marker obstacles',()=>{
 const labels=Array.from({length:20},(_,i)=>({number:String(i),x:150+i%3,y:150+i%5,width:64,height:17}))
 const obstacles=labels.map(l=>({...l,x:l.x-4,y:l.y-4,width:8,height:8}))
 const placed=placeLabels(labels,{left:0,right:346,top:0,bottom:380},obstacles)
 for(const a of placed)for(const b of [...placed.filter(b=>b!==a),...obstacles])expect(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y).toBe(false)
})
