// Test fixture: two same-named 2026 tests and a sprint weekend whose race is not archived yet.
import type {ArchiveCatalog} from './types'
const session=(key:number,name:string,start:string,available=true,cached=false)=>({key,name,type:null,start_utc:start,available,cached})
export const catalog:ArchiveCatalog={years:[2025,2026],year:2026,events:[
 {event:'Pre-Season Testing',key:1,location:'Sakhir',sessions:[session(10,'Day 1','2026-02-11T07:00:00+00:00')]},
 {event:'Pre-Season Testing',key:2,location:'Sakhir',sessions:[session(20,'Day 1','2026-02-18T07:00:00+00:00')]},
 {event:'Singapore Grand Prix',key:3,location:'Marina Bay',sessions:[session(30,'Sprint','2026-10-10T09:00:00+00:00',true,true),session(31,'Race','2026-10-11T12:00:00+00:00',false)]},
]}
