/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#f8f9fa",
        surfaceContainerLow: "#f2f3f4",
        surfaceContainerLowest: "#ffffff",
        surfaceContainerHigh: "#eceff1",
        surfaceContainerHighest: "#e4e7ea",
        onSurface: "#191c1d",
        onSurfaceVariant: "#5d4039",
        primary: "#b41f00",
        primaryContainer: "#df2d06",
        secondary: "#006c49",
        tertiary: "#825100",
        outlineVariant: "#e6bdb5",
      },
      fontFamily: {
        heading: ["Manrope", "sans-serif"],
        body: ["Inter", "sans-serif"],
      },
      boxShadow: {
        ambient: "0 10px 32px rgba(25, 28, 29, 0.04)",
      },
      borderRadius: {
        "chat-user": "16px 16px 4px 16px",
        "chat-ai": "16px 16px 16px 4px",
      },
    },
  },
  plugins: [],
};
