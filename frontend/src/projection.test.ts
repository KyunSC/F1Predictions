import {expect,it} from 'vitest'
import {circuit,project,Projector,projectedMarker,lapDelta,placeLabels,labelOffsets,type Label,type LabelOffset} from './projection'
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
// Car anchors captured from the 2026 Bahrain archive replay, about one second apart.
const bahrain=[
 [1,4875,-800,3,6397,1067,5,616,-2896,6,2256,-680,10,-2935,-2712,11,247,940,12,5622,77,14,391,-3759,16,5075,-549,18,-4399,-1727,23,-4468,19,27,-4530,-1198,30,596,-3080,31,-4566,-541,41,-2911,1192,43,-4102,1365,44,5884,369,55,63,-3865,63,2979,-1101,77,-4183,818,81,3409,-1392,87,-4553,-937],
 [1,5115,-501,3,6424,1256,5,659,-2586,6,2659,-831,10,-2506,-2846,11,68,954,12,5894,380,14,496,-3614,16,5339,-244,18,-4192,-2055,23,-4541,-272,27,-4463,-1541,30,636,-2748,31,-4555,-890,41,-3417,1265,43,-4381,1470,44,6111,632,55,250,-3854,63,3198,-1288,77,-4144,690,81,3707,-1447,87,-4518,-1277],
 [1,5485,-78,3,6390,1496,5,736,-2121,6,3105,-1215,10,-1880,-3067,11,-165,972,12,6163,692,14,568,-3358,16,5707,171,18,-3773,-2390,23,-4562,-747,27,-4251,-1983,30,682,-2431,31,-4502,-1374,41,-3959,1347,43,-4701,1483,44,6342,934,55,434,-3709,63,3536,-1424,77,-4160,507,81,4102,-1400,87,-4399,-1726],
 [1,5773,244,3,6312,1695,5,843,-1697,6,3498,-1416,10,-1340,-3277,11,-372,989,12,6337,925,14,597,-3065,16,6001,503,18,-3178,-2631,23,-4527,-1218,27,-3921,-2297,30,747,-2063,31,-4370,-1792,41,-4312,1440,43,-4921,1433,44,6422,1199,55,533,-3520,63,3860,-1444,77,-4259,339,81,4425,-1244,87,-4173,-2076],
 [1,6069,582,3,6128,1934,5,1029,-1278,6,4000,-1426,10,-869,-3479,11,-606,1006,12,6424,1221,14,648,-2665,16,6274,832,18,-2580,-2822,23,-4372,-1789,27,-3359,-2569,30,873,-1606,31,-4060,-2184,41,-4659,1486,43,-5074,1285,44,6391,1493,55,583,-3223,63,4226,-1354,77,-4417,126,81,4754,-943,87,-3781,-2385]]
it('does not flicker labels back and forth as real cars move between renders',()=>{
 // Labels used to be re-placed from scratch every frame, so a pack moving a few
 // pixels made labels hop between two slots and back (A, B, A), read as flicker.
 const bounds={left:-11278,right:12577,top:-4794,bottom:6432},width=2231,height=589,r=105
 const run=(memory:boolean)=>{
  let previous=new Map<string,LabelOffset>(),last=new Map<string,Label>(),flips=0
  const history=new Map<string,string[]>()
  for(let k=0;k<bahrain.length-1;k++)for(let s=0;s<60;s++){
   const anchors:Label[]=[]
   for(let i=0;i<bahrain[k].length;i+=3){const a=bahrain[k],b=bahrain[k+1],f=s/60;anchors.push({number:String(a[i]),x:a[i+1]+(b[i+1]-a[i+1])*f,y:a[i+2]+(b[i+2]-a[i+2])*f,width,height})}
   const placed=placeLabels(anchors,bounds,anchors.map(a=>({number:'',x:a.x-r*1.8,y:a.y-r*1.8,width:r*3.6,height:r*3.6})),memory?previous:undefined)
   previous=labelOffsets(anchors,placed)
   for(const p of placed){
    const q=last.get(p.number);last.set(p.number,p)
    if(!q||Math.hypot(p.x-q.x,p.y-q.y)<=height*.8)continue
    const o=previous.get(p.number)!,slot=`${Math.round(o.dx)},${Math.round(o.dy)}`,h=history.get(p.number)||[]
    if(h.at(-2)===slot)flips++
    history.set(p.number,[...h,slot].slice(-2))
   }
   for(const a of placed)for(const b of placed)if(a!==b&&a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y)overlaps++
  }
  return flips
 }
 let overlaps=0
 expect(run(false)).toBeGreaterThan(0)
 expect(run(true)).toBe(0)
 expect(overlaps).toBe(0)
})
