// Preview-only: copied to frontend/instrumentation-client.ts by preview/run.sh. Never commit it to a redesign.
// Inside the switcher's iframe, digit keys pick a style instead of reaching the app. preventDefault
// in the capture phase also stops the replay's 1/2/5 speed shortcuts, which skip prevented events.
if(window.parent!==window)addEventListener('keydown',e=>{
 if(!/^[0-9]$/.test(e.key)||e.repeat||e.ctrlKey||e.metaKey||e.altKey)return
 if(e.target instanceof Element&&e.target.closest('input:not([type="range"]),select,textarea,[contenteditable="true"]'))return
 e.preventDefault()
 window.parent.postMessage({type:'pitwall-preview-key',key:e.key},'*')
},{capture:true})
