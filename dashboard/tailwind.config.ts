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
        // Premium Dark Security Palette — Black & White Focus
        mag: {
          // Background layers — white/light
          bg: '#FFFFFF',
          panel: '#F9FAFB',
          surface: '#F3F4F6',
          border: '#E5E7EB',
          'border-bright': '#D1D5DB',

          // Primary — Dark (CTAs, emphasis)
          primary: '#111827',
          'primary-dim': '#374151',
          'primary-glow': 'rgba(17, 24, 39, 0.08)',
          'primary-bright': '#111827',

          // Accent — Bright Green for positive states
          accent: '#10B981',
          'accent-dim': '#059669',
          'accent-glow': 'rgba(16, 185, 129, 0.15)',

          // Danger — Vivid Red
          danger: '#EF4444',
          'danger-dim': '#DC2626',
          'danger-glow': 'rgba(239, 68, 68, 0.15)',

          // Warning — Amber
          warning: '#F59E0B',
          'warning-dim': '#D97706',
          'warning-glow': 'rgba(245, 158, 11, 0.15)',

          // Secondary — Gray
          secondary: '#6B7280',
          'secondary-dim': '#4B5563',
          'secondary-glow': 'rgba(107, 114, 128, 0.12)',

          // Text — dark to soft gray
          text: '#111827',
          'text-dim': '#6B7280',
          'text-bright': '#111827',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"SF Mono"', '"Share Tech Mono"', 'monospace'],
        sans: ['"Inter"', '"SF Pro"', 'system-ui', 'sans-serif'],
        display: ['"Inter"', '"SF Pro"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'mag-glow': '0 0 24px rgba(255, 255, 255, 0.08)',
        'mag-glow-strong': '0 0 36px rgba(255, 255, 255, 0.12)',
        'mag-accent': '0 0 20px rgba(16, 185, 129, 0.1)',
        'mag-danger': '0 0 20px rgba(239, 68, 68, 0.1)',
        'mag-panel': '0 4px 32px rgba(0, 0, 0, 0.4)',
        'mag-card': '0 2px 16px rgba(0, 0, 0, 0.3)',
        'mag-inset': 'inset 0 1px 0 rgba(255,255,255,0.04)',
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'ping-slow': 'ping 2s cubic-bezier(0, 0, 0.2, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.4s ease-out',
        'slide-in-right': 'slideInRight 0.3s ease-out',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'scan': 'scan 4s ease-in-out infinite',
        'path-draw': 'pathDraw 2s ease-out forwards',
        'm-glow': 'mGlow 3s ease-in-out infinite',
        'scan-line': 'scanningLine 3s ease-in-out infinite',
        'data-pulse': 'dataPulse 4s ease-in-out infinite',
        'fade-slide': 'fadeSlideUp 0.4s ease-out forwards',
        'data-flow': 'dataFlow 2s linear infinite',
        'shake': 'shake 0.4s ease-in-out',
        'float': 'floatParticle 6s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        glow: {
          '0%': { opacity: '0.5' },
          '100%': { opacity: '1' },
        },
        scan: {
          '0%, 100%': { transform: 'translateY(-100%)' },
          '50%': { transform: 'translateY(100%)' },
        },
        pathDraw: {
          '0%': { strokeDashoffset: '1000' },
          '100%': { strokeDashoffset: '0' },
        },
        mGlow: {
          '0%, 100%': { opacity: '0.4', transform: 'scale(1)' },
          '50%': { opacity: '0.8', transform: 'scale(1.02)' },
        },
        scanningLine: {
          '0%': { top: '0%', opacity: '0' },
          '5%': { opacity: '1' },
          '90%': { opacity: '1' },
          '100%': { top: '100%', opacity: '0' },
        },
        dataPulse: {
          '0%, 100%': { borderColor: 'rgba(255,255,255,0.06)' },
          '50%': { borderColor: 'rgba(255,255,255,0.12)' },
        },
        fadeSlideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        dataFlow: {
          '0%': { backgroundPosition: '200% center' },
          '100%': { backgroundPosition: '-200% center' },
        },
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '10%, 30%, 50%, 70%, 90%': { transform: 'translateX(-2px)' },
          '20%, 40%, 60%, 80%': { transform: 'translateX(2px)' },
        },
        floatParticle: {
          '0%, 100%': { transform: 'translateY(0) translateX(0)', opacity: '0' },
          '10%': { opacity: '0.3' },
          '90%': { opacity: '0.3' },
          '100%': { transform: 'translateY(-100px) translateX(20px)', opacity: '0' },
        },
      },
      backgroundImage: {
        'grid-pattern': `linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
                         linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px)`,
        'radial-glow': 'radial-gradient(ellipse at center, rgba(255, 255, 255, 0.03) 0%, transparent 70%)',
      },
      backgroundSize: {
        'grid-20': '20px 20px',
      },
    },
  },
  plugins: [],
};

export default config;
