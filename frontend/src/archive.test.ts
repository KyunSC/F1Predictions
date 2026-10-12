import {expect,it} from 'vitest'
import {defaultSelection,eventOption,initialYear,latestSession,sessionOption} from './archive'
import {catalog} from './archiveFixture'
it('preselects the replay on screen by session key, even when meeting names repeat',()=>{
 expect(defaultSelection(catalog,{Key:20,StartDate:'2026-02-18T10:00:00',Meeting:{Name:'Pre-Season Testing'}})).toEqual({event:2,session:20})
})
it('falls back to the meeting by name, then the newest archived session',()=>{
 expect(defaultSelection(catalog,{Key:999,StartDate:'2026-10-10T17:00:00',Meeting:{Name:'Singapore Grand Prix'}})).toEqual({event:3,session:30})
 expect(defaultSelection(catalog,{Key:999,StartDate:'2025-10-10T17:00:00',Meeting:{Name:'Singapore Grand Prix'}})).toEqual({event:3,session:30})
 expect(defaultSelection(catalog,{})).toEqual({event:3,session:30})
 expect(defaultSelection({...catalog,events:[{...catalog.events[2],sessions:[catalog.events[2].sessions[1]]}]})).toEqual({event:3,session:null})
})
it('labels sessions and reads the replay year',()=>{
 expect(catalog.events[2].sessions.map(sessionOption)).toEqual(['Sprint · downloaded','Race · Not archived yet'])
 expect(latestSession(catalog.events[2])).toBe(30)
 expect(catalog.events.map(e=>eventOption(e,catalog.events))).toEqual(['Pre-Season Testing · 2026-02-11','Pre-Season Testing · 2026-02-18','Singapore Grand Prix'])
 expect(initialYear({StartDate:'2025-05-25T15:00:00'},catalog.years)).toBe(2025)
 expect(initialYear({StartDate:'2017-05-25T15:00:00'},catalog.years)).toBeNull()
 expect(initialYear(undefined,catalog.years)).toBeNull()
})
