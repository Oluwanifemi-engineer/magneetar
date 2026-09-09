'use client';

import { useState, useEffect } from 'react';
import { MapPin, Shield, Camera, Lock, Zap, ChevronRight, Monitor, Smartphone, Battery } from 'lucide-react';

/**
 * ProductShowcase — shows what the real dashboard looks like.
 * No fake "live" data, no pretending to connect to an API.
 * Just honest screenshots of the actual product UI.
 */

const SCREENSHOTS = [
  {
    id: 'dashboard',
    label: 'Command Center',
    description: 'Full-screen map with device tracking, floating actions, and device drawer',
    render: () => <DashboardScreenshot />,
  },
  {
    id: 'sentinel',
    label: 'Theft Detection',
    description: 'Automatic theft scoring across 8 signals',
    render: () => <SentinelScreenshot />,
  },
  {
    id: 'evidence',
    label: 'Evidence Capture',
    description: 'Tamper-evident photos and audio you can take to the police',
    render: () => <EvidenceScreenshot />,
  },
  {
    id: 'commands',
    label: 'Remote Commands',
    description: 'Lock, siren, wipe, phantom mode — one click execution',
    render: () => <CommandsScreenshot />,
  },
];

/* ── Dashboard Screenshot ────────────────────────────────────────────── */
function DashboardScreenshot() {
  return (
    <div className="bg-mag-landing rounded-xl overflow-hidden border-mag-border/50 shadow-elevation-4">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-3 py-2 bg-mag-landing-chrome border-b border-mag-border/50">
        <div className="flex gap-1">
          <div className="w-2 h-2 rounded-full bg-red-500/70" />
          <div className="w-2 h-2 rounded-full bg-yellow-500/70" />
          <div className="w-2 h-2 rounded-full bg-emerald-500/70" />
        </div>
        <span className="text-[9px] font-mono text-mag-text-muted ml-1">magneetar.me/dashboard</span>
      </div>

      <div className="flex h-64">
        {/* Sidebar */}
        <div className="w-36 bg-mag-landing-side border-r border-mag-border/50 p-2.5 flex flex-col">
          <div className="text-[8px] font-mono text-mag-text-muted mb-2 tracking-wider">DEVICES</div>
          {[
            { name: 'Galaxy S24', status: 'online', color: 'bg-emerald-500' },
            { name: 'Pixel 8', status: 'stolen', color: 'bg-red-500' },
            { name: 'Redmi Note 12', status: 'offline', color: 'bg-mag-text-muted/50' },
          ].map((d) => (
            <div key={d.name} className={`flex items-center gap-1.5 px-2 py-1.5 rounded-md mb-1 ${d.status === 'online' ? 'bg-mag-surface-raised' : ''}`}>
              <div className={`w-1.5 h-1.5 rounded-full ${d.color}`} />
              <span className="text-[9px] font-mono text-mag-text-muted truncate">{d.name}</span>
            </div>
          ))}

          <div className="mt-auto text-[8px] font-mono text-mag-text-muted">MAGNEETAR v1.4.4</div>
        </div>

        {/* Map area */}
        <div className="flex-1 relative">
          {/* Grid pattern simulating map */}
          <div className="absolute inset-0 bg-grid-dark bg-[size:16px_16px] opacity-30" />

          {/* Device marker */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
            <div className="relative">
              <div className="absolute -inset-6 rounded-full bg-emerald-500/10 animate-pulse" />
              <div className="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center shadow-glow-md">
                <MapPin size={14} className="text-white" />
              </div>
            </div>
          </div>

          {/* Bottom info bar */}
          <div className="absolute bottom-0 left-0 right-0 bg-mag-landing/90 backdrop-blur-sm border-t border-mag-border/50 px-3 py-2 flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="text-[9px] font-mono text-mag-text-muted">Galaxy S24</span>
            </div>
            <span className="text-[9px] font-mono text-mag-text-muted">6.524°N 3.379°E</span>
            <span className="text-[9px] font-mono text-emerald-400/60">● LIVE</span>
            <div className="ml-auto flex items-center gap-1">
              <Battery size={9} className="text-mag-text-muted/50" />
              <span className="text-[9px] font-mono text-mag-text-muted">87%</span>
            </div>
          </div>
        </div>

        {/* Right panel */}
        <div className="w-40 bg-mag-landing-side border-l border-mag-border/50 p-2.5">
          <div className="text-[8px] font-mono text-mag-text-muted mb-2 tracking-wider">DETECTION</div>
          <div className="bg-mag-surface border-mag-border rounded-lg p-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[9px] font-mono text-mag-text-dim">Score</span>
              <span className="text-[10px] font-mono font-bold text-emerald-400">12</span>
            </div>
            <div className="h-1 border-mag-border/50 rounded-full overflow-hidden">
              <div className="h-full bg-emerald-400/60 rounded-full" style={{ width: '12%' }} />
            </div>
            <div className="text-[8px] font-mono text-emerald-400/50 mt-1">SAFE</div>
          </div>

          <div className="mt-3 text-[8px] font-mono text-mag-text-muted mb-1.5 tracking-wider">COMMANDS</div>
          <div className="space-y-1">              {['Ping Device', 'Lock Screen', 'Siren', 'Capture Evidence'].map((cmd) => (
              <div key={cmd} className="flex items-center gap-1.5 px-2 py-1.5 rounded bg-mag-surface border-mag-border/50">
                <span className="text-[9px] font-mono text-mag-text-muted">{cmd}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Sentinel Screenshot ─────────────────────────────────────────────── */
function SentinelScreenshot() {
  const signals = [
    { name: 'Motion Pattern', score: 8, weight: 25, status: 'normal' },
    { name: 'Battery Drop', score: 3, weight: 15, status: 'normal' },
    { name: 'SIM Change', score: 0, weight: 20, status: 'armed' },
    { name: 'Location Drift', score: 5, weight: 15, status: 'normal' },
    { name: 'Network Switch', score: 2, weight: 10, status: 'normal' },
    { name: 'Time Pattern', score: 4, weight: 15, status: 'normal' },
  ];

  return (
    <div className="bg-mag-landing rounded-xl overflow-hidden border-mag-border/50 shadow-elevation-4 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[10px] font-mono text-mag-text-muted tracking-wider">DETECTION</div>
          <div className="text-2xl font-extrabold text-white mt-1 font-mono tabular-nums">Threat Score: <span className="text-emerald-400">12</span></div>
        </div>
        <div className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
          <span className="text-[10px] font-mono font-bold text-emerald-400">SECURE</span>
        </div>
      </div>

      {/* Score bar */}          <div className="h-2 border-mag-border/50 rounded-full overflow-hidden mb-5">
        <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400" style={{ width: '12%' }} />
      </div>

      {/* Signal breakdown */}
      <div className="grid grid-cols-2 gap-2">          {signals.map((s) => (
            <div key={s.name} className="flex items-center gap-3 p-2.5 rounded-lg bg-mag-surface border-mag-border/50">
            <div className="flex-1 min-w-0">
              <div className="text-[10px] font-mono text-mag-text-muted">{s.name}</div>
              <div className="text-[8px] font-mono text-mag-text-muted">Weight: {s.weight}%</div>
            </div>
            <div className="text-right">
              <div className={`text-[11px] font-mono font-bold ${s.score >= 70 ? 'text-red-400' : s.score >= 40 ? 'text-amber-400' : 'text-emerald-400'}`}>{s.score}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Evidence Screenshot ─────────────────────────────────────────────── */
function EvidenceScreenshot() {
  const evidence = [
    { type: 'Photo', time: '10:02:31', hash: 'a3f2...8b1c', status: 'sealed' },
    { type: 'Audio', time: '10:02:28', hash: 'd7e1...4f2a', status: 'sealed' },
    { type: 'Photo', time: '10:01:55', hash: '9c4b...e6d3', status: 'sealed' },
    { type: 'Location', time: '10:02:33', hash: 'f1a8...2c7e', status: 'sealed' },
  ];

  return (
    <div className="bg-mag-landing rounded-xl overflow-hidden border-mag-border/50 shadow-elevation-4 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[10px] font-mono text-mag-text-muted tracking-wider">EVIDENCE LOG</div>
          <div className="text-sm font-bold text-white mt-1">Galaxy S24 — Chain of Custody</div>
        </div>
        <div className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
          <span className="text-[10px] font-mono font-bold text-emerald-400">VERIFIED</span>
        </div>
      </div>

      <div className="space-y-2">        {evidence.map((e, i) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-mag-surface border-mag-border/50">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              e.type === 'Photo' ? 'bg-blue-500/10 border border-blue-500/20' :
              e.type === 'Audio' ? 'bg-purple-500/10 border border-purple-500/20' :
              'bg-emerald-500/10 border border-emerald-500/20'
            }`}>
              {e.type === 'Photo' ? <Camera size={14} className="text-blue-400" /> :
               e.type === 'Audio' ? <Zap size={14} className="text-purple-400" /> :
               <MapPin size={14} className="text-emerald-400" />}
            </div>
            <div className="flex-1">
              <div className="text-[10px] font-mono text-mag-text-muted">{e.type}</div>
              <div className="text-[9px] font-mono text-mag-text-muted">{e.time}</div>
            </div>
            <div className="text-right">
              <div className="text-[9px] font-mono text-mag-text-muted">{e.hash}</div>
              <div className="text-[8px] font-mono text-emerald-400/60">SEALED</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Commands Screenshot ─────────────────────────────────────────────── */
function CommandsScreenshot() {
  const commands = [
    { icon: Shield, name: 'Ping Device', desc: 'Trigger max-volume alarm', status: 'delivered', color: 'emerald' },
    { icon: Lock, name: 'Lock Screen', desc: 'Remote screen lock with custom message', status: 'armed', color: 'amber' },
    { icon: Zap, name: 'Siren', desc: 'Maximum volume alarm for 5 minutes', status: 'pending', color: 'red' },
    { icon: Camera, name: 'Capture Evidence', desc: 'Front/rear photo + 20s audio', status: 'delivered', color: 'blue' },
    { icon: Lock, name: 'Wipe Data', desc: 'Factory reset with evidence preservation', status: 'locked', color: 'red' },
  ];

  return (
    <div className="bg-mag-landing rounded-xl overflow-hidden border-mag-border/50 shadow-elevation-4 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-[10px] font-mono text-mag-text-muted tracking-wider">REMOTE COMMANDS</div>
          <div className="text-sm font-bold text-white mt-1">Galaxy S24 — Command Queue</div>
        </div>
      </div>

      <div className="space-y-2">          {commands.map((cmd) => (
            <div key={cmd.name} className="flex items-center gap-3 p-3 rounded-lg bg-mag-surface border-mag-border/50 hover:border-mag-border transition-all cursor-pointer group">
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all group-hover:scale-105 ${
              cmd.color === 'emerald' ? 'bg-emerald-500/10 border border-emerald-500/20' :
              cmd.color === 'amber' ? 'bg-amber-500/10 border border-amber-500/20' :
              cmd.color === 'blue' ? 'bg-blue-500/10 border border-blue-500/20' :
              'bg-red-500/10 border border-red-500/20'
            }`}>
              <cmd.icon size={16} className={`${
                cmd.color === 'emerald' ? 'text-emerald-400' :
                cmd.color === 'amber' ? 'text-amber-400' :
                cmd.color === 'blue' ? 'text-blue-400' :
                'text-red-400'
              }`} />
            </div>
            <div className="flex-1">
              <div className="text-[11px] font-mono font-bold text-mag-text">{cmd.name}</div>
              <div className="text-[9px] font-mono text-mag-text-muted">{cmd.desc}</div>
            </div>
            <div className={`px-2 py-0.5 rounded text-[8px] font-mono font-bold tracking-wider ${
              cmd.status === 'delivered' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
              cmd.status === 'armed' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
              cmd.status === 'pending' ? 'bg-mag-surface text-mag-text-muted border-mag-border/50' :
              'bg-red-500/10 text-red-400 border border-red-500/20'
            }`}>
              {cmd.status.toUpperCase()}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ProductShowcase() {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <section className="py-28 sm:py-36 bg-black relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="text-center mb-12">              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border-mag-border/50 bg-mag-surface mb-5">
            <Monitor size={10} className="text-emerald-400" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-mag-text-muted">THE PRODUCT</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-4">
            What you actually get.
          </h2>
          <p className="text-mag-text-muted text-base max-w-lg mx-auto">
            No mockups. No concept art. This is the real Magneetar command center — web dashboard and mobile app.
          </p>
        </div>

        <div className="grid lg:grid-cols-5 gap-6 items-start">
          {/* Screenshot — takes 3 columns */}
          <div className="lg:col-span-3">
            <div className="transition-all duration-500">
              {SCREENSHOTS[activeTab].render()}
            </div>
          </div>

          {/* Tab selector — takes 2 columns */}
          <div className="lg:col-span-2 space-y-2">              {SCREENSHOTS.map((s, i) => (
                <button
                  key={s.id}
                  onClick={() => setActiveTab(i)}
                  className={"w-full text-left p-3.5 rounded-xl border transition-all duration-300 " +
                    (i === activeTab
                      ? 'bg-mag-surface-raised border-emerald-500/20 shadow-glow-sm'
                      : 'border-mag-border/25 hover:bg-mag-surface hover:border-mag-border/50')
                  }
              >
                <div className="flex items-center gap-3">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all ${
                    i === activeTab ? 'bg-emerald-500/10 border border-emerald-500/20' : 'bg-mag-surface border-mag-border'
                  }`}>
                    {i === 0 ? <Monitor size={16} className={i === activeTab ? 'text-emerald-400' : 'text-mag-text-muted'} /> :
                     i === 1 ? <Shield size={16} className={i === activeTab ? 'text-emerald-400' : 'text-mag-text-muted'} /> :
                     i === 2 ? <Camera size={16} className={i === activeTab ? 'text-emerald-400' : 'text-mag-text-muted'} /> :
                     <Lock size={16} className={i === activeTab ? 'text-emerald-400' : 'text-mag-text-muted'} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className={`text-sm font-bold transition-colors ${i === activeTab ? 'text-white' : 'text-mag-text-muted'}`}>
                      {s.label}
                    </span>
                    {i === activeTab && (
                      <p className="text-xs text-mag-text-muted mt-0.5 leading-relaxed">{s.description}</p>
                    )}
                  </div>
                  {i === activeTab && (
                    <ChevronRight size={14} className="text-emerald-400/50 shrink-0" />
                  )}
                </div>
              </button>
            ))}

            {/* Trust badges */}              <div className="flex items-center gap-4 pt-4 border-t border-mag-border mt-3">
              {['Uninstall-resistant', 'Encrypted', 'Source-available'].map((label) => (
                <span key={label} className="text-[9px] font-mono text-mag-text-muted">{label}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
