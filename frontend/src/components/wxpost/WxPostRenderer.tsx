'use client';

/* eslint-disable @next/next/no-img-element */

import { useMemo, useRef } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { remarkKeyPoints } from './remarkKeyPoints';
import type {
  WxPostBodyNode,
  WxPostDirectiveNode,
  WxPostLayout,
  WxPostMediaAsset,
  WxPostPresentation,
  WxPostPreviewSize,
  WxPostRenderDocument,
  WxPostTypeface,
} from './types';

const PALETTE_CLASSES = {
  'brand-blue':
    '[--palette-bg-light:#fff] [--palette-text-light:#111827] [--palette-muted-light:#5f6b7a] [--palette-accent-light:#2563eb] [--palette-accent-2-light:#7c3aed] [--palette-soft-light:#eef2ff] [--palette-border-light:#dbe3f3] [--palette-bg-dark:#10131a] [--palette-text-dark:#f3f4f6] [--palette-muted-dark:#aeb7c5] [--palette-accent-dark:#60a5fa] [--palette-accent-2-dark:#a78bfa] [--palette-soft-dark:#1c2332] [--palette-border-dark:#30394b]',
  'paper-neutral':
    '[--palette-bg-light:#f8f6f0] [--palette-text-light:#25231f] [--palette-muted-light:#706b61] [--palette-accent-light:#2d2b27] [--palette-accent-2-light:#9b9285] [--palette-soft-light:#efebe1] [--palette-border-light:#c9c1b5] [--palette-bg-dark:#1b1a17] [--palette-text-dark:#f0ede4] [--palette-muted-dark:#b9b2a5] [--palette-accent-dark:#e2ddd2] [--palette-accent-2-dark:#9b9285] [--palette-soft-dark:#2a2722] [--palette-border-dark:#514c43]',
  'warm-terracotta':
    '[--palette-bg-light:#fffaf2] [--palette-text-light:#3d2d27] [--palette-muted-light:#80685d] [--palette-accent-light:#d8653b] [--palette-accent-2-light:#e9a23b] [--palette-soft-light:#fff0dd] [--palette-border-light:#e6c9b7] [--palette-bg-dark:#211612] [--palette-text-dark:#fff1e7] [--palette-muted-dark:#c9a99a] [--palette-accent-dark:#fb8b61] [--palette-accent-2-dark:#f6bd60] [--palette-soft-dark:#34231c] [--palette-border-dark:#5c3c30]',
} as const;

const APPEARANCE_CLASSES = {
  light:
    '[--article-bg:var(--palette-bg-light)] [--article-text:var(--palette-text-light)] [--article-muted:var(--palette-muted-light)] [--article-accent:var(--palette-accent-light)] [--article-accent-2:var(--palette-accent-2-light)] [--article-soft:var(--palette-soft-light)] [--article-border:var(--palette-border-light)]',
  dark: '[--article-bg:var(--palette-bg-dark)] [--article-text:var(--palette-text-dark)] [--article-muted:var(--palette-muted-dark)] [--article-accent:var(--palette-accent-dark)] [--article-accent-2:var(--palette-accent-2-dark)] [--article-soft:var(--palette-soft-dark)] [--article-border:var(--palette-border-dark)] [color-scheme:dark]',
} as const;

const BODY_FONT_CLASSES: Record<WxPostTypeface, string> = {
  'modern-sans':
    "font-['Avenir_Next','Segoe_UI',Roboto,'Helvetica_Neue',Arial,sans-serif]",
  'editorial-serif':
    "font-['Iowan_Old_Style','Palatino_Linotype','Book_Antiqua',Georgia,'Times_New_Roman',serif]",
  'humanist-mix':
    "font-['Avenir_Next','Segoe_UI',Roboto,'Helvetica_Neue',Arial,sans-serif]",
};

