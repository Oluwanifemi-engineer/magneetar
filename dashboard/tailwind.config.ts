import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        mag: {
          // Dark-first palette
          bg: '#030712',
          surface: '#111827',
          'surface-raised': '#1f2937',
          border: '#1f2937',
          'border-light': '#374151',

          // Landing page — intentional nested-dark hierarchy for visual depth.
          // These are deliberately lighter than mag.bg so landing cards pop
          // against the page; they mirror the dashboard surface scale but sit
          // between mag.bg and mag.surface for a lifted hero feel.
          'landing': '#0c1220',
          'landing-chrome': '#0a0e18',
          'landing-side': '#080c14',
          'landing-border': '#1f2937',

          // Primary — Aubergine magenta accent (the ONE brand color).
          // Used ONLY for primary actions, active states, focus rings, and
          // armed states. Status colors (emerald/amber/red) are reserved for
          // real status and must never be repurposed as decoration.
          // Chosen 2026-09-09 to match the black/white launcher icon and the
          // Android app's aubergine accent — one brand color, all platforms.
          primary: '#8E2A6E',
          'primary-bright': '#C0549C',
          'primary-dim': '#71265A',
          'primary-glow': 'rgba(142, 42, 110, 0.15)',

          // Danger
          danger: '#ef4444',
          'danger-glow': 'rgba(239, 68, 68, 0.15)',

          // Warning
          warning: '#f59e0b',
          'warning-glow': 'rgba(245, 158, 11, 0.15)',

          // Text hierarchy
          text: '#f9fafb',
          'text-dim': '#9ca3af',
          'text-muted': '#6b7280',
          // Text hierarchy levels (for panel/stat typography)
          'text-1': '#f9fafb',
          'text-2': '#9ca3af',
          'text-3': '#6b7280',
          'text-4': '#4b5563',
        },
      },
      fontFamily: {
        mono: ['var(--font-jetbrains)', '"SF Mono"', '"Share Tech Mono"', 'monospace'],
        sans: ['var(--font-inter)', '"SF Pro"', 'system-ui', 'sans-serif'],
        // FIX: font-display was undefined — now maps to Inter with display swap
        display: ['var(--font-inter)', '"SF Pro"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'glow-sm': '0 0 12px rgba(142, 42, 110, 0.10)',
        'glow-md': '0 0 24px rgba(142, 42, 110, 0.14)',
        'glow-lg': '0 0 48px rgba(142, 42, 110, 0.18)',
        'glow-xl': '0 8px 64px rgba(142, 42, 110, 0.22)',
        'elevation-1': '0 1px 3px rgba(0, 0, 0, 0.3)',
        'elevation-2': '0 4px 12px rgba(0, 0, 0, 0.4)',
        'elevation-3': '0 8px 32px rgba(0, 0, 0, 0.5)',
        'elevation-4': '0 16px 64px rgba(0, 0, 0, 0.6)',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'grid-dark': `linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px)`,
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'float': 'float 6s ease-in-out infinite',
        'float-slow': 'float 8s ease-in-out infinite',
        'glow-pulse': 'glowPulse 3s ease-in-out infinite',
        'slide-up': 'slideUp 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-in': 'fadeIn 0.6s ease-out',
        'scale-in': 'scaleIn 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-12px)' },
        },
        glowPulse: {
          '0%, 100%': { opacity: '0.5' },
          '50%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
