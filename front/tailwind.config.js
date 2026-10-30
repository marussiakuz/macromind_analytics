/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#4D966F',
          hover: '#3D7D5C',
          light: '#1A3D2A',
        },
        secondary: {
          DEFAULT: '#68B589',
          hover: '#56977A',
          light: '#1A3A28',
        },
        surface: '#1A1A1A',
        card: '#2C2C2C',
        'card-border': '#3C3C3C',
        text: {
          main: '#F0F0F0',
          secondary: '#8A8A8E',
          light: '#636366',
        },
      },
      borderRadius: {
        xl: '12px',
        '2xl': '20px',
        '3xl': '28px',
      },
      boxShadow: {
        soft: '0 4px 24px rgba(0, 0, 0, 0.35)',
        medium: '0 8px 32px rgba(0, 0, 0, 0.45)',
        large: '0 12px 48px rgba(0, 0, 0, 0.55)',
      },
    },
  },
  plugins: [],
};