const TITLE_FONT_CLASSES: Record<WxPostTypeface, string> = {
  'modern-sans':
    "font-['Avenir_Next','Segoe_UI',Roboto,'Helvetica_Neue',Arial,sans-serif]",
  'editorial-serif':
    "font-[Baskerville,'Iowan_Old_Style','Palatino_Linotype','Book_Antiqua',Georgia,serif]",
  'humanist-mix':
    "font-[Charter,'Bitstream_Charter','Sitka_Text',Cambria,Georgia,serif]",
};

const MODULE_CLASS = 'grid min-w-0 gap-4';
const MODULE_LABEL_CLASS =
  'text-[0.74rem] font-semibold uppercase tracking-[0.12em] text-[var(--article-muted)]';
const CAPTION_CLASS = 'm-0 text-[var(--article-muted)]';

interface WxPostRendererProps {
  article: WxPostRenderDocument;
  presentation?: WxPostPresentation;
  previewSize?: WxPostPreviewSize;
  contextLabel?: string;
  className?: string;
}

interface DirectiveProps {
  node: WxPostDirectiveNode;
  mediaById: Map<string, WxPostMediaAsset>;
  layout: WxPostLayout;
  previewSize: WxPostPreviewSize;
  titleFontClass: string;
}

function MediaFigure({
  media,
  fallback,
}: {
  media?: WxPostMediaAsset;
  fallback: string;
}) {
  return (
    <div className='relative min-h-48 overflow-hidden border border-[var(--article-border)] bg-[var(--article-soft)]'>
      {media?.kind === 'image' ? (
        <img
          className='block h-full min-h-[inherit] w-full object-cover'
          src={media.sourceUrl}
          alt={media.description}
          loading='lazy'
        />
      ) : (
        <span className='grid min-h-[inherit] place-items-center p-4 text-center text-[var(--article-muted)]'>
          {fallback}
        </span>
      )}
    </div>
  );
}

