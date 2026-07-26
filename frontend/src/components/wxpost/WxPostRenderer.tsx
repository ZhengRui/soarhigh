'use client';

/* eslint-disable @next/next/no-img-element */

import { useMemo, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { remarkKeyPoints } from './remarkKeyPoints';
import styles from './WxPostRenderer.module.css';
import type {
  WxPostBodyNode,
  WxPostDirectiveNode,
  WxPostMediaAsset,
  WxPostPresentation,
  WxPostPreviewSize,
  WxPostRenderDocument,
} from './types';

const LAYOUT_CLASSES = {
  'brand-default': styles.layoutBrandDefault,
  'field-notes': styles.layoutFieldNotes,
  'editorial-feature': styles.layoutEditorialFeature,
} as const;

const PALETTE_CLASSES = {
  'brand-blue': styles.paletteBrandBlue,
  'paper-neutral': styles.palettePaperNeutral,
  'warm-terracotta': styles.paletteWarmTerracotta,
} as const;

const APPEARANCE_CLASSES = {
  light: styles.appearanceLight,
  dark: styles.appearanceDark,
} as const;

const TYPEFACE_CLASSES = {
  'modern-sans': styles.typefaceModernSans,
  'editorial-serif': styles.typefaceEditorialSerif,
  'humanist-mix': styles.typefaceHumanistMix,
} as const;

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
}

function MediaFigure({
  media,
  fallback,
}: {
  media?: WxPostMediaAsset;
  fallback: string;
}) {
  return (
    <div className={styles.mediaFrame}>
      {media?.kind === 'image' ? (
        <img
          className={styles.mediaImage}
          src={media.sourceUrl}
          alt={media.description}
          loading='lazy'
        />
      ) : (
        <span className={styles.mediaPlaceholder}>{fallback}</span>
      )}
    </div>
  );
}

