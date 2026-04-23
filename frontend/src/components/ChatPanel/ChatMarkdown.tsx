'use client';

import dynamic from 'next/dynamic';

// Same pattern as src/components/posts/MarkdownRenderer.tsx — dynamic import
// to keep @uiw/react-md-editor (bundle-heavy) out of the initial page load.
// Module is cached after first render so subsequent bubbles don't re-flash.
const MDPreview = dynamic(
  () => import('@uiw/react-md-editor').then((mod) => mod.default.Markdown),
  { ssr: false, loading: () => null }
);

export function ChatMarkdown({ source }: { source: string }) {
  return (
    <div className='chat-markdown' data-color-mode='light'>
      <MDPreview source={source} />
    </div>
  );
}
