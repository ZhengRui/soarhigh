import type { Config } from 'tailwindcss';
import defaultTheme from 'tailwindcss/defaultTheme';
import typography from '@tailwindcss/typography';

export default {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
      },
      screens: {
        '4xs': '240px',
        '3xs': '320px',
        '2xs': '360px',
        xs: '480px',
        ...defaultTheme.screens,
      },
      typography: {
        DEFAULT: {
          css: {
            maxWidth: 'none',
            color: 'var(--tw-prose-body)',
            a: {
              color: 'var(--tw-prose-links)',
              textDecoration: 'underline',
              fontWeight: '500',
            },
            h1: {
              marginTop: '1.5em',
            },
            h2: {
              marginTop: '1.5em',
            },
            h3: {
              marginTop: '1.5em',
            },
          },
        },
      },
    },
  },
  plugins: [typography],
} satisfies Config;
