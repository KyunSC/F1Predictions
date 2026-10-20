import type {Metadata,Viewport} from 'next'
import type {ReactNode} from 'react'
import '../src/style.css'
export const metadata:Metadata={title:'Pitwall · Local F1 timing'}
export const viewport:Viewport={width:'device-width',initialScale:1,themeColor:[{media:'(prefers-color-scheme: light)',color:'#f3f1ec'},{media:'(prefers-color-scheme: dark)',color:'#0d1015'}]}
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en" suppressHydrationWarning><head><link rel="preconnect" href="https://fonts.googleapis.com"/><link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin=""/><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,500;0,600;0,700;1,800&family=Barlow:wght@400;500;600;700&display=swap"/></head><body>{children}</body></html>}
