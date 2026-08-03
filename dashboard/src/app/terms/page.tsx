'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LandingNav } from '@/components/landing/LandingNav';
import { Footer } from '@/components/landing/Footer';
import {
  ScrollText,
  UserCheck,
  ShieldAlert,
  Camera,
  Lock,
  FileText,
  AlertTriangle,
  Ban,
  Gavel,
  Mail,
  ArrowLeft,
  CheckCircle2,
} from 'lucide-react';

const SECTIONS = [
  {
    icon: ScrollText,
    title: '1. These Terms',
    body: [
      'These Terms of Service ("Terms") govern your use of Magneetar — the Android app, the web command center, and the Magneetar API (together, "the Service").',
      'By creating an account or using the Service, you agree to these Terms and to our Privacy Policy. If you do not agree, do not use the Service.',
      'The Service is operated by Magneetar (Lagos, Nigeria). References to "we", "us", or "our" mean Magneetar.',
    ],
  },
  {
    icon: UserCheck,
    title: '2. Your Account',
    body: [
      'You must be at least 18 years old, or the age of legal majority in your jurisdiction, to create an account. If you are younger, a parent or guardian must create the account and accept these Terms on your behalf.',
      'You are responsible for keeping your credentials confidential and for all activity under your account. Contact privacy@magneetar.me immediately if you believe your account has been compromised.',
      'You may hold multiple accounts, use one account for multiple devices, and add family, coworkers, or team members to your circles as you choose.',
    ],
  },
  {
    icon: ShieldAlert,
    title: '3. Acceptable Use — No Covert Surveillance',
    body: [
      'Magneetar is an anti-theft and location-sharing service. You may only track, capture evidence from, or issue commands to devices that you own or that you have been explicitly authorized to manage by the owner.',
      'You must not use the Service to spy on, stalk, or secretly monitor another person — including partners, family members, employees, or tenants — without their informed consent. This is prohibited by these Terms, by Nigerian law, and by the NDPR.',
      'Evidence capture (photo/audio) is designed to run on your own devices during a theft response, with the persistent notification shown on the device. Using it for covert surveillance is a material breach of these Terms and grounds for immediate termination, account deletion, and reporting to law enforcement where appropriate.',
      'If you share a device with someone else, you are responsible for obtaining their consent before enabling theft detection or evidence capture on that device.',
    ],
  },
  {
    icon: Camera,
    title: '4. Evidence Capture & Consent',
    body: [
      'By enabling theft detection on a device, you authorize Magneetar to capture photos and audio when an active theft response is triggered, and to store that evidence with a SHA-256 chain of custody for presentation to law enforcement.',
      'You confirm that you are the owner of (or are authorized to manage) the device on which you enable these features, and that the people reasonably expected to use it are aware it is protected by Magneetar.',
      'Evidence is stored encrypted and retained per our Privacy Policy. You can purge evidence cases permanently from the command center at any time.',
      'You are responsible for how you use captured evidence. Magneetar does not provide legal advice; if you intend to use evidence in legal proceedings, we recommend involving law enforcement early.',
    ],
  },
  {
    icon: Lock,
    title: '5. Privacy & Data Protection',
    body: [
      'We process personal data — including location data and evidence media — in accordance with our Privacy Policy, the Nigeria Data Protection Act and NDPR, and the GDPR where it applies to you.',
      'You have the right to access, export, correct, and delete your data, and to withdraw consent at any time. Exercise these rights from the dashboard or by emailing privacy@magneetar.me.',
      'We do not sell your data. We do not share it with third parties except as needed to operate the Service (for example, your chosen alert providers) or as required by law.',
      'Because of the sensitivity of location data, we encrypt it at rest (AES-256-GCM, per-device keys) and in transit (TLS).',
    ],
  },
  {
    icon: FileText,
    title: '6. Plans, Fees & Payments',
    body: [
      'Magneetar offers a free plan (protects 1 device) and paid plans with higher device allowances: Personal (up to 3 devices) and Guardian (up to 10 devices), billed in Nigerian Naira monthly or yearly. Enterprise pricing is customised per organisation.',
      'Paid plan fees are disclosed on our pricing page before you commit. We will give you at least 30 days&apos; notice before raising prices on an active paid plan, and you can downgrade or cancel at any time.',
      'Until self-serve online payment is live, paid upgrades are activated manually by our team after payment. Once applied, your plan tier and its device allowance are enforced automatically by the service.',
      'Upgrading never requires re-registering your devices, and downgrading never deletes your data — it only caps how many additional devices you can add.',
    ],
  },
  {
    icon: AlertTriangle,
    title: '7. No Guarantee of Recovery',
    body: [
      'Magneetar dramatically improves your chances of recovering a stolen device — but we do not and cannot guarantee recovery, and we are not a security or law-enforcement agency.',
      'The Service depends on factors outside our control: device hardware, battery, network coverage, OEM background restrictions, and the actions of the person holding the device.',
      'Evidence we capture is provided for informational and law-enforcement purposes only. We do not guarantee that any particular evidence will be admissible in any legal proceeding.',
      'To the maximum extent permitted by law, the Service is provided "as is" and "as available" without warranties of any kind, express or implied.',
    ],
  },
  {
    icon: Ban,
    title: '8. Termination',
    body: [
      'You may stop using the Service and delete your account at any time from the dashboard. Deletion is permanent and removes your devices, location history, and evidence cases.',
      'We may suspend or terminate access to the Service — with or without notice — if you breach these Terms, especially Section 3 (Acceptable Use), or if we are required to do so by law.',
      'Upon termination, your data is deleted in line with our retention and deletion practices. Sections that by their nature survive termination (including Sections 5, 7, 9, and 10) continue to apply.',
    ],
  },
  {
    icon: Gavel,
    title: '9. Dispute Resolution & Governing Law',
    body: [
      'These Terms are governed by the laws of the Federal Republic of Nigeria.',
      'We encourage you to contact us first — most issues are resolved in a single email. Any dispute not resolved informally will be subject to the exclusive jurisdiction of the courts of Lagos State, Nigeria.',
      'Nothing in these Terms limits any mandatory consumer-protection rights you may have under the law of your country of residence.',
    ],
  },
  {
    icon: Mail,
    title: '10. Changes to These Terms',
    body: [
      'We may update these Terms as the Service evolves. Material changes will be announced through the Service (for example, a notice in the dashboard) at least 14 days before they take effect.',
      'Continued use of the Service after changes take effect constitutes acceptance of the updated Terms. If you do not accept them, you can delete your account before the effective date.',
      'Questions about these Terms? Email legal@magneetar.me — we respond within 30 days.',
    ],
  },
];

