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
        // Premium Magenta Dark Palette — bright, bold, military-grade
        mag: {
          // Background layers
          bg: '#0a0a0f',
          panel: '#111118',
          surface: '#1a1a24',
          border: '#2a2a38',
          'border-bright': '#3a3a50',

          // Primary — Magenta / Hot Pink
          primary: '#E91E8C',
          'primary-dim': '#C4176E',
          'primary-glow': 'rgba(233, 30, 140, 0.15)',

          // Secondary — Electric Cyan
          secondary: '#06B6D4',
          'secondary-dim': '#0891B2',
          'secondary-glow': 'rgba(6, 182, 212, 0.15)',

          // Accent — Bright Green for positive states
          accent: '#22C55E',
          'accent-dim': '#16A34A',
          'accent-glow': 'rgba(34, 197, 94, 0.15)',

          // Danger — Vivid Red
          danger: '#EF4444',
          'danger-dim': '#DC2626',
          'danger-glow': 'rgba(239, 68, 68, 0.15)',

          // Warning — Amber
          warning: '#F59E0B',
          'warning-dim': '#D97706',
          'warning-glow': 'rgba(245, 158, 11, 0.15)',

          // Text — bright & crisp
          text: '#FFFFFF',
          'text-dim': '#C0C4D0',
          'text-bright': '#FFFFFF',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"SF Mono"', '"Share Tech Mono"', 'monospace'],
        sans: ['"Inter"', '"SF Pro"', 'system-ui', 'sans-serif'],
        display: ['"Inter"', '"SF Pro"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'mag-glow': '0 0 24px rgba(233, 30, 140, 0.12)',
        'mag-glow-strong': '0 0 36px rgba(233, 30, 140, 0.2)',
        'mag-accent': '0 0 20px rgba(34, 197, 94, 0.1)',
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
      },
      backgroundImage: {
        'grid-pattern': `linear-gradient(rgba(233, 30, 140, 0.02) 1px, transparent 1px),
                         linear-gradient(90deg, rgba(233, 30, 140, 0.02) 1px, transparent 1px)`,
        'radial-glow': 'radial-gradient(ellipse at center, rgba(233, 30, 140, 0.04) 0%, transparent 70%)',
      },
      backgroundSize: {
        'grid-20': '20px 20px',
      },
    },
  },
  plugins: [],
};

export default config;
