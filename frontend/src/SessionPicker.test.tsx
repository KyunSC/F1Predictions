// @vitest-environment jsdom
import React from 'react'
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {SessionPicker} from './SessionPicker'
import {catalog} from './archiveFixture'
const json=(body:unknown,ok=true,status=200)=>({ok,status,statusText:'',json:async()=>body})
const sprint={Key:30,StartDate:'2026-10-10T17:00:00',Meeting:{Name:'Singapore Grand Prix'}}
let fetchMock:ReturnType<typeof vi.fn>
beforeEach(()=>{
 vi.stubGlobal('React',React)
 fetchMock=vi.fn(async(url:string,init?:RequestInit)=>init?.method==='POST'
  ?json({id:1,status:'importing',year:2026,key:JSON.parse(String(init.body)).key,label:'2026 Pre-Season Testing · Day 1',error:null})
  :json({...catalog,year:Number(new URL(url,'http://x').searchParams.get('year')||2026)}))
 vi.stubGlobal('fetch',fetchMock)
})
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
const select=(name:string)=>screen.getByRole('combobox',{name}) as HTMLSelectElement
it('preselects the replay, disables unarchived sessions and posts the chosen key',async()=>{
 const close=vi.fn()
 const view=render(<SessionPicker session={sprint} archive={null} disabled={false} close={close}/>)
 await waitFor(()=>expect(select('Session').value).toBe('30'))
 expect(select('Year').value).toBe('2026');expect(select('Event').value).toBe('3')
 expect(fetchMock).toHaveBeenCalledTimes(1);expect(fetchMock.mock.calls[0][0]).toBe('/api/archive')
 const race=within(select('Session')).getByRole('option',{name:'Race · Not archived yet'}) as HTMLOptionElement
 expect(race.disabled).toBe(true)
 expect(within(select('Session')).getByRole('option',{name:'Sprint · downloaded'})).toBeTruthy()
 expect(within(select('Event')).getAllByRole('option').map(o=>o.textContent)).toEqual(['Pre-Season Testing · 2026-02-11','Pre-Season Testing · 2026-02-18','Singapore Grand Prix'])
 fireEvent.change(select('Event'),{target:{value:'2'}})
 expect(select('Session').value).toBe('20')
 fireEvent.click(screen.getByRole('button',{name:'Load'}))
 await screen.findByText('Downloading 2026 Pre-Season Testing · Day 1…')
 const [url,init]=fetchMock.mock.calls[1]
 expect(url).toBe('/api/archive/load');expect(JSON.parse(init.body)).toEqual({year:2026,key:20})
 expect((screen.getByRole('button',{name:'Load'}) as HTMLButtonElement).disabled).toBe(true)
 // Done but the replay on screen has not reached the new session yet: stay open.
 const done={id:1,status:null,year:2026,key:20,label:'2026 Pre-Season Testing · Day 1',error:null}
 view.rerender(<SessionPicker session={sprint} archive={done} disabled={false} close={close}/>)
 expect(close).not.toHaveBeenCalled()
 view.rerender(<SessionPicker session={{...sprint,Key:20}} archive={done} disabled={false} close={close}/>)
 expect(close).toHaveBeenCalled()
})
it('shows an import error for this request only',async()=>{
 const failed={id:4,status:'error' as const,year:2026,key:20,label:'2026 Pre-Season Testing · Day 1',error:'Archive lacks SessionInfo'}
 const view=render(<SessionPicker session={sprint} archive={failed} disabled={false} close={vi.fn()}/>)
 await waitFor(()=>expect(select('Session').value).toBe('30'))
 expect(screen.queryByRole('alert')).toBeNull()
 fireEvent.change(select('Event'),{target:{value:'2'}});fireEvent.click(screen.getByRole('button',{name:'Load'}))
 await screen.findByText(/Downloading/)
 view.rerender(<SessionPicker session={sprint} archive={{...failed,id:1}} disabled={false} close={vi.fn()}/>)
 expect(screen.getByRole('alert').textContent).toBe('Could not load 2026 Pre-Season Testing · Day 1: Archive lacks SessionInfo')
 expect((screen.getByRole('button',{name:'Load'}) as HTMLButtonElement).disabled).toBe(false)
 fetchMock.mockResolvedValueOnce(json({detail:'Another session is already loading'},false,409))
 fireEvent.click(screen.getByRole('button',{name:'Load'}))
 await waitFor(()=>expect(screen.getByRole('alert').textContent).toBe('Another session is already loading'))
})
it("opens on the replay's season and refetches when the year changes",async()=>{
 render(<SessionPicker session={{Key:999,StartDate:'2025-05-25T15:00:00'}} archive={null} disabled={false} close={vi.fn()}/>)
 await waitFor(()=>expect(select('Year').value).toBe('2025'))
 expect(fetchMock.mock.calls.map(c=>c[0])).toEqual(['/api/archive','/api/archive?year=2025'])
 fireEvent.change(select('Year'),{target:{value:'2026'}})
 await waitFor(()=>expect(select('Year').value).toBe('2026'))
 expect(fetchMock.mock.calls.at(-1)![0]).toBe('/api/archive?year=2026')
 expect(select('Session').value).toBe('30')
})
it('is disabled while the dashboard is busy or offline',async()=>{
 render(<SessionPicker session={sprint} archive={null} disabled close={vi.fn()}/>)
 await waitFor(()=>expect(select('Session').value).toBe('30'))
 expect(['Year','Event','Session'].every(n=>select(n).disabled)).toBe(true)
 expect((screen.getByRole('button',{name:'Load'}) as HTMLButtonElement).disabled).toBe(true)
})
