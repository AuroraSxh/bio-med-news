import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        apple: {
          black: "#000000",
          gray: "#f5f5f7",
          text: "#1d1d1f",
          blue: "#0071e3",
          link: "#0066cc",
          linkDark: "#2997ff",
          darkSurface1: "#272729",
          darkSurface2: "#2f2f32",
          darkSurface3: "#28282a",
        },
      },
      fontFamily: {
        display: [
          '"SF Pro Display"',
          '"SF Pro Icons"',
          '"Helvetica Neue"',
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        text: [
          '"SF Pro Text"',
          '"SF Pro Icons"',
          '"Helvetica Neue"',
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        apple: "0 5px 30px 3px rgba(0,0,0,0.22)",
      },
      borderRadius: {
        pill: "980px",
      },
      transitionTimingFunction: {
        apple: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