function GalleryBlock({
  node,
  mediaById,
}: {
  node: Extract<WxPostDirectiveNode, { name: 'gallery' }>;
  mediaById: Map<string, WxPostMediaAsset>;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const items = node.payload.items
    .map((id) => mediaById.get(id))
    .filter((item): item is WxPostMediaAsset => Boolean(item));

  const move = (direction: -1 | 1) => {
    const track = trackRef.current;
    if (!track) return;
    track.scrollBy({
      left: direction * Math.max(track.clientWidth * 0.84, 240),
      behavior: 'smooth',
    });
  };

  return (
    <section className={styles.module} data-testid='directive-gallery'>
      <div className={styles.galleryHeading}>
        <div>
          <span className={styles.moduleLabel}>Gallery</span>
          {node.payload.caption && (
            <h2 className={styles.moduleTitle}>{node.payload.caption}</h2>
          )}
        </div>
        <div className={styles.galleryControls}>
          <button
            className={styles.galleryButton}
            type='button'
            aria-label='Previous gallery image'
            onClick={() => move(-1)}
          >
            ←
          </button>
          <button
            className={styles.galleryButton}
            type='button'
            aria-label='Next gallery image'
            onClick={() => move(1)}
          >
            →
          </button>
        </div>
      </div>
      <div
        className={styles.galleryTrack}
        ref={trackRef}
        data-testid='gallery-track'
      >
        {items.map((media) => (
          <figure className={styles.galleryItem} key={media.id}>
            <MediaFigure media={media} fallback={`Missing image ${media.id}`} />
            <figcaption>{media.description}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

function DirectiveBlock({ node, mediaById }: DirectiveProps) {
  switch (node.name) {
    case 'gallery':
      return <GalleryBlock node={node} mediaById={mediaById} />;

    case 'video': {
      const media = mediaById.get(node.payload.media);
      return (
        <section className={styles.module} data-testid='directive-video'>
          <div className={styles.videoMeta}>
            <span className={styles.moduleLabel}>Video</span>
            {node.payload.caption && (
              <span className={styles.caption}>{node.payload.caption}</span>
            )}
          </div>
          {media?.kind === 'video' ? (
            <div className={styles.videoFrame}>
              <video
                className={styles.video}
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
          {media && <p className={styles.caption}>{media.description}</p>}
        </section>
      );
    }

    case 'takeaway':
      return (
        <aside
          className={`${styles.module} ${styles.takeaway}`}
          data-testid='directive-takeaway'
        >
          <span className={styles.moduleLabel}>Takeaway</span>
          {node.payload.title && (
            <h2 className={styles.moduleTitle}>{node.payload.title}</h2>
          )}
          <p>{node.payload.text}</p>
        </aside>
      );

    case 'person': {
      const media = node.payload.media
        ? mediaById.get(node.payload.media)
        : undefined;
      return (
        <section className={styles.module} data-testid='directive-person'>
          <span className={styles.moduleLabel}>Profile</span>
          <div className={styles.personLayout}>
            <MediaFigure
              media={media}
              fallback={`Portrait of ${node.payload.name}`}
            />
            <div className={styles.personCopy}>
              <h2 className={styles.personName}>{node.payload.name}</h2>
              {node.payload.role && (
                <p className={styles.personRole}>{node.payload.role}</p>
              )}
              {node.payload.summary && <p>{node.payload.summary}</p>}
              {node.payload.quote && (
                <blockquote>“{node.payload.quote}”</blockquote>
              )}
            </div>
          </div>
        </section>
      );
    }

    case 'info-grid':
      return (
        <section className={styles.module} data-testid='directive-info-grid'>
          <span className={styles.moduleLabel}>At a glance</span>
          {node.payload.title && (
            <h2 className={styles.moduleTitle}>{node.payload.title}</h2>
          )}
          <div className={styles.infoGrid}>
            {node.payload.items.map((item) => (
              <div
                className={styles.infoItem}
                key={`${item.label}-${item.value}`}
              >
                <span className={styles.caption}>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </section>
      );

    case 'timeline':
      return (
        <section className={styles.module} data-testid='directive-timeline'>
          <span className={styles.moduleLabel}>Timeline</span>
          {node.payload.title && (
            <h2 className={styles.moduleTitle}>{node.payload.title}</h2>
          )}
          <div className={styles.timelineList}>
            {node.payload.items.map((item) => (
              <div
                className={styles.timelineEntry}
                key={`${item.label}-${item.title}`}
              >
                <strong className={styles.timeLabel}>{item.label}</strong>
                <div className={styles.timelineCopy}>
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
          className={`${styles.module} ${styles.pullQuote}`}
          data-testid='directive-pull-quote'
        >
          <blockquote>“{node.payload.text}”</blockquote>
          {node.payload.attribution && (
            <figcaption>
              <cite>— {node.payload.attribution}</cite>
            </figcaption>
          )}
        </figure>
      );
  }
}

function MarkdownBlock({
  node,
}: {
  node: Extract<WxPostBodyNode, { kind: 'markdown' }>;
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

  return (
    <section
      className={styles.markdownSegment}
      data-leading-heading={hasLeadingHeading}
      data-source-line={node.line}
      data-testid='markdown-segment'
    >
      <div className={styles.markdown}>
        {hasLeadingHeading ? (
          <>
            <div className={styles.sectionHeading}>
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkKeyPoints]}>
                {headingSource}
              </ReactMarkdown>
            </div>
            {copySource && (
              <div className={styles.sectionCopy} data-wxpost-section-copy>
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkKeyPoints]}>
                  {copySource}
                </ReactMarkdown>
              </div>
            )}
          </>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkKeyPoints]}>
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

  const articleClasses = [
    styles.article,
    LAYOUT_CLASSES[presentation.layout],
    PALETTE_CLASSES[presentation.palette],
    APPEARANCE_CLASSES[presentation.appearance],
    TYPEFACE_CLASSES[presentation.typeface],
  ].join(' ');

  return (
    <div
      className={`${styles.stage} ${
        previewSize === 'mobile-390'
          ? styles.previewMobile
          : styles.previewDesktop
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
        <header className={styles.hero}>
          <div className={styles.heroMeta}>
            <span className={styles.eyebrow}>
              {article.articleType === 'custom'
                ? article.customArticleType
                : article.articleType.replaceAll('-', ' ')}
            </span>
            {contextLabel && (
              <span className={styles.folio}>{contextLabel}</span>
            )}
          </div>
          <span
            className={styles.fieldNotesMark}
            data-testid='field-notes-mark'
            aria-hidden='true'
          >
            <span>Field</span>
            <span>Notes</span>
          </span>
          <h1 className={styles.title}>{article.title}</h1>
          {article.excerpt && <p className={styles.deck}>{article.excerpt}</p>}
          <div className={styles.heroFooter}>
            <span>{article.byline ?? 'SoarHigh Toastmasters'}</span>
            <span>SoarHigh</span>
          </div>
        </header>

        <div className={styles.body} data-testid='wxpost-body'>
          {article.body.map((node, index) =>
            node.kind === 'markdown' ? (
              <MarkdownBlock
                node={node}
                key={`markdown-${node.line}-${index}`}
              />
            ) : (
              <DirectiveBlock
                node={node}
                mediaById={mediaById}
                key={`${node.name}-${node.line}`}
              />
            )
          )}
        </div>
      </article>
    </div>
  );
}
