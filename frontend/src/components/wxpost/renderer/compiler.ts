import type {
  WxPostCompileRequest,
  WxPostCompileResult,
  WxPostDirectiveNode,
  WxPostMarkdownNode,
  WxPostMediaAsset,
  WxPostRenderContext,
  WxPostRenderDocument,
} from '../types';
import { wxPostEditKey, type WxPostEditTarget } from './editing';
import { escapeAttribute, escapeHtml, safeUrl, styleAttribute } from './html';
import { compileMarkdown, compileSectionMarkdown } from './markdown';
import {
  layoutModuleInset,
  layoutWidth,
  presentationTokens,
  type PresentationTokens,
} from './presentation';

const MODULE_LABEL_STYLE: Array<[string, string]> = [
  ['display', 'block'],
  ['margin-bottom', '6px'],
  ['font-size', '16px'],
  ['font-weight', '400'],
  ['letter-spacing', '0.08em'],
  ['line-height', '1.85'],
  ['text-transform', 'uppercase'],
];

// Matches the Style Lab's 12px mobile and 29.44px desktop insets while
// preserving one canonical HTML result across both preview canvases.
const ARTICLE_INLINE_PADDING = 'clamp(12px,calc(5.0405% - 7.6578px),29.44px)';

function safeAssetUrl(value: string | null | undefined) {
  return safeUrl(value, { allowBlob: true });
}

function articleTypeLabel(article: WxPostRenderDocument) {
  if (article.articleType === 'custom') {
    return article.customArticleType || 'Custom article';
  }
  return article.articleType
    .split('-')
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ');
}

function mediaUrl(
  media: WxPostMediaAsset | undefined,
  context: WxPostRenderContext
) {
  if (!media) return '';
  return safeAssetUrl(context.assetUrls?.[media.id] ?? media.sourceUrl);
}

function moduleLabel(label: string, tokens: PresentationTokens) {
  return `<span ${styleAttribute([
    ...MODULE_LABEL_STYLE,
    ['color', tokens.muted],
  ])}>${escapeHtml(label)}</span>`;
}

function editAttributes(
  editable: boolean,
  target: WxPostEditTarget,
  label: string
) {
  if (!editable) return '';
  return `data-wxpost-edit-key="${escapeAttribute(
    wxPostEditKey(target)
  )}" data-wxpost-edit-label="${escapeAttribute(label)}"`;
}

function directiveEditAttributes(
  editable: boolean,
  nodeIndex: number,
  path: Array<string | number>,
  label: string
) {
  return editAttributes(
    editable,
    { kind: 'directive', nodeIndex, path },
    label
  );
}

function directiveItemDeleteButton(
  editable: boolean,
  nodeIndex: number,
  itemIndex: number,
  label: string
) {
  if (!editable) return '';
  const key = wxPostEditKey({
    kind: 'directive',
    nodeIndex,
    path: ['items', itemIndex],
  });
  return `<button type="button" data-wxpost-delete-item="${escapeAttribute(
    key
  )}" aria-label="Delete ${escapeAttribute(label)}" title="Delete item" ${styleAttribute(
    [
      ['position', 'absolute'],
      ['top', '0'],
      ['right', '0'],
      ['display', 'flex'],
      ['width', '28px'],
      ['height', '28px'],
      ['align-items', 'center'],
      ['justify-content', 'center'],
      ['border', '0'],
      ['border-radius', '999px'],
      ['background', 'rgba(254,242,242,0.92)'],
      ['color', '#b91c1c'],
      ['cursor', 'pointer'],
      ['font-family', 'ui-sans-serif,system-ui,sans-serif'],
      ['font-size', '18px'],
      ['font-weight', '600'],
      ['line-height', '1'],
      ['padding', '0'],
    ]
  )}>&times;</button>`;
}

function mediaEditAttributes(
  editable: boolean,
  mediaId: string,
  label: string
) {
  return editAttributes(
    editable,
    { kind: 'media', mediaId, field: 'description' },
    label
  );
}

function moduleHeading(
  value: string,
  tokens: PresentationTokens,
  attributes = ''
) {
  return `<h2 ${attributes} ${styleAttribute([
    ['margin', '0'],
    ['color', tokens.text],
    ['font-family', tokens.titleFont],
    ['font-size', '20px'],
    ['font-weight', '500'],
    ['line-height', '1.35'],
    ['letter-spacing', '-0.02em'],
  ])}>${escapeHtml(value)}</h2>`;
}