export default function TermsPage() {
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const serverUrl = sessionStorage.getItem('mt_server_url');
    const apiKey = sessionStorage.getItem('mt_api_key');
    setAuthed(Boolean(serverUrl && apiKey));
  }, []);

  return (
    <div className="min-h-screen bg-mag-bg text-white overflow-x-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-40 pointer-events-none" />
      <div className="absolute -top-40 left-1/3 w-[600px] h-[400px] rounded-full bg-[#E91E8C]/10 blur-[130px] animate-aurora pointer-events-none" aria-hidden="true" />
      <div className="absolute top-1/3 -right-32 w-[480px] h-[480px] rounded-full bg-[#06B6D4]/8 blur-[120px] animate-aurora pointer-events-none" style={{ animationDelay: '-6s' }} aria-hidden="true" />

      <LandingNav authed={authed} />

      <main className="relative max-w-4xl mx-auto px-5 sm:px-8 pt-16 pb-24">
        {/* Back link */}
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-[11px] font-mono font-bold tracking-wider text-white/40 hover:text-white transition-colors"
        >
          <ArrowLeft size={13} />
          BACK TO HOME
        </Link>

        {/* Header */}
        <header className="mt-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-5">
            <ScrollText size={12} className="text-[#06B6D4]" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">TERMS OF SERVICE</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-display font-extrabold tracking-tight leading-[1.1]">
            Clear rules for
            <br />
            <span className="text-gradient-primary animate-gradient-x">a serious tool.</span>
          </h1>
          <p className="mt-5 text-white/45 leading-relaxed max-w-2xl text-[15px]">
            Magneetar is a powerful anti-theft system. These Terms keep it powerful for its intended
            purpose — recovering your own stolen devices and staying connected with your people — and
            clearly out of bounds for everything else. They apply to the Magneetar Android app, the web
            command center, and the Magneetar API.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-4">
            <span className="px-3 py-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] text-[10px] font-mono text-white/40">
              EFFECTIVE · AUGUST 1, 2026
            </span>
            <span className="px-3 py-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] text-[10px] font-mono text-white/40">
              VERSION 1.0
            </span>
            <span className="px-3 py-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.05] text-[10px] font-mono font-bold text-emerald-300 flex items-center gap-1.5">
              <CheckCircle2 size={11} />
              NO-COVERT-SURVEILLANCE COMMITMENT
            </span>
          </div>
        </header>

        {/* Sections */}
        <div className="mt-14 space-y-5">
          {SECTIONS.map((section, i) => (
            <section
              key={section.title}
              className="group rounded-2xl border border-white/[0.07] bg-mag-panel/40 backdrop-blur-sm p-7 sm:p-8 transition-all duration-300 hover:border-white/[0.14] hover:bg-mag-panel/60"
              style={{ animationDelay: `${i * 0.04}s` }}
            >
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 shrink-0 rounded-xl border border-white/[0.08] bg-white/[0.03] flex items-center justify-center">
                  <section.icon size={17} className="text-[#06B6D4]" />
                </div>
                <div className="flex-1">
                  <h2 className="text-lg font-display font-bold tracking-tight text-white">{section.title}</h2>
                  <ul className="mt-4 space-y-3">
                    {section.body.map((point) => (
                      <li key={point} className="flex gap-3 text-[13.5px] leading-relaxed text-white/45">
                        <span className="mt-[7px] w-1.5 h-1.5 shrink-0 rounded-full bg-gradient-to-r from-[#E91E8C] to-[#06B6D4]" aria-hidden="true" />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>
          ))}
        </div>

        {/* Contact block */}
        <div className="mt-12 rounded-2xl border border-[#E91E8C]/20 bg-gradient-to-br from-[#E91E8C]/[0.06] to-[#06B6D4]/[0.04] p-8 text-center">
          <Mail size={20} className="mx-auto text-[#E91E8C]" />
          <h2 className="mt-3 text-xl font-display font-bold tracking-tight">Questions about these terms?</h2>
          <p className="mt-2 text-[13.5px] text-white/45 max-w-lg mx-auto">
            Email{' '}
            <a href="mailto:legal@magneetar.me" className="text-[#06B6D4] hover:text-[#22D3EE] font-semibold transition-colors">
              legal@magneetar.me
            </a>{' '}
            — we respond within 30 days.
          </p>
        </div>
      </main>

      <Footer />
    </div>
  );
}
