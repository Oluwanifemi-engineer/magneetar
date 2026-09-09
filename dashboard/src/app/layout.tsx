import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import 'leaflet/dist/leaflet.css';
import './globals.css';
import SkipNav from '@/components/ui/SkipNav';
import FocusIndicator from '@/components/ui/FocusIndicator';

const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  display: 'swap',
  variable: '--font-inter',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-jetbrains',
});

export const metadata: Metadata = {
  title: 'MAGNEETAR — Protect What You Own. Stay Close to Who You Love.',
  description:
    'Anti-theft tracking for Android. When your phone is stolen, it keeps reporting its location, captures evidence, and lets you lock it remotely. Built for Africa.',
  keywords: [
    'anti-theft',
    'device tracking',
    'gps tracker',
    'smartphone security',
    'theft recovery',
    'phone theft Nigeria',
    'anti theft app Africa',
    'track stolen phone Nigeria',
    'phone tracking app',
    'stolen phone recovery',
    'anti theft Android',
    'Magneetar',
  ],
  openGraph: {
    title: 'MAGNEETAR — Protect What You Own. Stay Close to Who You Love.',
    description:
      'Anti-theft tracking for Android. When your phone is stolen, it keeps reporting its location, captures evidence, and lets you lock it remotely.',
    type: 'website',
  },
  icons: {
    icon: '/favicon.svg',
  },
};

export const viewport: Viewport = {
  themeColor: '#030712',
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
        <link rel="manifest" href="/manifest.json" />

      </head>
      <body className={`bg-mag-bg text-mag-text min-h-screen antialiased ${inter.variable} ${jetbrainsMono.variable}`}>
        {/* WCAG 2.4.1: Skip navigation for keyboard users */}
        <SkipNav />
        {/* WCAG 2.4.7/2.4.11: Focus indicators + target size + reduced motion */}
        <FocusIndicator />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              if ('serviceWorker' in navigator) {
                window.addEventListener('load', () => {
                  navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).then((registration) => {
                    console.log('SW registered:', registration.scope);
                  }).catch((error) => {
                    console.log('SW registration failed:', error);
                  });
                });
              }
            `,
          }}
        />
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
      </body>
    </html>
  );
}
