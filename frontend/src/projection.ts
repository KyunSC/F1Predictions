import type {Sample} from './positions'
export type Point=[number,number]
type Segment={a:Point;b:Point;start:number;length:number}
export type Circuit={segments:Segment[];length:number}
export type Projected=Sample&{distance:number}
export function circuit(outline:Point[]):Circuit {
 const points=[...outline]
 if(points.length&&points[0].some((v,i)=>v!==points.at(-1)![i]))points.push(points[0])
 let length=0
 const segments:Segment[]=[]
 for(let i=1;i<points.length;i++){
  const a=points[i-1],b=points[i],size=Math.hypot(b[0]-a[0],b[1]-a[1])
  if(size){segments.push({a,b,start:length,length:size});length+=size}
 }
 return {segments,length}
}
export function lapDelta(a:number,b:number,length:number){return ((b-a+length/2)%length+length)%length-length/2}
export function atDistance(track:Circuit,distance:number):Point {
 const d=((distance%track.length)+track.length)%track.length
 const segment=track.segments.find(s=>s.start+s.length>=d)!
 const f=(d-segment.start)/segment.length
 return [segment.a[0]+(segment.b[0]-segment.a[0])*f,segment.a[1]+(segment.b[1]-segment.a[1])*f]
}
export function project(sample:Sample,track:Circuit,previous?:Projected):Projected {
 const dt=previous?sample.presentation_timestamp-previous.presentation_timestamp:Infinity
 const continuous=previous&&dt>0&&dt<=2
 let best:{score:number;distance:number;x:number;y:number}|undefined
 for(const s of track.segments){
  const dx=s.b[0]-s.a[0],dy=s.b[1]-s.a[1]
  const f=Math.max(0,Math.min(1,((sample.x-s.a[0])*dx+(sample.y-s.a[1])*dy)/(s.length*s.length)))
  const x=s.a[0]+dx*f,y=s.a[1]+dy*f,distance=s.start+s.length*f
  let score=(x-sample.x)**2+(y-sample.y)**2
  if(continuous){
   // Nearby branches may be indistinguishable spatially. Penalize implausible
   // lap travel, using measured movement, never timing order or race position.
   const movement=Math.hypot(sample.x-previous.x,sample.y-previous.y)
   const travel=Math.abs(lapDelta(previous.distance,distance,track.length))
   const allowance=Math.max(track.length*.004,movement*2)
   score+=Math.max(0,travel-allowance)**2*16
  }
  if(!best||score<best.score)best={score,distance,x,y}
 }
 return {...sample,x:best!.x,y:best!.y,distance:best!.distance}
}
// The cache retains branch continuity across sliding stream windows. A new
// instance is created for each session/generation or geometry change.
export class Projector {
 private histories=new Map<string,Map<number,Projected>>()
 constructor(public track:Circuit){}
 history(number:string,samples:Sample[]):Projected[]{
  const cached=this.histories.get(number)||new Map<number,Projected>()
  let previous:Projected|undefined
  const result=samples.map(sample=>{
   const p=cached.get(sample.source_timestamp)||project(sample,this.track,previous)
   cached.set(sample.source_timestamp,p);previous=p;return p
  })
  this.histories.set(number,new Map(result.map(p=>[p.source_timestamp,p])))
  return result
 }
}
export function projectedMarker(samples:Projected[],time:number,track:Circuit,reduced=false){
 const previous=samples.filter(s=>s.presentation_timestamp<=time).at(-1)
 if(!previous)return null
 const age=Math.max(0,time-previous.presentation_timestamp)
 if(age>15)return null
 const next=samples.find(s=>s.presentation_timestamp>time)
 let distance=previous.distance
 if(!reduced&&next&&next.presentation_timestamp-previous.presentation_timestamp<=2){
  const f=(time-previous.presentation_timestamp)/(next.presentation_timestamp-previous.presentation_timestamp)
  distance+=lapDelta(distance,next.distance,track.length)*f
 }
 const [x,y]=atDistance(track,distance)
 return {...previous,x,y,distance,age,stale:age>5}
}
export type Label={number:string;x:number;y:number;width:number;height:number}
// Offset of a placed label from its anchor, in label heights so it survives resizes.
export type LabelOffset={dx:number;dy:number}
export function labelOffsets(anchors:Label[],placed:Label[]){
 return new Map(placed.map(p=>{const a=anchors.find(a=>a.number===p.number)!;return [p.number,{dx:(p.x-a.x)/a.height,dy:(p.y-a.y)/a.height}] as const}))
}
export function placeLabels(labels:Label[],bounds:{left:number;right:number;top:number;bottom:number},obstacles:Label[]=[],previous?:Map<string,LabelOffset>){
 const placed:Label[]=[...obstacles]
 const sorted=[...labels].sort((a,b)=>Number(a.number)-Number(b.number))
 const clamp=(label:Label,x:number,y:number)=>({...label,x:Math.max(bounds.left,Math.min(bounds.right-label.width,x)),y:Math.max(bounds.top,Math.min(bounds.bottom-label.height,y))})
 const result=sorted.map(label=>{
  let best={...label},bestScore=Infinity
  const step=label.height*1.2
  // Labels are re-placed every frame as cars move. Without hysteresis a tiny
  // move flips a label to another row or side, which reads as flicker. Keep the
  // previous slot unless it now overlaps or a much closer one has opened up,
  // and when it must move, prefer slots near where it was.
  const collisions=(candidate:Label)=>placed.filter(p=>candidate.x<p.x+p.width+step*.15&&candidate.x+candidate.width+step*.15>p.x&&candidate.y<p.y+p.height+step*.15&&candidate.y+candidate.height+step*.15>p.y).length
  const last=previous?.get(label.number),slot=last&&clamp(label,label.x+last.dx*label.height,label.y+last.dy*label.height)
  const blocked=slot&&collisions(slot)?slot:undefined
  const consider=(candidate:Label,bonus=0)=>{
   const score=collisions(candidate)*1e12+Math.hypot(candidate.x-label.x,candidate.y-label.y)+(blocked?Math.hypot(candidate.x-blocked.x,candidate.y-blocked.y):0)-bonus
   if(score<bestScore){best=candidate;bestScore=score}
  }
  if(slot&&!blocked)consider(slot,step*2)
  if(blocked)for(let k=1;k<=8;k++)for(const sign of [1,-1])consider(clamp(label,blocked.x,blocked.y+sign*k*step*.25))
  for(let row=0;row<60;row++)for(const side of [1,-1,2,-2,3,-3]){
   const dy=(row===0?0:Math.ceil(row/2)*(row%2?1:-1))*step
   consider(clamp(label,label.x+Math.sign(side)*label.height+(side>0?side-1:side)*label.width,label.y+dy))
  }
  placed.push(best);return best
 })
 const overlaps=(a:Label,b:Label)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y
 if(!result.some((a,i)=>result.slice(i+1).some(b=>overlaps(a,b))))return result
 // Very dense packs need the whole available SVG area. Use non-overlapping
 // cells as a deterministic fallback rather than silently hiding a driver.
 if(!labels.length)return []
 const w=labels[0].width,h=labels[0].height,gap=h*.2,cells:Label[]=[]
 for(let y=bounds.top;y+h<=bounds.bottom;y+=h+gap)
  for(let x=bounds.left;x+w<=bounds.right;x+=w+gap){
   const cell={number:'',x,y,width:w,height:h}
   if(!obstacles.some(o=>overlaps(cell,o)))cells.push(cell)
  }
 if(cells.length<sorted.length)return result
 return sorted.map(label=>{
  cells.sort((a,b)=>Math.hypot(a.x-label.x,a.y-label.y)-Math.hypot(b.x-label.x,b.y-label.y))
  return {...cells.shift()!,number:label.number}
 })
}
