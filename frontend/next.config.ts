import type {NextConfig} from 'next'
// The FastAPI backend serves the API and both WebSockets; rewrites proxy them
// (including WebSocket upgrades) so the browser keeps a single localhost origin.
const backend='http://127.0.0.1:8000'
const config:NextConfig={
 // Agent guidance lives in the repository's AGENTS.md; don't generate copies here.
 agentRules:false,
 rewrites:async()=>[{source:'/api/:path*',destination:`${backend}/api/:path*`},{source:'/ws/:path*',destination:`${backend}/ws/:path*`},{source:'/ws',destination:`${backend}/ws`}],
}
export default config
