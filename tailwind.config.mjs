/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
  theme: {
    extend: {
      colors: {
        paper: "oklch(0.975 0.007 106.521)",
        surface: "oklch(0.955 0.009 106.5)",
        muted: "oklch(0.93 0.011 106.5)",
        line: "oklch(0.905 0.012 106.5)",
        ink: {
          DEFAULT: "oklch(0.32 0.026 195.945)",
          muted: "oklch(0.48 0.022 196)",
        },
        primary: {
          DEFAULT: "oklch(0.56 0.16 34.263)",
          foreground: "oklch(0.975 0.007 106.521)",
        },
        coral: "#e56b4f",
        teal: "oklch(0.527 0.085 193.827)",
        ring: "oklch(0.24 0.04 194)",
      },
      fontFamily: {
        sans: ['"DM Sans"', '"Noto Sans TC"', "sans-serif"],
      },
      typography: ({ theme }) => ({
        hina: {
          css: {
            "--tw-prose-body": theme("colors.ink.DEFAULT"),
            "--tw-prose-headings": theme("colors.ink.DEFAULT"),
            "--tw-prose-links": theme("colors.primary.DEFAULT"),
            "--tw-prose-bold": theme("colors.ink.DEFAULT"),
            "--tw-prose-bullets": theme("colors.coral"),
            "--tw-prose-counters": theme("colors.ink.muted"),
            "--tw-prose-hr": theme("colors.line"),
            "--tw-prose-quotes": theme("colors.ink.DEFAULT"),
            "--tw-prose-quote-borders": theme("colors.coral"),
            "--tw-prose-code": theme("colors.ink.DEFAULT"),
          },
        },
      }),
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
