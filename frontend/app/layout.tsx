import type {Metadata,Viewport} from 'next'
import type {ReactNode} from 'react'
import '../src/style.css'
export const metadata:Metadata={title:'Pitwall · Local F1 timing'}
export const viewport:Viewport={width:'device-width',initialScale:1,themeColor:'#101318'}
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en" suppressHydrationWarning><body>{children}</body></html>}
