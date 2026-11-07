/**
 * Semantic colours resolve to CSS variables holding RGB triplets (defined in THEME_CSS inside App.jsx).
 * One class (e.g. `bg-card`, `text-hint`, `bg-accent/10`) therefore works in light, dark and any Telegram theme.
 */
const rgb = (v) => `rgb(var(${v}) / <alpha-value>)`;

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: rgb('--bg'), card: rgb('--card'), line: rgb('--line'), fill: rgb('--fill'),
        tx: rgb('--tx'), hint: rgb('--hint'),
        accent: rgb('--accent'), 'accent-fg': rgb('--accent-fg'),
        danger: rgb('--danger'), ok: rgb('--ok'),
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', 'Roboto', '"Segoe UI"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