function renderSection(
  node: Extract<WxPostDirectiveNode, { name: 'section' }>,
  markdown: WxPostMarkdownNode,
  number: number,
  tokens: PresentationTokens,
  layout: WxPostCompileRequest['presentation']['layout'],
  editable: boolean,
  directiveIndex: number,
  markdownIndex: number
) {
  const markdownParts = compileSectionMarkdown(
    markdown.source,
    tokens,
    editable ? { nodeIndex: markdownIndex } : undefined
  );
  const isBrand = layout === 'brand-default';
  const isFieldNotes = layout === 'field-notes';
  const headingStyles: Array<[string, string]> = isBrand
    ? [
        ['display', 'flex'],
        ['flex-wrap', 'wrap'],
        ['align-items', 'baseline'],
        ['justify-content', 'space-between'],
        ['column-gap', '12px'],
        ['flex', '0 0 100%'],
        ['padding-bottom', '12px'],
        ['border-bottom', `1px solid ${tokens.border}`],
      ]
    : isFieldNotes
      ? [
          ['display', 'flex'],
          ['flex-wrap', 'wrap'],
          ['align-content', 'flex-start'],
          ['align-items', 'baseline'],
          ['column-gap', '12px'],
          ['flex', '1 1 120px'],
          ['min-width', '120px'],
        ]
      : [
          ['display', 'flex'],
          ['flex-direction', 'column'],
          ['align-content', 'start'],
          ['align-items', 'flex-start'],
          ['flex', '1 1 200px'],
          ['min-width', '160px'],
          ['padding-top', '12px'],
          ['border-top', `3px solid ${tokens.accent}`],
        ];
  const copyStyles: Array<[string, string]> = isBrand
    ? [
        ['display', 'flex'],
        ['flex-direction', 'column'],
        ['gap', '12px'],
        ['flex', '0 0 100%'],
      ]
    : isFieldNotes
      ? [
          ['display', 'flex'],
          ['flex-direction', 'column'],
          ['gap', '12px'],
          ['flex', '3 1 360px'],
          ['min-width', '0'],
        ]
      : [
          ['display', 'flex'],
          ['flex-direction', 'column'],
          ['gap', '12px'],
          ['flex', '2 1 360px'],
          ['min-width', '0'],
        ];
  const rootStyles: Array<[string, string]> = [
    ['display', 'flex'],
    ['flex-wrap', 'wrap'],
    ['align-items', 'flex-start'],
    ['gap', isBrand ? '16px 0' : '16px 24px'],
    ['min-width', '0'],
  ];
  if (isFieldNotes) {
    rootStyles.push(
      ['padding-top', '16px'],
      ['border-top', `1px solid ${tokens.border}`]
    );
  }
  return `<section data-testid="directive-section" data-wxpost-directive="section" data-wxpost-line="${
    node.line
  }" ${styleAttribute([
    ['display', 'block'],
    ['min-width', '0'],
    ['margin', '0 0 32px'],
  ])}><div data-wxpost-line="${
    markdown.line
  }" data-wxpost-kind="markdown" ${styleAttribute(
    rootStyles
  )}><div data-wxpost-section-heading="true" ${styleAttribute(
    headingStyles
  )}><span ${directiveEditAttributes(
    editable,
    directiveIndex,
    ['kicker'],
    'section kicker'
  )} ${styleAttribute([
    ...MODULE_LABEL_STYLE,
    ['margin-bottom', '0'],
    ['color', tokens.muted],
  ])}>${escapeHtml(node.payload.kicker)}</span><span data-wxpost-decoration="true" contenteditable="false" ${styleAttribute(
    [
      ...MODULE_LABEL_STYLE,
      ['margin-bottom', '0'],
      ['color', tokens.muted],
      ['font-variant-numeric', 'tabular-nums'],
    ]
  )}>${String(number).padStart(2, '0')}</span>${
    markdownParts.heading
  }</div><div data-wxpost-section-copy="true" ${styleAttribute(copyStyles)}>${
    markdownParts.body
  }</div></div></section>`;
}

function caption(value: string, tokens: PresentationTokens, attributes = '') {
  return `<p ${attributes} ${styleAttribute([
    ['margin', '8px 0 0'],
    ['color', tokens.muted],
    ['font-size', '16px'],
    ['line-height', '1.85'],
  ])}>${escapeHtml(value)}</p>`;
}

