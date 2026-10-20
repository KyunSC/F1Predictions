import type {Metadata,Viewport} from 'next'
import type {ReactNode} from 'react'
import '../src/style.css'
export const metadata:Metadata={title:'Pitwall · Local F1 timing'}
export const viewport:Viewport={width:'device-width',initialScale:1,themeColor:'#0d1015'}
// style.css names Inter (text) and Barlow Condensed (headings); load them so they don't fall back to Arial.
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en" suppressHydrationWarning><head><link rel="preconnect" href="https://fonts.googleapis.com"/><link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin=""/><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Inter:ital,wght@0,400;0,500;0,600;0,700;1,800&display=swap"/></head><body>{children}</body></html>}
