import type {Metadata,Viewport} from 'next'
import type {ReactNode} from 'react'
import '../src/style.css'
export const metadata:Metadata={title:'Pitwall · Local F1 timing'}
export const viewport:Viewport={width:'device-width',initialScale:1,themeColor:'#0d1015'}
// Barlow for text, Barlow Condensed for headings and figures, JetBrains Mono for lap times.
const fonts='https://fonts.googleapis.com/css2?family=Barlow:ital,wght@0,400;0,500;0,600;1,800&family=Barlow+Condensed:wght@500;600;700&family=JetBrains+Mono:wght@400;600&display=swap'
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en" suppressHydrationWarning><head><link rel="preconnect" href="https://fonts.googleapis.com"/><link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin=""/><link rel="stylesheet" href={fonts}/></head><body>{children}</body></html>}