function GalleryBlock({
  node,
  mediaById,
  previewSize,
  titleFontClass,
}: {
  node: Extract<WxPostDirectiveNode, { name: 'gallery' }>;
  mediaById: Map<string, WxPostMediaAsset>;
  previewSize: WxPostPreviewSize;
  titleFontClass: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const items = node.payload.items
    .map((id) => mediaById.get(id))
    .filter((item): item is WxPostMediaAsset => Boolean(item));
  const isMobilePreview = previewSize === 'mobile-390';

  const move = (direction: -1 | 1) => {
    const track = trackRef.current;
    if (!track) return;
    track.scrollBy({
      left: direction * Math.max(track.clientWidth * 0.84, 240),
      behavior: 'smooth',
    });
  };

  return (
    <section className={MODULE_CLASS} data-testid='directive-gallery'>
      <div className='flex flex-wrap items-center justify-between gap-3'>
        <div>
          <span className={MODULE_LABEL_CLASS}>Gallery</span>
          {node.payload.caption && (
            <h2
              className={`m-0 text-[clamp(1.4rem,3vw,1.8rem)] leading-[1.18] tracking-[-0.025em] text-[var(--article-text)] ${titleFontClass}`}
            >
              {node.payload.caption}
            </h2>
          )}
        </div>
        <div className='flex gap-[0.4rem]'>
          <button
            className='inline-grid h-8 w-8 cursor-pointer place-items-center rounded-full border border-[var(--article-border)] bg-transparent text-[var(--article-text)] hover:border-[var(--article-accent)] focus-visible:border-[var(--article-accent)] focus-visible:outline-none'
            type='button'
            aria-label='Previous gallery image'
            onClick={() => move(-1)}
          >
            ←
          </button>
          <button
            className='inline-grid h-8 w-8 cursor-pointer place-items-center rounded-full border border-[var(--article-border)] bg-transparent text-[var(--article-text)] hover:border-[var(--article-accent)] focus-visible:border-[var(--article-accent)] focus-visible:outline-none'
            type='button'
            aria-label='Next gallery image'
            onClick={() => move(1)}
          >
            →
          </button>
        </div>
      </div>
      <div
        className={
          isMobilePreview
            ? 'scrollbar-hide flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-smooth pb-[0.4rem] [overscroll-behavior-inline:contain]'
            : 'grid grid-cols-2 gap-3 max-[540px]:flex max-[540px]:snap-x max-[540px]:snap-mandatory max-[540px]:overflow-x-auto max-[540px]:scroll-smooth max-[540px]:pb-[0.4rem]'
        }
        ref={trackRef}
        data-testid='gallery-track'
      >
        {items.map((media) => (
          <figure
            className={`m-0 min-w-0 ${
              isMobilePreview
                ? 'basis-[84%] shrink-0 snap-start'
                : 'max-[540px]:basis-[84%] max-[540px]:shrink-0 max-[540px]:snap-start'
            }`}
            key={media.id}
          >
            <MediaFigure media={media} fallback={`Missing image ${media.id}`} />
            <figcaption className='mt-[0.45rem] text-[0.82rem] leading-6 text-[var(--article-muted)]'>
              {media.description}
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

function DirectiveBlock({
  node,
  mediaById,
  layout,
  previewSize,
  titleFontClass,
}: DirectiveProps) {
  const isMobilePreview = previewSize === 'mobile-390';
  const moduleTitleClass = `m-0 text-[clamp(1.4rem,3vw,1.8rem)] leading-[1.18] tracking-[-0.025em] text-[var(--article-text)] ${titleFontClass}`;

  switch (node.name) {
    case 'gallery':
      return (
        <GalleryBlock
          node={node}
          mediaById={mediaById}
          previewSize={previewSize}
          titleFontClass={titleFontClass}
        />
      );

    case 'video': {
      const media = mediaById.get(node.payload.media);
      return (
        <section className={MODULE_CLASS} data-testid='directive-video'>
          <div className='flex flex-wrap items-baseline justify-between gap-3'>
            <span className={MODULE_LABEL_CLASS}>Video</span>
            {node.payload.caption && (
              <span className={CAPTION_CLASS}>{node.payload.caption}</span>
            )}
          </div>
          {media?.kind === 'video' ? (
            <div className='overflow-hidden border border-[var(--article-border)] bg-black'>
              <video
                className='block aspect-video max-h-[32rem] w-full object-cover'
                controls
                preload='metadata'
                poster={media.posterUrl ?? undefined}
                aria-label={media.description}
                data-testid='wxpost-video'
              >
                <source src={media.sourceUrl} />
                Your browser does not support embedded video.
              </video>
            </div>
          ) : (
            <MediaFigure fallback={`Missing video ${node.payload.media}`} />
          )}
          {media && <p className={CAPTION_CLASS}>{media.description}</p>}
        </section>
      );
    }

    case 'takeaway':
      return (
        <aside
          className={`${MODULE_CLASS} ${
            layout === 'editorial-feature'
              ? 'border-y border-[var(--article-border)] px-0 py-5 text-center'
              : 'border-l-[3px] border-[var(--article-accent)] pl-4'
          }`}
          data-testid='directive-takeaway'
        >
          <span className={MODULE_LABEL_CLASS}>Takeaway</span>
          {node.payload.title && (
            <h2 className={moduleTitleClass}>{node.payload.title}</h2>
          )}
          <p className='m-0'>{node.payload.text}</p>
        </aside>
      );

    case 'person': {
      const media = node.payload.media
        ? mediaById.get(node.payload.media)
        : undefined;
      return (
        <section className={MODULE_CLASS} data-testid='directive-person'>
          <span className={MODULE_LABEL_CLASS}>Profile</span>
          <div
            className={`grid items-start gap-5 ${
              isMobilePreview
                ? 'grid-cols-1'
                : 'grid-cols-[minmax(9rem,1fr)_2fr] max-[540px]:grid-cols-1'
            }`}
          >
            <MediaFigure
              media={media}
              fallback={`Portrait of ${node.payload.name}`}
            />
            <div className='grid gap-[0.8rem] [&_p]:m-0'>
              <h2
                className={`m-0 leading-[1.18] tracking-[-0.025em] text-[var(--article-text)] ${titleFontClass}`}
              >
                {node.payload.name}
              </h2>
              {node.payload.role && (
                <p className={CAPTION_CLASS}>{node.payload.role}</p>
              )}
              {node.payload.summary && <p>{node.payload.summary}</p>}
              {node.payload.quote && (
                <blockquote className='m-0 border-l-2 border-[var(--article-accent)] pl-[0.8rem] text-[var(--article-muted)]'>
                  “{node.payload.quote}”
                </blockquote>
              )}
            </div>
          </div>
        </section>
      );
    }

    case 'info-grid':
      return (
        <section className={MODULE_CLASS} data-testid='directive-info-grid'>
          <span className={MODULE_LABEL_CLASS}>At a glance</span>
          {node.payload.title && (
            <h2 className={moduleTitleClass}>{node.payload.title}</h2>
          )}
          <div
            className={`grid gap-4 border-y border-[var(--article-border)] py-4 ${
              isMobilePreview
                ? 'grid-cols-1'
                : 'grid-cols-3 max-[540px]:grid-cols-1'
            }`}
          >
            {node.payload.items.map((item) => (
              <div className='grid gap-1' key={`${item.label}-${item.value}`}>
                <span className={CAPTION_CLASS}>{item.label}</span>
                <strong className='text-[var(--article-text)]'>
                  {item.value}
                </strong>
              </div>
            ))}
          </div>
        </section>
      );

    case 'timeline':
      return (
        <section className={MODULE_CLASS} data-testid='directive-timeline'>
          <span className={MODULE_LABEL_CLASS}>Timeline</span>
          {node.payload.title && (
            <h2 className={moduleTitleClass}>{node.payload.title}</h2>
          )}
          <div className='grid border-l border-[var(--article-border)] pl-4'>
            {node.payload.items.map((item, index) => (
              <div
                className={`grid gap-4 py-4 ${
                  isMobilePreview
                    ? 'grid-cols-1 gap-y-[0.35rem]'
                    : 'grid-cols-[minmax(4.5rem,auto)_1fr] max-[540px]:grid-cols-1 max-[540px]:gap-y-[0.35rem]'
                } ${index > 0 ? 'border-t border-[var(--article-border)]' : ''}`}
                key={`${item.label}-${item.title}`}
              >
                <strong className={MODULE_LABEL_CLASS}>{item.label}</strong>
                <div className='grid gap-[0.35rem] [&_p]:m-0'>
                  <strong>{item.title}</strong>
                  {item.description && <p>{item.description}</p>}
                </div>
              </div>
            ))}
          </div>
        </section>
      );

    case 'pull-quote':
      return (
        <figure
          className={`${MODULE_CLASS} border-y border-[var(--article-border)] py-[1.35rem] text-center ${
            layout === 'editorial-feature' ? 'mx-auto w-[min(100%,34rem)]' : ''
          }`}
          data-testid='directive-pull-quote'
        >
          <blockquote
            className={`m-0 text-[clamp(1.45rem,4vw,2.15rem)] leading-[1.45] ${titleFontClass}`}
          >
            “{node.payload.text}”
          </blockquote>
          {node.payload.attribution && (
            <figcaption>
              <cite className='text-[0.85rem] not-italic text-[var(--article-muted)]'>
                — {node.payload.attribution}
              </cite>
            </figcaption>
          )}
        </figure>
      );
  }
}

function MarkdownBlock({
  node,
  layout,
  previewSize,
  titleFontClass,
}: {
  node: Extract<WxPostBodyNode, { kind: 'markdown' }>;
  layout: WxPostLayout;
  previewSize: WxPostPreviewSize;
  titleFontClass: string;
}) {
  const normalizedSource = node.source.trimStart();
  const leadingHeading = normalizedSource.match(
    /^(#{2,3})[ \t]+(.+?)(?:\r?\n|$)/
  );
  const hasLeadingHeading = Boolean(leadingHeading);
  const headingSource = leadingHeading?.[0].trim() ?? '';
  const copySource = leadingHeading
    ? normalizedSource.slice(leadingHeading[0].length).trimStart()
    : '';
  const isMobilePreview = previewSize === 'mobile-390';
  const editorialSplit =
    layout === 'editorial-feature' && hasLeadingHeading && !isMobilePreview;
  const markdownComponents: Components = {
    h2: ({ children, ...props }) => (
      <h2 className={titleFontClass} {...props}>
        {children}
      </h2>
    ),
    h3: ({ children, ...props }) => (
      <h3 className={titleFontClass} {...props}>
        {children}
      </h3>
    ),
  };

  const markdownClass = [
    'text-[var(--article-text)]',
    '[&>:first-child]:mt-0 [&>:last-child]:mb-0',
    '[&_p]:mb-4 [&_p]:mt-0 [&_p]:text-[var(--article-text)]',
    '[&_li]:text-[var(--article-text)]',
    '[&_h2]:mb-4 [&_h2]:mt-0 [&_h2]:text-[clamp(1.65rem,4vw,2.2rem)] [&_h2]:leading-[1.3] [&_h2]:tracking-[-0.02em] [&_h2]:text-[var(--article-text)]',
    '[&_h3]:mb-4 [&_h3]:mt-0 [&_h3]:text-[1.3rem] [&_h3]:leading-[1.3] [&_h3]:tracking-[-0.02em] [&_h3]:text-[var(--article-text)]',
    '[&_a]:text-[var(--article-accent)] [&_a]:underline [&_a]:decoration-1 [&_a]:underline-offset-[0.2em]',
    '[&_blockquote]:mx-0 [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--article-accent)] [&_blockquote]:pl-4 [&_blockquote]:text-[var(--article-text)]',
    '[&_ul]:mb-4 [&_ul]:mt-0 [&_ul]:list-disc [&_ul]:pl-[1.4rem] [&_ol]:mb-4 [&_ol]:mt-0 [&_ol]:list-decimal [&_ol]:pl-[1.4rem]',
    '[&_code]:rounded-[0.2rem] [&_code]:bg-[var(--article-soft)] [&_code]:px-[0.35em] [&_code]:py-[0.15em] [&_code]:text-[var(--article-text)]',
    '[&_pre]:overflow-x-auto [&_pre]:border [&_pre]:border-[var(--article-border)] [&_pre]:bg-[var(--article-soft)] [&_pre]:p-4',
    '[&_.wxpost-key-point]:not-italic [&_.wxpost-key-point]:font-semibold [&_.wxpost-key-point]:underline [&_.wxpost-key-point]:decoration-[var(--article-accent)] [&_.wxpost-key-point]:decoration-2 [&_.wxpost-key-point]:underline-offset-4',
    layout === 'brand-default'
      ? '[&_h2]:border-b [&_h2]:border-[var(--article-border)] [&_h2]:pb-[0.65rem]'
      : '',
    layout === 'field-notes'
      ? `[&_h2]:before:mb-[0.35rem] [&_h2]:before:block [&_h2]:before:text-[0.68rem] [&_h2]:before:font-semibold [&_h2]:before:tracking-[0.12em] [&_h2]:before:text-[var(--article-muted)] [&_h2]:before:content-['FIELD_NOTE'] ${
          isMobilePreview ? '[&_h2]:before:hidden' : ''
        }`
      : '',
    editorialSplit
      ? 'grid grid-cols-[minmax(10rem,0.85fr)_minmax(0,2fr)] gap-x-6 gap-y-[0.85rem] max-[540px]:block'
      : '',
    layout === 'editorial-feature' && !hasLeadingHeading
      ? 'mx-auto max-w-[40rem]'
      : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <section
      className='min-w-0'
      data-leading-heading={hasLeadingHeading}
      data-source-line={node.line}
      data-testid='markdown-segment'
    >
      <div className={markdownClass}>
        {hasLeadingHeading ? (
          <>
            <div
              className={
                editorialSplit
                  ? `col-start-1 row-start-1 block max-[540px]:block [&_h2]:border-t-[3px] [&_h2]:border-[var(--article-accent)] [&_h2]:pt-3 ${titleFontClass}`
                  : 'contents'
              }
            >
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkKeyPoints]}
                components={markdownComponents}
              >
                {headingSource}
              </ReactMarkdown>
            </div>
            {copySource && (
              <div
                className={
                  editorialSplit
                    ? 'col-start-2 row-start-1 block max-[540px]:block [&>:first-child]:mt-0 [&>:last-child]:mb-0'
                    : 'contents'
                }
                data-wxpost-section-copy
              >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkKeyPoints]}
                  components={markdownComponents}
                >
                  {copySource}
                </ReactMarkdown>
              </div>
            )}
          </>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkKeyPoints]}
            components={markdownComponents}
          >
            {node.source}
          </ReactMarkdown>
        )}
      </div>
    </section>
  );
}

export function WxPostRenderer({
  article,
  presentation = article.presentation,
  previewSize = 'mobile-390',
  contextLabel,
  className = '',
}: WxPostRendererProps) {
  const mediaById = useMemo(
    () =>
      new Map(
        article.media
          .filter((media) => media.include)
          .map((media) => [media.id, media])
      ),
    [article.media]
  );

  const isMobilePreview = previewSize === 'mobile-390';
  const titleFontClass = TITLE_FONT_CLASSES[presentation.typeface];
  const articleClasses = [
    'box-border grid w-full gap-[clamp(1.75rem,4vw,2.75rem)] overflow-hidden border border-[var(--article-border)] bg-[var(--article-bg)] text-base leading-[1.85] text-[var(--article-text)] [box-shadow:0_1.5rem_4rem_rgb(15_23_42_/_12%)]',
    isMobilePreview ? 'px-4 pb-8 pt-[1.35rem]' : 'p-[clamp(2rem,5vw,3.5rem)]',
    PALETTE_CLASSES[presentation.palette],
    APPEARANCE_CLASSES[presentation.appearance],
    BODY_FONT_CLASSES[presentation.typeface],
  ].join(' ');

  const heroClasses = [
    'grid gap-4 border-b border-[var(--article-border)] py-6',
    presentation.palette === 'brand-blue'
      ? 'border-t-4 border-t-transparent [border-image:linear-gradient(90deg,var(--article-accent),var(--article-accent-2))_1]'
      : '',
    presentation.palette === 'warm-terracotta'
      ? 'border-t-4 border-t-[var(--article-accent)]'
      : '',
    presentation.layout === 'field-notes'
      ? isMobilePreview
        ? 'grid-cols-1 pt-0'
        : 'grid-cols-[5rem_minmax(0,1fr)] items-start gap-x-5 pt-0 max-[540px]:grid-cols-1'
      : '',
    presentation.layout === 'editorial-feature'
      ? isMobilePreview
        ? 'grid-cols-1'
        : 'grid-cols-[minmax(0,1.7fr)_minmax(12rem,1fr)] items-start gap-x-6 max-[540px]:grid-cols-1'
      : '',
  ]
    .filter(Boolean)
    .join(' ');

  const fieldNotesDesktop =
    presentation.layout === 'field-notes' && !isMobilePreview;
  const editorialDesktop =
    presentation.layout === 'editorial-feature' && !isMobilePreview;

  return (
    <div
      className={`mx-auto w-full ${
        isMobilePreview ? 'max-w-[390px]' : 'max-w-[760px]'
      } ${className}`}
      data-testid='wxpost-stage'
      data-preview-size={previewSize}
    >
      <article
        className={articleClasses}
        data-testid='wxpost-article'
        data-layout={presentation.layout}
        data-palette={presentation.palette}
        data-appearance={presentation.appearance}
        data-typeface={presentation.typeface}
      >
        <header className={heroClasses}>
          <div
            className={`flex flex-wrap items-baseline justify-between gap-3 ${
              fieldNotesDesktop
                ? 'col-span-2 col-start-1 row-start-1 max-[540px]:col-span-1'
                : editorialDesktop
                  ? 'col-start-1 row-start-1'
                  : ''
            }`}
          >
            <span className={MODULE_LABEL_CLASS}>
              {article.articleType === 'custom'
                ? article.customArticleType
                : article.articleType.replaceAll('-', ' ')}
            </span>
            {contextLabel && (
              <span className={MODULE_LABEL_CLASS}>{contextLabel}</span>
            )}
          </div>
          <span
            className={
              fieldNotesDesktop
                ? 'col-start-1 row-[2/span_3] grid content-start border-t-2 border-[var(--article-accent)] pt-[0.65rem] text-[0.68rem] font-semibold uppercase leading-6 tracking-[0.12em] text-[var(--article-muted)] max-[540px]:hidden'
                : 'hidden'
            }
            data-testid='field-notes-mark'
            aria-hidden='true'
          >
            <span>Field</span>
            <span>Notes</span>
          </span>
          <h1
            className={`m-0 min-w-0 text-[clamp(2.15rem,7vw,4rem)] leading-[1.18] tracking-[-0.025em] text-[var(--article-text)] [overflow-wrap:break-word] ${titleFontClass} ${
              fieldNotesDesktop
                ? 'col-start-2 row-start-2 max-[540px]:col-start-1 max-[540px]:row-auto'
                : editorialDesktop
                  ? 'col-start-1 row-start-2'
                  : ''
            }`}
          >
            {article.title}
          </h1>
          {article.excerpt && (
            <p
              className={`m-0 text-[var(--article-muted)] ${
                fieldNotesDesktop
                  ? 'col-start-2 row-start-3 max-[540px]:col-start-1 max-[540px]:row-auto'
                  : editorialDesktop
                    ? 'col-start-2 row-[2/span_2] border-l border-[var(--article-border)] pl-4 max-[540px]:col-start-1 max-[540px]:row-auto max-[540px]:border-l-0 max-[540px]:border-t max-[540px]:pl-0 max-[540px]:pt-4'
                    : ''
              }`}
            >
              {article.excerpt}
            </p>
          )}
          <div
            className={`flex flex-wrap items-baseline justify-between gap-3 text-[0.78rem] text-[var(--article-muted)] ${
              fieldNotesDesktop
                ? 'col-start-2 row-start-4 max-[540px]:col-start-1 max-[540px]:row-auto'
                : editorialDesktop
                  ? 'col-start-1 row-start-3'
                  : ''
            }`}
          >
            <span>{article.byline ?? 'SoarHigh Toastmasters'}</span>
            <span>SoarHigh</span>
          </div>
        </header>

        <div className='grid gap-9' data-testid='wxpost-body'>
          {article.body.map((node, index) =>
            node.kind === 'markdown' ? (
              <MarkdownBlock
                node={node}
                layout={presentation.layout}
                previewSize={previewSize}
                titleFontClass={titleFontClass}
                key={`markdown-${node.line}-${index}`}
              />
            ) : (
              <DirectiveBlock
                node={node}
                mediaById={mediaById}
                layout={presentation.layout}
                previewSize={previewSize}
                titleFontClass={titleFontClass}
                key={`${node.name}-${node.line}`}
              />
            )
          )}
        </div>
      </article>
    </div>
  );
}
