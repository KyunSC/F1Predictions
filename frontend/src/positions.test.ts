import {describe,it,expect} from 'vitest'
import {marker,presentationClock,transform,type Sample,type Stream} from './positions'
const sample=(t:number,x=t):Sample=>({x,y:0,z:0,source_timestamp:t,presentation_timestamp:t,status:'OnTrack'})
describe('actual coordinates',()=>{
 it('rotates and flips both axes consistently',()=>{const [x,y]=transform(1,0,90);expect(x).toBeCloseTo(0);expect(y).toBeCloseTo(-1)})
 it('interpolates without extrapolation or filling long gaps',()=>{expect(marker([sample(1),sample(2)],1.5)?.x).toBe(1.5);expect(marker([sample(1)],2)?.x).toBe(1);expect(marker([sample(1),sample(5)],3)?.x).toBe(1);expect(marker([sample(2)],1)).toBeNull()})
 it('holds under reduced motion and hides stale cars',()=>{expect(marker([sample(1),sample(2)],1.5,true)?.x).toBe(1);expect(marker([sample(1)],7)?.stale).toBe(true);expect(marker([sample(1)],17)).toBeNull()})
 it('uses replay speed and freezes paused, ended and disconnected clocks',()=>{const s={presentation_clock:10,connection:'replay',replay:{speed:5,paused:false,ended:false}} as Stream;expect(presentationClock(s,.2,true)).toBe(11);expect(presentationClock(s,2,false)).toBe(10);s.replay!.paused=true;expect(presentationClock(s,.2,true)).toBe(10);s.replay!.paused=false;s.replay!.ended=true;expect(presentationClock(s,.2,true)).toBe(10)})
})

import {aligned} from './positions'
it('rejects obvious frame mismatch while preserving off-track measurements',()=>{
 expect(aligned([[0,0],[10,10]],{'1':[sample(1,1000)]})).toBe(false)
 expect(aligned([[0,0],[10,10]],{'1':[{...sample(1,1000),status:'OffTrack'}]})).toBe(true)
})