function mediaPlaceholder(label: string, tokens: PresentationTokens) {
  return `<div ${styleAttribute([
    ['display', 'flex'],
    ['align-items', 'center'],
    ['justify-content', 'center'],
    ['min-height', '192px'],
    ['padding', '16px'],
    ['border', `1px solid ${tokens.border}`],
    ['background', tokens.soft],
    ['color', tokens.muted],
    ['text-align', 'center'],
  ])}>${escapeHtml(label)}</div>`;
}

function imageMarkup(
  media: WxPostMediaAsset | undefined,
  context: WxPostRenderContext,
  tokens: PresentationTokens,
  missingLabel: string
) {
  const url = mediaUrl(media, context);
  if (!url || media?.kind !== 'image') {
    return mediaPlaceholder(missingLabel, tokens);
  }
  return `<img src="${escapeAttribute(url)}" alt="${escapeAttribute(
    media.description
  )}" loading="lazy" ${styleAttribute([
    ['display', 'block'],
    ['width', '100%'],
    ['max-width', '100%'],
    ['height', 'auto'],
    ['margin', '0 auto'],
    ['border', `1px solid ${tokens.border}`],
  ])}>`;
}

function mediaDeleteButton(
  editable: boolean,
  mediaId: string,
  deleteKey: string,
  label: string
) {
  if (!editable) return '';
  return `<button type="button" data-wxpost-delete-media="${escapeAttribute(
    mediaId
  )}" data-wxpost-delete-key="${escapeAttribute(
    deleteKey
  )}" class="bg-red-400/75 transition-colors hover:bg-red-500" aria-label="${escapeAttribute(label)}" title="${escapeAttribute(
    label
  )}" contenteditable="false" ${styleAttribute([
    ['position', 'absolute'],
    ['top', '10px'],
    ['right', '10px'],
    ['z-index', '2'],
    ['display', 'grid'],
    ['width', '32px'],
    ['height', '32px'],
    ['place-items', 'center'],
    ['padding', '0'],
    ['border', '1px solid rgba(255,255,255,0.35)'],
    ['border-radius', '9999px'],
    ['box-shadow', '0 2px 8px rgba(15,23,42,0.22)'],
    ['color', '#ffffff'],
    ['cursor', 'pointer'],
  ])}><svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16" ${styleAttribute(
    [['display', 'block']]
  )}><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>`;
}

function editableMediaFrame(
  body: string,
  editable: boolean,
  mediaId: string,
  deleteKey: string,
  label: string
) {
  return `<div data-wxpost-media-frame="${escapeAttribute(
    mediaId
  )}"${editable ? ' tabindex="0"' : ''} ${styleAttribute([
    ['position', 'relative'],
    ['min-width', '0'],
    ['outline', 'none'],
  ])}>${body}${mediaDeleteButton(editable, mediaId, deleteKey, label)}</div>`;
}

function moduleShell(
  name: string,
  line: number,
  body: string,
  inset: string,
  extraStyles: Array<[string, string]> = []
) {
  return `<section data-testid="directive-${escapeAttribute(
    name
  )}" data-wxpost-directive="${escapeAttribute(
    name
  )}" data-wxpost-line="${line}" ${styleAttribute([
    ['display', 'block'],
    ['min-width', '0'],
    ['margin', `0 0 32px ${inset}`],
    ...extraStyles,
  ])}>${body}</section>`;
}

function renderImage(
  node: Extract<WxPostDirectiveNode, { name: 'image' }>,
  mediaById: Map<string, WxPostMediaAsset>,
  context: WxPostRenderContext,
  tokens: PresentationTokens,
  editable: boolean,
  nodeIndex: number
) {
  const media = mediaById.get(node.payload.media);
  const figureCaption = node.payload.caption ?? media?.description;
  const captionAttributes = node.payload.caption
    ? directiveEditAttributes(editable, nodeIndex, ['caption'], 'image caption')
    : media
      ? mediaEditAttributes(editable, media.id, 'image description')
      : '';
  return moduleShell(
    'image',
    node.line,
    `<figure ${styleAttribute([['margin', '0']])}>${editableMediaFrame(
      imageMarkup(
        media,
        context,
        tokens,
        `Missing image ${node.payload.media}`
      ),
      editable,
      node.payload.media,
      wxPostEditKey({ kind: 'directive', nodeIndex, path: ['media'] }),
      `Remove ${node.payload.media} from Draft`
    )}${
      figureCaption ? caption(figureCaption, tokens, captionAttributes) : ''
    }</figure>`,
    '0'
  );
}

