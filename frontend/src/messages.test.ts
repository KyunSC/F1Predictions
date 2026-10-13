import {expect,it} from 'vitest'
import {importantMessages,messageLevel} from './messages'
it('ranks race-control messages by importance',()=>{
 expect(messageLevel({Category:'SafetyCar',Message:'VSC DEPLOYED'})).toBe('major')
 expect(messageLevel({Category:'Flag',Flag:'RED',Message:'RED FLAG'})).toBe('major')
 expect(messageLevel({Category:'Flag',Flag:'CHEQUERED',Message:'CHEQUERED FLAG'})).toBe('major')
 expect(messageLevel({Category:'Other',Message:'FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 44 (HAM)'})).toBe('major')
 expect(messageLevel({Category:'Flag',Flag:'DOUBLE YELLOW',Message:'DOUBLE YELLOW IN TRACK SECTOR 14'})).toBe('minor')
 expect(messageLevel({Category:'Flag',Flag:'BLACK AND WHITE',Message:'BLACK AND WHITE FLAG FOR CAR 12 (ANT) - TRACK LIMITS'})).toBe('minor')
 expect(messageLevel({Category:'Other',Message:'FIA STEWARDS: TURN 1 INCIDENT INVOLVING CAR 44 (HAM) UNDER INVESTIGATION'})).toBe('minor')
 expect(messageLevel({Category:'Other',Message:'MARSHALS ON TRACK AT TURN 15'})).toBe('minor')
 expect(messageLevel({Category:'Other',Message:'FIA STEWARDS: TURN 1 INCIDENT INVOLVING CAR 55 (SAI) REVIEWED NO FURTHER INVESTIGATION'})).toBe('routine')
 expect(messageLevel({Category:'Other',Message:'CAR 87 (BEA) TIME 1:40.294 DELETED - TRACK LIMITS AT TURN 2 LAP 3'})).toBe('routine')
 expect(messageLevel({Category:'Flag',Flag:'BLUE',Message:'WAVED BLUE FLAG FOR CAR 77 (BOT)'})).toBe('routine')
 expect(messageLevel({})).toBe('routine')
})
it('keeps only important messages, in order',()=>{
 const messages=[{Message:'VSC DEPLOYED',Category:'SafetyCar'},{Message:'PIT EXIT OPEN'},{Message:'YELLOW IN TRACK SECTOR 5',Flag:'YELLOW'}]
 expect(importantMessages(messages)).toEqual([messages[0],messages[2]])
})
