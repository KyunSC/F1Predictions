import type {Metadata,Viewport} from 'next'
import type {ReactNode} from 'react'
import '../src/style.css'
export const metadata:Metadata={title:'Pitwall · Local F1 timing'}
export const viewport:Viewport={width:'device-width',initialScale:1,themeColor:'#0d1015'}
// Inter for text and timing figures, Barlow Condensed for headings, positions and the lap count.
const fonts='https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Inter:wght@400;500;600;700;800&display=swap'
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en" suppressHydrationWarning><head><link rel="preconnect" href="https://fonts.googleapis.com"/><link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin=""/><link rel="stylesheet" href={fonts}/></head><body>{children}</body></html>}
