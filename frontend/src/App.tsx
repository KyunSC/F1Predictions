'use client'
import {useEffect,useRef,useState} from 'react'
import {usePresentation} from './positions'
import {TrackMap} from './TrackMap'
import {SessionPicker} from './SessionPicker'
import {pitLossNote,rejoinCell,rejoinTitle} from './pitRejoin'
import {formatPoints,movement,pointsGained,standingDetail,standingLabel} from './standings'
import {fastestLap,paceDelta,predictionScore,tabTitle} from './timing'
import {importantMessages,messageLevel} from './messages'
import {isInteractive,replayKey,store,stored} from './controls'
const dash=(v:unknown)=>v===undefined||v===null||v===''?'—':String(v)
const teamColor=(c?:string|null)=>`#${/^[0-9a-f]{6}$/i.test(c||'')?c:'888888'}`
// Display only: replay seconds as m:ss, and what each track status means for someone new to F1.
const clock=(s:number)=>{const t=Math.max(0,Math.floor(s));return `${Math.floor(t/60)}:${String(t%60).padStart(2,'0')}`}
const FLAG:Record<string,{tone:string;help:string}>={
 '1':{tone:'green',help:'normal racing'},
 '2':{tone:'yellow',help:'hazard on track: drivers must slow down and may not overtake there'},
 '4':{tone:'yellow',help:'safety car: cars queue behind it and may not overtake'},
 '5':{tone:'red',help:'session stopped, cars return to the pit lane'},
 '6':{tone:'yellow',help:'virtual safety car: every car must slow to a set pace'},
 '7':{tone:'yellow',help:'virtual safety car ending: racing resumes shortly'},
}
const COLUMNS:[string,string][]=[['Pos',''],['Driver',''],['Gap','to leader'],['Interval','to car ahead'],['If pit','would rejoin'],['Last lap',''],['Best lap',''],['Tyre',''],['Stint','laps on tyre']]
export function App(){
 // The stored choice survives reloads and session changes; it is shown only while that car is in the session.
 const [chosen,setChosen]=useState<string|null>(null),[important,setImportant]=useState(false),[scrub,setScrub]=useState<number|null>(null)
 const choose=(n:string|null)=>{setChosen(n);store('pitwall.selected',n)}
 useEffect(()=>{setChosen(stored('pitwall.selected'));setImportant(stored('pitwall.important')==='1')},[])
 const {data,stream,online,time}=usePresentation()
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[picking,setPicking]=useState(false)
 const control=async(action:string,speed?:number,position?:number)=>{setBusy(true);try{const response=await fetch('/api/replay/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,speed,position})});if(!response.ok)throw Error(await response.text());await response.json()}catch(e){setError(String(e))}finally{setBusy(false)}}
 const switchMode=async(mode:string)=>{setBusy(true);setError('');try{const response=await fetch('/api/mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})});if(!response.ok)throw Error(await response.text())}catch(e){setError(String(e))}finally{setBusy(false)}}
 const pickerButton=<button aria-expanded={picking} disabled={busy||!online} onClick={()=>setPicking(open=>!open)}>Change session</button>
 const selected=chosen&&(data?.drivers.some(d=>d.number===chosen)||stream?.samples?.[chosen])?chosen:null
 const rejoin=data?.drivers.find(d=>d.number===selected)?.pit_rejoin;const replay=data?.replay; const stale=!online||data?.connection.stale; const mode=data?.connection.mode
 const fastest=fastestLap(data?.drivers||[]),score=replay?.ended&&!data?.prediction_reason?predictionScore(data?.predictions||[],data?.drivers||[]):null
 const messages=important?importantMessages(data?.messages||[]):data?.messages||[]
 // Re-applied on every render: Next's metadata title can replace it after a reload.
 const title=tabTitle(data);useEffect(()=>{if(document.title!==title)document.title=title})
 const keys=useRef<(e:KeyboardEvent)=>void>(()=>{})
 useEffect(()=>{keys.current=e=>{if(!replay||busy||!online||e.defaultPrevented||e.repeat||e.ctrlKey||e.metaKey||e.altKey||isInteractive(e.target))return;const c=replayKey(e.key,replay);if(!c)return;e.preventDefault();control(c.action,'speed' in c?c.speed:undefined)}})
 useEffect(()=>{const handle=(e:KeyboardEvent)=>keys.current(e);addEventListener('keydown',handle);return()=>removeEventListener('keydown',handle)},[])
 const seekTo=async()=>{if(scrub===null)return;await control('seek',undefined,scrub);setScrub(null)}
 const lap=data?.laps.CurrentLap,laps=data?.laps.TotalLaps,leader=data?.drivers.find(d=>d.position==='1'),flag=FLAG[String(data?.track.Status??'')]
 return <main>
 <header>
  <a className="brand" href="/">P<span>Ⅱ</span>TWALL<span className="local">LOCAL / F1</span></a>
  <div className="header-actions">
   <div className={`badge ${stale?'warning':''}`}><i/>{!online?'Dashboard disconnected':replay?'Replay':stale?'Feed stale':'Live feed connected'}</div>
   <div className="mode-switch" role="group" aria-label="Dashboard mode">{[['replay','Historical'],['live','Live']].map(([m,label])=><button key={m} aria-pressed={mode===m} disabled={busy||!online||mode===m} onClick={()=>switchMode(m)}>{label}</button>)}</div>
   {mode==='live'&&pickerButton}
  </div>
 </header>
 <section className="hero">
  <div className="hero-title">
   <div className="eyebrow">{replay?'Recorded session':data?.connection.live_verified?'Live timing':'Live timing · awaiting verification'}</div>
   <h1>{data?.session.Meeting?.Name||'Waiting for session'}</h1>
   <div className="session-meta">{dash(data?.session.Meeting?.Location)} <span>/</span> {dash(data?.session.Name)}</div>
  </div>
  <div className="lap">
   <div className="lap-label">Lap</div>
   <div className="lap-count">{dash(lap)}<small> / {dash(laps)}</small></div>
   {lap&&laps?<div className="lap-bar" aria-hidden="true"><i style={{width:`${Math.min(100,lap/laps*100)}%`}}/></div>:null}
   {leader&&<p className="leader"><b>{leader.name||leader.code||leader.number}</b> leads</p>}
  </div>
 </section>
 <div className={`conditions flag-${flag?.tone||'none'}`}>
  <p className="track-status"><i className="track-dot"/><b>{data?.track.Message||'Track status unavailable'}</b>{flag&&<span> — {flag.help}</span>}</p>
  <span>Air <b>{dash(data?.weather.AirTemp)}°C</b></span><span>Track <b>{dash(data?.weather.TrackTemp)}°C</b></span>
  <span className="age">{replay?'Recorded data':`Received ${data?.connection.age_seconds==null?'—':Math.floor(data.connection.age_seconds)+'s ago'}`} {data?.connection.mode==='live'&&data.connection.source_age_seconds!=null?` · Source age ${data.connection.source_age_seconds.toFixed(1)}s`:''}</span>
 </div>
 {(!online||data?.connection.stale)&&<div role="status" className="notice">{!online?'Connecting to the local backend. Displayed data may be out of date.':'Timing data is stale. Waiting for fresh upstream updates.'}</div>}
 {data?.connection.error&&<div className="notice">{data.connection.error}</div>}
 {error&&<div role="alert" className="notice">{error}</div>}
 {replay&&<section className="replay" aria-label="Replay controls">
  <div className="replay-info">
   <p className="replay-title"><strong>{replay.label}</strong><span className="replay-time">{clock(scrub??replay.position)} / {clock(replay.duration)}{replay.ended?' · Finished':replay.paused?' · Paused':''}</span></p>
   <p>{replay.label==='Demo replay'?'Synthetic timing · not an actual race recording':'Recorded timing · not live'}<span className="keys" aria-hidden="true">Keys <kbd>Space</kbd> pause <kbd>R</kbd> restart <kbd>1</kbd><kbd>2</kbd><kbd>5</kbd> speed</span></p>
  </div>
  <div className="controls"><button disabled={busy||!online||replay.ended} onClick={()=>control(replay.paused?'resume':'pause')}>{replay.paused?'▶ Resume':'Ⅱ Pause'}</button><button disabled={busy||!online} onClick={()=>control('restart')}>↺ Restart</button><label>Speed <select aria-label="Replay speed" value={replay.speed} disabled={busy||!online} onChange={e=>control('speed',Number(e.target.value))}>{[1,2,5].map(n=><option key={n} value={n}>{n}×</option>)}</select></label>{pickerButton}</div>
  <input className="scrub" type="range" aria-label="Seek replay" min={0} max={Math.floor(replay.duration)} step={1} value={Math.floor(scrub??replay.position)} aria-valuetext={`${Math.floor(scrub??replay.position)} of ${Math.floor(replay.duration)} seconds`} disabled={busy||!online} onChange={e=>setScrub(Number(e.target.value))} onPointerUp={seekTo} onKeyUp={seekTo} onBlur={seekTo}/><progress max={replay.duration||1} value={scrub??replay.position}/>
 </section>}
 {picking&&<SessionPicker session={data?.session} archive={data?.archive} disabled={busy||!online} close={()=>setPicking(false)}/>}
 <div className="layout"><div className="main-column">
  <section className="panel timing" data-presentation-time={time}>
   <div className="panel-heading"><h2>Timing tower</h2><span>{data?.drivers.length||0} drivers</span></div>
   <p className="description">Running order, leader first. Select a driver to follow their car on the track map.</p>
   <p className="scroll-hint" aria-hidden="true">Swipe the table sideways for lap times, tyres and pit projections →</p><div className="table-scroll" role="region" aria-label="Timing tower" tabIndex={0}><table><thead><tr>{COLUMNS.map(([label,hint])=><th key={label} scope="col">{label}{hint&&<small>{hint}</small>}</th>)}</tr></thead><tbody>{data?.drivers.map(d=><tr key={d.number} data-driver-number={d.number} className={selected===d.number?'selected-driver':rejoin&&(rejoin.ahead===d.number||rejoin.behind===d.number)?'rejoin-neighbour':''}>
    <td className="position">{dash(d.position)}</td>
    <td className="driver-cell"><div className="driver" style={{borderColor:teamColor(d.color)}}><span className="driver-line"><button aria-pressed={selected===d.number} onClick={()=>choose(d.number)}>{d.code||d.name||d.number}</button>{d.code&&d.name&&<span className="driver-name">{d.name}</span>}</span><small>{d.team||'—'}</small></div></td>
    <td>{dash(d.gap)}</td><td>{dash(d.interval)}</td><td title={rejoinTitle(d,data.drivers)}>{rejoinCell(d)}</td><td>{dash(d.last_lap)}</td>
    <td className="best"><span className={fastest===d.number?'fastest':undefined} title={fastest===d.number?'Fastest lap of the session':undefined}>{dash(d.best_lap)}</span></td>
    <td><span className="tyre-cell"><span title={d.compound} className={`tyre ${d.compound?.toLowerCase()}`}>{d.compound?.slice(0,1)||'—'}</span>{d.compound&&<span className="tyre-name">{d.compound.toLowerCase()}</span>}</span></td>
    <td>{dash(d.stint_laps)}</td></tr>)}</tbody></table>{!data?.drivers.length&&<p className="empty">Timing will appear when session data arrives.</p>}</div>
   <div className="table-foot"><span>{replay?'Replay':'Live'} timing</span><span>{pitLossNote(data?.pit_loss,data?.track.Status)}</span><span className="key-fastest">Fastest lap of the session</span><span>Unavailable values shown as —</span></div>
  </section>
  <TrackMap stream={stream} online={online} time={time} drivers={data?.drivers||[]} selected={selected} select={choose} pitLoss={data?.pit_loss?.seconds}/>
 </div>
 <aside>
  <section className="panel predictions"><div className="panel-heading"><h2>Pre-race pace</h2><span>Fixed for the race</span></div>
   <p className="description">Pace rank is the pre-race prediction of each car's speed: 1 is fastest, and a lower ratio is faster. It does not predict the finishing order. The P-number shows where the car runs now, with ▲ ahead of its pace rank and ▼ behind it.</p>
   {score&&<div className="scorecard" role="status"><h3>How the prediction did</h3><p>Pace rank against the final classification · {score.drivers} drivers</p><dl><div><dt>Order match</dt><dd>{score.spearman.toFixed(2)}</dd></div><div><dt>Podium</dt><dd>{score.podium}/3</dd></div><div><dt>Winner</dt><dd>{score.winner?'Correct':'Missed'}</dd></div></dl><p className="hint">Order match is the Spearman rank correlation: 1.00 means the same order, 0 means no relation.</p></div>}
   {data?.prediction_reason?<div className="prediction-empty"><h3>No matching predictions</h3><p>{data.prediction_reason}</p></div>:data?.predictions.map(p=>{const delta=paceDelta(p,data.drivers.find(d=>d.number===p.racing_number));return <div className="prediction-row" key={p.racing_number}><b>{p.pace_rank}</b><span>{data.drivers.find(d=>d.number===p.racing_number)?.code||p.driver}<small>{Object.values(p.missing_features).some(Boolean)?'Missing inputs: '+Object.entries(p.missing_features).filter(([,v])=>v).map(([k])=>k.replace('Missing','')).join(', '):'All inputs available'}</small></span>{delta&&<span className={`movement ${delta.change>0?'up':delta.change<0?'down':''}`} title={delta.title}>{delta.label}</span>}<code>{p.predicted_pace_ratio.toFixed(4)}</code></div>})}
   {data?.prediction_generated_at&&<p className="description generated">Generated {new Date(data.prediction_generated_at).toLocaleString()}</p>}
  </section>
  <section className="panel standings"><div className="panel-heading"><h2>Championship if positions hold</h2><span>Drivers</span></div>
   <p className="description">Drivers' standings if every car finished where it runs now, as projected by the F1 timing feed.</p>
   {data?.standings?.rows.length?<div className="standings-list" role="region" aria-label="Projected drivers' standings" tabIndex={0}>{data.standings.rows.map(s=><div className={`standing-row ${selected===s.number?'selected-driver':''}`} key={s.number}><b>{s.position}</b><span className="standing-driver" style={{borderColor:teamColor(s.color)}}>{standingLabel(s)}<small>{standingDetail(s)}</small></span><span className={`movement ${s.positions_gained&&s.positions_gained>0?'up':'down'}`}>{movement(s)}</span><code>{formatPoints(s.points)}<small>{pointsGained(s)}</small></code></div>)}</div>:<p className="empty">{data?.standings?.reason||'Championship projection unavailable.'}</p>}
  </section>
  <section className="panel race-control"><div className="panel-heading"><h2>Race control</h2><button className="filter" aria-pressed={important} onClick={()=>{setImportant(!important);store('pitwall.important',important?null:'1')}}>Important only</button></div>
   <p className="description">Official messages from the race director: flags, penalties and investigations.</p>
   <div className="message-list" role="region" aria-label="Race control messages" tabIndex={0}>{messages.length?messages.map((m,i)=><article key={`${m.Utc}-${i}`} className={`level-${messageLevel(m)}`}><time>{m.Utc?m.Utc.slice(11,19):'—'}</time><p>{m.Message||'—'}</p></article>):<p className="empty">{important&&data?.messages.length?'No flags, penalties or investigations yet.':'No race-control messages.'}</p>}</div>
  </section>
 </aside></div>
 <footer><span>Personal Pitwall</span><span>Local session · {replay?'replay':data?.connection.live_verified?'live timing received':'live connectivity unverified'} · Approximate track-projected positions</span></footer>
 </main>
}
