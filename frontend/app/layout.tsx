import type {Metadata,Viewport} from 'next'
import type {ReactNode} from 'react'
import {Barlow,Barlow_Condensed} from 'next/font/google'
import '../src/style.css'
// Barlow for text, its condensed cut for positions, codes and headings: the narrow, upright
// shapes of a timing screen. next/font self-hosts both, so the page makes no font requests.
const text=Barlow({subsets:['latin'],weight:['400','500','600'],variable:'--font-text',display:'swap'})
const display=Barlow_Condensed({subsets:['latin'],weight:['500','600','700','800'],style:['normal','italic'],variable:'--font-display',display:'swap'})
export const metadata:Metadata={title:'Pitwall · Local F1 timing'}
export const viewport:Viewport={width:'device-width',initialScale:1,themeColor:'#0c0e12'}
export default function RootLayout({children}:{children:ReactNode}){return <html lang="en" className={`${text.variable} ${display.variable}`} suppressHydrationWarning><body>{children}</body></html>}
