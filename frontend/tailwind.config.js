/** Design tokens for the storefront. Every colour used in the UI comes from here. */
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#222831", // header, primary text, icon strokes
        page: "#FAF8F1", // page background
        line: "#E4DFD3", // 1px card / tile borders
        amber: { DEFAULT: "#C58940", light: "#E5BA73" }, // primary button + hover
        cream: "#FAEAB1", // small badges, icon fills
        tile: "#F1EDE3", // image fallback tile
        muted: { DEFAULT: "#6B7079", strong: "#4A4F57" },
        ok: { DEFAULT: "#2F855A", bg: "#E7F2EC" },
        bad: { DEFAULT: "#C53030", bg: "#FBEAEA" },
        retry: { DEFAULT: "#8A5A1E", bg: "#FDF8EC" },
        pending: "#8A8F98",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: { card: "12px", control: "8px" },
      maxWidth: { content: "1120px" },
      boxShadow: { none: "none" },
    },
  },
  plugins: [],
};
