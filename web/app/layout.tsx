import type { Metadata, Viewport } from 'next'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import './globals.css'

export const metadata: Metadata = {
  title: 'Consola de misión · Monitor de IA del dron',
  description:
    'Simulador de un dron que publica eventos en un bus, detector de reglas y agentes de IA (monitor e informe) que diagnostican lo que pasa.',
  icons: { icon: '/icon.svg' },
}

export const viewport: Viewport = {
  colorScheme: 'light',
  themeColor: '#eef1f5',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="es" className="bg-background">
      <body className="font-sans antialiased">{children}</body>
    </html>
  )
}
