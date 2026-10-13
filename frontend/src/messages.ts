import type {Snapshot} from './types'
export type Message=Snapshot['messages'][number]
export type MessageLevel='major'|'minor'|'routine'
// Major: neutralisations, red and chequered flags, penalties. Minor: yellow and
// black-and-white flags, incidents and investigations. Everything else is routine.
export function messageLevel(m:Message):MessageLevel{
 const text=(m.Message||'').toUpperCase(),flag=(m.Flag||'').toUpperCase()
 if(/NO FURTHER/.test(text))return 'routine'
 if(m.Category==='SafetyCar'||['RED','BLACK','CHEQUERED'].includes(flag)||/PENALTY|DISQUALIF|SUSPENDED/.test(text))return 'major'
 if(['YELLOW','DOUBLE YELLOW','BLACK AND WHITE'].includes(flag)||/INVESTIGAT|NOTED|MARSHALS ON TRACK|RECOVERY VEHICLE/.test(text))return 'minor'
 return 'routine'
}
export const importantMessages=(messages:Message[])=>messages.filter(m=>messageLevel(m)!=='routine')
