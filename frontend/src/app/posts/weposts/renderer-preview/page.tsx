import type { Metadata } from 'next';

import { WePostRendererShowcase } from './WePostRendererShowcase';

export const metadata: Metadata = {
  title: 'WePost Renderer Lab - SoarHigh',
  description: 'Fixture-driven preview for the production WePost renderer.',
  robots: {
    index: false,
    follow: false,
  },
};

export default function WePostRendererPreviewPage() {
  return <WePostRendererShowcase />;
}