function renderGallery(
  node: Extract<WxPostDirectiveNode, { name: 'gallery' }>,
  mediaById: Map<string, WxPostMediaAsset>,
  context: WxPostRenderContext,
  tokens: PresentationTokens,
  editable: boolean,
  nodeIndex: number
) {
  const items = node.payload.items.flatMap((id, itemIndex) => {
    const media = mediaById.get(id);
    return media ? [{ media, itemIndex }] : [];
  });
  const heading = node.payload.caption
    ? `<div ${styleAttribute([['margin-bottom', '14px']])}>${moduleLabel(
        'Gallery',
        tokens
      )}${moduleHeading(
        node.payload.caption,
        tokens,
        directiveEditAttributes(
          editable,
          nodeIndex,
          ['caption'],
          'gallery caption'
        )
      )}</div>`
    : moduleLabel('Gallery', tokens);
  const figures = items
    .map(
      ({ media, itemIndex }) =>
        `<figure ${styleAttribute([
          ['flex', '0 0 100%'],
          ['min-width', '0'],
          ['margin', '0'],
          ['scroll-snap-align', 'start'],
        ])}>${editableMediaFrame(
          imageMarkup(media, context, tokens, `Missing image ${media.id}`),
          editable,
          media.id,
          wxPostEditKey({
            kind: 'directive',
            nodeIndex,
            path: ['items', itemIndex],
          }),
          `Remove ${media.id} from Draft`
        )}${caption(
          media.description,
          tokens,
          mediaEditAttributes(editable, media.id, 'image description')
        )}</figure>`
    )
    .join('');
  return moduleShell(
    'gallery',
    node.line,
    `${heading}<div data-testid="gallery-track" aria-label="Image gallery" role="region" tabindex="0" ${styleAttribute(
      [
        ['display', 'flex'],
        ['width', '100%'],
        ['gap', '12px'],
        ['overflow-x', 'auto'],
        ['padding-bottom', '6px'],
        ['scroll-snap-type', 'x mandatory'],
        ['overscroll-behavior-inline', 'contain'],
      ]
    )}>${figures}</div>`,
    '0'
  );
}

