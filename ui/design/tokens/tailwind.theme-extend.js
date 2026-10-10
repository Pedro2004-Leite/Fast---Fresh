// Extensão do tema Tailwind com os tokens do design (tokens.json). Cola em tailwind.config.js > theme.extend.
module.exports = {
  colors: {
    ground: '#D9DBDC',
    sheet: '#F5F6F6',
    chip: '#E5E7E8',
    track: { segmented: '#C7CACB', bar: '#DADCDD' },
    ink: { DEFAULT: '#27282A', secondary: '#585B5E', sub: '#3A3C3E', on: '#F5F6F6' },
    cell: '#D3D5D6',
    spine: { DEFAULT: '#B4B7B9', ink: '#2F3234' },
    sev: {
      critical: { DEFAULT: '#D8322B', ink: '#FFFFFF' },
      high: { DEFAULT: '#F28C1F', ink: '#27282A' },
      medium: { DEFAULT: '#FFD21F', ink: '#27282A' },
    },
  },
  fontFamily: {
    sans: ["'Hanken Grotesk'", 'system-ui', 'sans-serif'],
    mono: ["'IBM Plex Mono'", 'monospace'],
  },
  borderRadius: { sheet: '24px', card: '20px', chip: '14px', badge: '12px', cell: '2px' },
};
