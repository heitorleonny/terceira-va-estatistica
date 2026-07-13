/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Camadas de fundo (near-black, quente)
        ink: {
          900: "#09090a",
          850: "#0e0e10",
          800: "#141416",
          750: "#191a1d",
          700: "#212226",
        },
        line: {
          DEFAULT: "#26262b",
          strong: "#37373f",
        },
        // Texto — papel quente de terminal editorial
        paper: {
          DEFAULT: "#ECEAE1",
          dim: "#A7A59B",
          mute: "#6E6C63",
        },
        // Acento âmbar (assinatura de terminal financeiro)
        amber: {
          DEFAULT: "#E8A33D",
          bright: "#F6BC55",
          deep: "#B97E27",
        },
        up: { DEFAULT: "#48C06B", dim: "#2e6b41" },
        down: { DEFAULT: "#E5484D", dim: "#7a2b2e" },
        azure: { DEFAULT: "#78ABC4", dim: "#3d5a68" },
      },
      fontFamily: {
        display: ['"Fraunces Variable"', "Georgia", "serif"],
        sans: ['"Inter Variable"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      letterSpacing: {
        micro: "0.14em",
      },
      fontSize: {
        micro: ["0.66rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.02) inset, 0 8px 30px -12px rgba(0,0,0,0.7)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: {
          "0%,49%": { opacity: "1" },
          "50%,100%": { opacity: "0.15" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s ease-out both",
        blink: "blink 1.1s step-end infinite",
      },
    },
  },
  plugins: [],
};