function renderDirective(
  node: WxPostDirectiveNode,
  mediaById: Map<string, WxPostMediaAsset>,
  context: WxPostRenderContext,
  tokens: PresentationTokens,
  inset: string,
  layout: WxPostCompileRequest['presentation']['layout'],
  editable: boolean,
  nodeIndex: number
) {
  switch (node.name) {
    case 'section':
      return '';
    case 'image':
      return renderImage(node, mediaById, context, tokens, editable, nodeIndex);
    case 'gallery':
      return renderGallery(
        node,
        mediaById,
        context,
        tokens,
        editable,
        nodeIndex
      );
    case 'video': {
      const media = mediaById.get(node.payload.media);
      const url = mediaUrl(media, context);
      const video =
        media?.kind === 'video' && url
          ? `<video data-testid="wxpost-video" controls preload="metadata"${
              media.posterUrl
                ? ` poster="${escapeAttribute(safeAssetUrl(media.posterUrl))}"`
                : ''
            } aria-label="${escapeAttribute(
              media.description
            )}" ${styleAttribute([
              ['display', 'block'],
              ['width', '100%'],
              ['height', 'auto'],
              ['background', '#000000'],
            ])}><source src="${escapeAttribute(url)}"></video>`
          : mediaPlaceholder(`Missing video ${node.payload.media}`, tokens);
      const heading = node.payload.caption
        ? `${moduleLabel('Video', tokens)}${moduleHeading(
            node.payload.caption,
            tokens,
            directiveEditAttributes(
              editable,
              nodeIndex,
              ['caption'],
              'video caption'
            )
          )}`
        : moduleLabel('Video', tokens);
      return moduleShell(
        'video',
        node.line,
        `<div ${styleAttribute([
          ['margin-bottom', '14px'],
        ])}>${heading}</div>${editableMediaFrame(
          video,
          editable,
          node.payload.media,
          wxPostEditKey({ kind: 'directive', nodeIndex, path: ['media'] }),
          `Remove ${node.payload.media} from Draft`
        )}${
          media
            ? caption(
                media.description,
                tokens,
                mediaEditAttributes(editable, media.id, 'video description')
              )
            : ''
        }`,
        '0'
      );
    }
    case 'takeaway':
      return moduleShell(
        'takeaway',
        node.line,
        `${moduleLabel('Takeaway', tokens)}${
          node.payload.title
            ? `${moduleHeading(
                node.payload.title,
                tokens,
                directiveEditAttributes(
                  editable,
                  nodeIndex,
                  ['title'],
                  'takeaway title'
                )
              )}`
            : ''
        }<p ${directiveEditAttributes(
          editable,
          nodeIndex,
          ['text'],
          'takeaway text'
        )} ${styleAttribute([
          ['margin', node.payload.title ? '10px 0 0' : '0'],
          ['color', tokens.text],
        ])}>${escapeHtml(node.payload.text)}</p>`,
        inset,
        layout === 'editorial-feature'
          ? [
              ['padding', '20px 0'],
              ['border-top', `1px solid ${tokens.border}`],
              ['border-bottom', `1px solid ${tokens.border}`],
              ['text-align', 'center'],
            ]
          : [
              ['padding-left', '16px'],
              ['border-left', `3px solid ${tokens.accent}`],
            ]
      );
    case 'person': {
      const media = node.payload.media
        ? mediaById.get(node.payload.media)
        : undefined;
      const portrait = node.payload.media
        ? imageMarkup(
            media,
            context,
            tokens,
            `Portrait of ${node.payload.name}`
          )
        : '';
      const copy = `${moduleHeading(
        node.payload.name,
        tokens,
        directiveEditAttributes(editable, nodeIndex, ['name'], 'person name')
      )}${
        node.payload.role
          ? caption(
              node.payload.role,
              tokens,
              directiveEditAttributes(
                editable,
                nodeIndex,
                ['role'],
                'person role'
              )
            )
          : ''
      }${
        node.payload.summary
          ? `<p ${directiveEditAttributes(
              editable,
              nodeIndex,
              ['summary'],
              'person summary'
            )} ${styleAttribute([
              ['margin', '12px 0 0'],
              ['color', tokens.text],
            ])}>${escapeHtml(node.payload.summary)}</p>`
          : ''
      }${
        node.payload.quote
          ? `<blockquote ${styleAttribute([
              ['margin', '14px 0 0'],
              ['padding-left', '12px'],
              ['border-left', `2px solid ${tokens.accent}`],
              ['color', tokens.muted],
            ])}>“<span ${directiveEditAttributes(
              editable,
              nodeIndex,
              ['quote'],
              'person quote'
            )}>${escapeHtml(node.payload.quote)}</span>”</blockquote>`
          : ''
      }`;
      return moduleShell(
        'person',
        node.line,
        `${moduleLabel('Profile', tokens)}<div ${styleAttribute([
          ['display', 'flex'],
          ['flex-wrap', 'wrap'],
          ['align-items', 'flex-start'],
          ['gap', '20px'],
        ])}>${
          portrait
            ? `<div ${styleAttribute([
                ['flex', '1 1 180px'],
                ['min-width', '0'],
              ])}>${editableMediaFrame(
                portrait,
                editable,
                node.payload.media!,
                wxPostEditKey({
                  kind: 'directive',
                  nodeIndex,
                  path: ['media'],
                }),
                `Remove ${node.payload.media} from Draft`
              )}</div>`
            : ''
        }<div ${styleAttribute([
          ['flex', '2 1 260px'],
          ['min-width', '0'],
        ])}>${copy}</div></div>`,
        inset
      );
    }
    case 'info-grid': {
      const items = node.payload.items
        .map(
          (item, index) =>
            `<div ${styleAttribute([
              ['position', 'relative'],
              ['flex', '1 1 140px'],
              ['min-width', '0'],
              ['padding-right', editable ? '34px' : false],
            ])} data-wxpost-item-container><span ${styleAttribute([
              ['display', 'block'],
              ['color', tokens.muted],
              ['font-size', '16px'],
              ['line-height', '1.85'],
            ])} ${directiveEditAttributes(
              editable,
              nodeIndex,
              ['items', index, 'label'],
              'info label'
            )}>${escapeHtml(item.label)}</span><strong ${directiveEditAttributes(
              editable,
              nodeIndex,
              ['items', index, 'value'],
              'info value'
            )} ${styleAttribute([
              ['color', tokens.text],
              ['font-weight', '600'],
            ])}>${escapeHtml(item.value)}</strong>${directiveItemDeleteButton(
              editable,
              nodeIndex,
              index,
              'info item'
            )}</div>`
        )
        .join('');
      return moduleShell(
        'info-grid',
        node.line,
        `${moduleLabel('At a glance', tokens)}${
          node.payload.title
            ? `<div ${styleAttribute([
                ['margin-bottom', '14px'],
              ])}>${moduleHeading(
                node.payload.title,
                tokens,
                directiveEditAttributes(
                  editable,
                  nodeIndex,
                  ['title'],
                  'info grid title'
                )
              )}</div>`
            : ''
        }<div ${styleAttribute([
          ['display', 'flex'],
          ['flex-wrap', 'wrap'],
          ['gap', '16px'],
          ['padding', '16px 0'],
          ['border-top', `1px solid ${tokens.border}`],
          ['border-bottom', `1px solid ${tokens.border}`],
        ])}>${items}</div>`,
        inset
      );
    }
    case 'timeline': {
      const items = node.payload.items
        .map(
          (item, index) =>
            `<div ${styleAttribute([
              ['position', 'relative'],
              ['display', 'flex'],
              ['flex-wrap', 'wrap'],
              ['gap', '8px 16px'],
              ['padding', '14px 0'],
              ['padding-right', editable ? '34px' : false],
              ['border-top', index > 0 ? `1px solid ${tokens.border}` : false],
            ])} data-wxpost-item-container><strong ${styleAttribute([
              ['flex', '0 1 80px'],
              ['color', tokens.muted],
              ['font-size', '16px'],
              ['letter-spacing', '0.08em'],
              ['line-height', '1.85'],
              ['text-transform', 'uppercase'],
            ])} ${directiveEditAttributes(
              editable,
              nodeIndex,
              ['items', index, 'label'],
              'timeline label'
            )}>${escapeHtml(item.label)}</strong><div ${styleAttribute([
              ['flex', '1 1 220px'],
              ['min-width', '0'],
            ])}><strong ${directiveEditAttributes(
              editable,
              nodeIndex,
              ['items', index, 'title'],
              'timeline item title'
            )} ${styleAttribute([
              ['color', tokens.text],
              ['font-weight', '600'],
            ])}>${escapeHtml(item.title)}</strong>${
              item.description
                ? `<p ${directiveEditAttributes(
                    editable,
                    nodeIndex,
                    ['items', index, 'description'],
                    'timeline item description'
                  )} ${styleAttribute([
                    ['margin', '4px 0 0'],
                    ['color', tokens.text],
                  ])}>${escapeHtml(item.description)}</p>`
                : ''
            }</div>${directiveItemDeleteButton(
              editable,
              nodeIndex,
              index,
              'timeline item'
            )}</div>`
        )
        .join('');
      return moduleShell(
        'timeline',
        node.line,
        `${moduleLabel('Timeline', tokens)}${
          node.payload.title
            ? `<div ${styleAttribute([
                ['margin-bottom', '8px'],
              ])}>${moduleHeading(
                node.payload.title,
                tokens,
                directiveEditAttributes(
                  editable,
                  nodeIndex,
                  ['title'],
                  'timeline title'
                )
              )}</div>`
            : ''
        }<div ${styleAttribute([
          ['padding-left', '16px'],
          ['border-left', `1px solid ${tokens.border}`],
        ])}>${items}</div>`,
        inset
      );
    }
    case 'pull-quote':
      return moduleShell(
        'pull-quote',
        node.line,
        `${moduleLabel('Quote', tokens)}<blockquote ${styleAttribute([
          ['margin', '0'],
          ['color', tokens.text],
          ['font-family', tokens.titleFont],
          ['font-size', '20px'],
          ['line-height', '1.45'],
        ])}>“<span ${directiveEditAttributes(
          editable,
          nodeIndex,
          ['text'],
          'pull quote'
        )}>${escapeHtml(node.payload.text)}</span>”</blockquote>${
          node.payload.attribution
            ? `<p ${styleAttribute([
                ['margin', '10px 0 0'],
                ['color', tokens.muted],
                ['font-size', '16px'],
                ['line-height', '1.85'],
              ])}>— <span ${directiveEditAttributes(
                editable,
                nodeIndex,
                ['attribution'],
                'quote attribution'
              )}>${escapeHtml(node.payload.attribution)}</span></p>`
            : ''
        }`,
        inset,
        [
          ['max-width', layout === 'editorial-feature' ? '544px' : 'none'],
          ['margin-left', layout === 'editorial-feature' ? 'auto' : inset],
          ['margin-right', layout === 'editorial-feature' ? 'auto' : '0'],
          ['padding', '20px 0'],
          ['border-top', `1px solid ${tokens.border}`],
          ['border-bottom', `1px solid ${tokens.border}`],
          ['text-align', 'center'],
        ]
      );
  }
}

