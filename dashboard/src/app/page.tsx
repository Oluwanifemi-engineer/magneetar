'use client';

import { useEffect, useState } from 'react';
import { LandingNav } from '@/components/landing/LandingNav';
import { Hero } from '@/components/landing/Hero';
import { Features } from '@/components/landing/Features';
import { HowItWorks } from '@/components/landing/HowItWorks';
import { Africa } from '@/components/landing/Africa';
import { Provenance } from '@/components/landing/Provenance';
import { Security } from '@/components/landing/Security';
import { Pricing } from '@/components/landing/Pricing';
import { CTA } from '@/components/landing/CTA';
import { Footer } from '@/components/landing/Footer';
import { Reveal } from '@/hooks/useScrollReveal';

export default function HomePage() {
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const serverUrl = sessionStorage.getItem('mt_server_url');
    const apiKey = sessionStorage.getItem('mt_api_key');
    setAuthed(Boolean(serverUrl && apiKey));
  }, []);

  return (
    <div className="min-h-screen bg-white text-gray-900 overflow-x-hidden">
      <LandingNav authed={authed} />
      <main>
        <Hero authed={authed} />
        <Reveal><Features /></Reveal>
        <Reveal><HowItWorks /></Reveal>
        <Reveal><Africa /></Reveal>
        <Reveal><Provenance /></Reveal>
        <Reveal><Security /></Reveal>
        <Reveal><Pricing authed={authed} /></Reveal>
        <Reveal><CTA authed={authed} /></Reveal>
      </main>
      <Footer />
    </div>
  );
}
