import type {
  WxPostAppearance,
  WxPostLayout,
  WxPostPalette,
  WxPostPresentation,
  WxPostTypeface,
} from '../types';

export interface PresentationTokens {
  background: string;
  text: string;
  muted: string;
  accent: string;
  accentSecondary: string;
  soft: string;
  border: string;
  titleFont: string;
  bodyFont: string;
}

const PALETTES: Record<
  WxPostPalette,
  Record<WxPostAppearance, Omit<PresentationTokens, 'titleFont' | 'bodyFont'>>
> = {
  'brand-blue': {
    light: {
      background: '#ffffff',
      text: '#111827',
      muted: '#5f6b7a',
      accent: '#2563eb',
      accentSecondary: '#7c3aed',
      soft: '#eef2ff',
      border: '#dbe3f3',
    },
    dark: {
      background: '#10131a',
      text: '#f3f4f6',
      muted: '#aeb7c5',
      accent: '#60a5fa',
      accentSecondary: '#a78bfa',
      soft: '#1c2332',
      border: '#30394b',
    },
  },
  'paper-neutral': {
    light: {
      background: '#f8f6f0',
      text: '#25231f',
      muted: '#706b61',
      accent: '#2d2b27',
      accentSecondary: '#9b9285',
      soft: '#efebe1',
      border: '#c9c1b5',
    },
    dark: {
      background: '#1b1a17',
      text: '#f0ede4',
      muted: '#b9b2a5',
      accent: '#e2ddd2',
      accentSecondary: '#9b9285',
      soft: '#2a2722',
      border: '#514c43',
    },
  },
  'warm-terracotta': {
    light: {
      background: '#fffaf2',
      text: '#3d2d27',
      muted: '#80685d',
      accent: '#d8653b',
      accentSecondary: '#e9a23b',
      soft: '#fff0dd',
      border: '#e6c9b7',
    },
    dark: {
      background: '#211612',
      text: '#fff1e7',
      muted: '#c9a99a',
      accent: '#fb8b61',
      accentSecondary: '#f6bd60',
      soft: '#34231c',
      border: '#5c3c30',
    },
  },
};

const TYPEFACES: Record<
  WxPostTypeface,
  Pick<PresentationTokens, 'titleFont' | 'bodyFont'>
> = {
  'modern-sans': {
    titleFont:
      '"Avenir Next","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif',
    bodyFont:
      '"Avenir Next","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif',
  },
  'editorial-serif': {
    titleFont:
      'Baskerville,"Iowan Old Style","Palatino Linotype","Book Antiqua",Georgia,serif',
    bodyFont:
      '"Iowan Old Style","Palatino Linotype","Book Antiqua",Georgia,"Times New Roman",serif',
  },
  'humanist-mix': {
    titleFont: 'Charter,"Bitstream Charter","Sitka Text",Cambria,Georgia,serif',
    bodyFont:
      '"Avenir Next","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif',
  },
};

export function presentationTokens(
  presentation: WxPostPresentation
): PresentationTokens {
  return {
    ...PALETTES[presentation.palette][presentation.appearance],
    ...TYPEFACES[presentation.typeface],
  };
}

export function layoutWidth(layout: WxPostLayout) {
  switch (layout) {
    case 'brand-default':
      return '736px';
    case 'field-notes':
      return '768px';
    case 'editorial-feature':
      return '816px';
  }
}

export function layoutModuleInset(layout: WxPostLayout) {
  return layout === 'field-notes' ? '18px' : '0';
}