function renderHeader(
  article: WxPostRenderDocument,
  context: WxPostRenderContext,
  tokens: PresentationTokens,
  layout: WxPostCompileRequest['presentation']['layout'],
  palette: WxPostCompileRequest['presentation']['palette'],
  editable: boolean
) {
  const topBorderStyles: Array<[string, string]> =
    palette === 'brand-blue'
      ? [
          ['border-top', '4px solid transparent'],
          [
            'border-image',
            `linear-gradient(90deg,${tokens.accent},${tokens.accentSecondary}) 1`,
          ],
        ]
      : palette === 'warm-terracotta'
        ? [['border-top', `4px solid ${tokens.accent}`]]
        : [['border-top', `1px solid ${tokens.text}`]];
  const metaContext = layout === 'field-notes' ? null : context.contextLabel;
  const meta = `<div ${styleAttribute([
    ['display', 'flex'],
    ['flex-wrap', 'wrap'],
    ['justify-content', 'space-between'],
    ['gap', '8px'],
    ['color', tokens.muted],
    ['font-size', '16px'],
    ['font-weight', '400'],
    ['letter-spacing', '0.08em'],
    ['line-height', '1.85'],
    ['margin-bottom', '16px'],
    ['text-transform', 'uppercase'],
  ])}><span>${escapeHtml(articleTypeLabel(article))}</span>${
    metaContext ? `<span>${escapeHtml(metaContext)}</span>` : ''
  }</div>`;
  const title = `<h1 ${editAttributes(
    editable,
    { kind: 'article', field: 'title' },
    'draft title'
  )} ${styleAttribute([
    ['margin', '0 0 16px'],
    ['color', tokens.text],
    ['font-family', tokens.titleFont],
    ['font-size', '24px'],
    ['font-weight', '500'],
    ['line-height', '1.35'],
    ['letter-spacing', '-0.02em'],
    ['overflow-wrap', 'break-word'],
  ])}>${escapeHtml(article.title)}</h1>`;
  const deck = article.excerpt
    ? `<p ${editAttributes(
        editable,
        { kind: 'article', field: 'excerpt' },
        'draft excerpt'
      )} ${styleAttribute([
        ['margin', '0 0 16px'],
        ['color', tokens.muted],
        ['font-size', '16px'],
        ['line-height', '1.85'],
      ])}>${escapeHtml(article.excerpt)}</p>`
    : '';
  const publisher =
    article.byline || context.publisherName || 'SoarHigh Toastmasters';
  const footer = `<div ${styleAttribute([
    ['display', 'flex'],
    ['flex-wrap', 'wrap'],
    ['justify-content', 'space-between'],
    ['gap', '8px'],
    ['color', tokens.muted],
    ['font-size', '16px'],
    ['line-height', '1.85'],
  ])}><span ${
    article.byline
      ? editAttributes(
          editable,
          { kind: 'article', field: 'byline' },
          'draft byline'
        )
      : ''
  }>${escapeHtml(publisher)}</span>${
    context.displayDate ? `<span>${escapeHtml(context.displayDate)}</span>` : ''
  }</div>`;

  if (layout === 'editorial-feature') {
    return `<header ${styleAttribute([
      ['display', 'flex'],
      ['flex-wrap', 'wrap'],
      ['align-items', 'flex-end'],
      ['gap', '18px 24px'],
      ['padding', '0 0 24px'],
      ...topBorderStyles,
      ['border-bottom', `1px solid ${tokens.border}`],
    ])}><div ${styleAttribute([
      ['flex', '2 1 320px'],
      ['display', 'block'],
      ['min-width', '0'],
    ])}>${meta}${title}${footer}</div>${
      deck
        ? `<div ${styleAttribute([
            ['flex', '1 1 220px'],
            ['padding-left', '16px'],
            ['border-left', `1px solid ${tokens.border}`],
          ])}>${deck}</div>`
        : ''
    }</header>`;
  }

  if (layout === 'field-notes') {
    return `<header ${styleAttribute([
      ['display', 'flex'],
      ['flex-wrap', 'wrap'],
      ['align-items', 'flex-start'],
      ['gap', '16px 24px'],
      ['padding', '12px 0 24px'],
      ...topBorderStyles,
      ['border-bottom', `1px solid ${tokens.border}`],
    ])}>${
      context.contextLabel
        ? `<span data-wxpost-hero-mark="true" ${styleAttribute([
            ['flex', '1 1 120px'],
            ['min-width', '120px'],
            ['color', tokens.muted],
            ['font-size', '16px'],
            ['font-weight', '400'],
            ['letter-spacing', '0.08em'],
            ['line-height', '1.85'],
            ['text-transform', 'uppercase'],
          ])}>${escapeHtml(context.contextLabel)}</span>`
        : ''
    }<div ${styleAttribute([
      ['flex', '3 1 360px'],
      ['min-width', '0'],
    ])}>${meta}${title}${deck}${footer}</div></header>`;
  }

  return `<header ${styleAttribute([
    ['display', 'block'],
    ['padding', '24px 0'],
    ...topBorderStyles,
    ['border-bottom', `1px solid ${tokens.border}`],
  ])}>${meta}${title}${deck}${footer}</header>`;
}

