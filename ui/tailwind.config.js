/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          from: "#03061A",
          to: "#070D2E",
        },
        neon: {
          cyan: "#01B5E2",
          blue: "#0075FF",
          pink: "#FF0080",
          green: "#2DD4BF",
          amber: "#FFB547",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      animation: {
        "spin-slow": "spin 2s linear infinite",
      },
    },
  },
  plugins: [],
};
