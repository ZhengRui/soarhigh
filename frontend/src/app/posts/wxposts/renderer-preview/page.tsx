import type { Metadata } from 'next';

import { WxPostRendererShowcase } from './WxPostRendererShowcase';

export const metadata: Metadata = {
  title: 'WXPost Renderer Lab - SoarHigh',
  description: 'Fixture-driven preview for the production WXPost renderer.',
  robots: {
    index: false,
    follow: false,
  },
};

export default function WxPostRendererPreviewPage() {
  return <WxPostRendererShowcase />;
}