export function compileWxPost(
  request: WxPostCompileRequest,
  options: { editable?: boolean } = {}
): WxPostCompileResult {
  const { renderDocument: article, presentation, context } = request;
  const editable = options.editable ?? false;
  const tokens = presentationTokens(presentation);
  const mediaById = new Map(
    article.media
      .filter((media) => media.include)
      .map((media) => [media.id, media])
  );
  const inset = layoutModuleInset(presentation.layout);
  const bodyParts: string[] = [];
  let sectionNumber = 0;
  for (let index = 0; index < article.body.length; index += 1) {
    const node = article.body[index];
    if (node.kind === 'directive' && node.name === 'section') {
      const following = article.body[index + 1];
      if (following?.kind === 'markdown') {
        sectionNumber += 1;
        bodyParts.push(
          renderSection(
            node,
            following,
            sectionNumber,
            tokens,
            presentation.layout,
            editable,
            index,
            index + 1
          )
        );
        index += 1;
        continue;
      }
    }
    if (node.kind === 'directive') {
      bodyParts.push(
        renderDirective(
          node,
          mediaById,
          context,
          tokens,
          inset,
          presentation.layout,
          editable,
          index
        )
      );
      continue;
    }
    bodyParts.push(
      `<section data-testid="markdown-segment" data-wxpost-line="${node.line}" data-wxpost-kind="markdown" ${styleAttribute(
        [
          ['min-width', '0'],
          ['margin', '0 0 32px'],
        ]
      )}><div>${compileMarkdown(
        node.source,
        tokens,
        editable ? { editable: { nodeIndex: index } } : undefined
      )}</div></section>`
    );
  }
  const body = bodyParts.join('');

  const html = `<article data-testid="wxpost-article" data-wxpost-render-version="1" data-layout="${escapeAttribute(
    presentation.layout
  )}" data-palette="${escapeAttribute(
    presentation.palette
  )}" data-appearance="${escapeAttribute(
    presentation.appearance
  )}" data-typeface="${escapeAttribute(
    presentation.typeface
  )}" ${styleAttribute([
    ['box-sizing', 'border-box'],
    ['display', 'block'],
    ['width', '100%'],
    ['max-width', layoutWidth(presentation.layout)],
    ['margin', '0 auto'],
    ['padding', `29.44px ${ARTICLE_INLINE_PADDING}`],
    ['border', `1px solid ${tokens.border}`],
    ['background', tokens.background],
    ['color', tokens.text],
    ['font-family', tokens.bodyFont],
    ['font-size', '16px'],
    ['font-weight', '430'],
    ['line-height', '1.85'],
    ['box-shadow', '0 24px 64px rgba(15,23,42,0.12)'],
  ])}>${renderHeader(
    article,
    context,
    tokens,
    presentation.layout,
    presentation.palette,
    editable
  )}<div data-wxpost-body="true" ${styleAttribute([
    ['display', 'block'],
    ['padding-top', '32px'],
  ])}>${body}</div></article>`;

  return { renderVersion: 1, html };
}
