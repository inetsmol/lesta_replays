/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './replays/templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // Custom color palette from site.css
        dark: {
          900: '#0b0b0b',  // --bg
          800: '#141414',  // --panel
          700: '#1a1a1a',  // --panel-2
          600: '#292929',  // --border
        },
        text: {
          DEFAULT: '#e6e6e6',  // --text
          muted: '#b6b6b6',    // --muted
        },
        accent: {
          DEFAULT: '#c0392b',  // --accent
          500: '#c0392b',
          600: '#e74c3c',      // --accent-2
        },
        gold: '#f7c76b',       // --gold
        success: '#27ae60',    // --success
        focus: '#3b82f6',      // --focus
      },
      boxShadow: {
        'custom': '0 6px 18px rgba(0, 0, 0, .35)',  // --shadow
      },
      borderRadius: {
        'custom': '12px',     // --radius
        'custom-sm': '8px',   // --radius-sm
      },
      screens: {
        'xs': '480px',
        'sm': '640px',
        'md': '768px',
        'lg': '1024px',
        'xl': '1280px',
        '2xl': '1600px',
      },
      maxWidth: {
        'content': '1003px',    // .container-center
        'site': '1600px',       // #content
        'footer': '1200px',     // .footer
      },
      minWidth: {
        'content': '1003px',    // .container-center для detail страницы
      },
    },
  },
  plugins: [],
}
