import type { Metadata, Viewport } from 'next';
import 'leaflet/dist/leaflet.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'MAGNEETAR — Tactical Command Center',
  description: 'Military-grade device tracking and anti-theft command center',
  icons: {
    icon: '/favicon.svg',
  },
};

export const viewport: Viewport = {
  themeColor: '#0a0a0f',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="application-name" content="MAGNEETAR" />
      </head>
      <body className="bg-mag-bg text-mag-text min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
