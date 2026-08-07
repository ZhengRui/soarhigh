/**
 * WeChat mini emitter — a SECOND, export-only renderer for when the canonical
 * HTML would approach WeChat's 20,000-char draft limit.
 *
 * It reads the same `WxPostRenderDocument` as the canonical compiler but writes
 * minimal single-column HTML that APPROXIMATES the web look at ~half the bytes
 * (~50% smaller on real posts). It carries NO editing machinery (editability
 * lives entirely in the untouched canonical renderer) and always emits the
 * LIGHT palette (WeChat has no dark mode). The public preview page lets members
 * toggle Canonical vs Mini to compare look and rendered-char count.
 *
 * Covers all 9 directives so it is at capability parity with the canonical
 * renderer. Prose + section headings reuse the shared markdown helpers.
 *
 * Byte strategy (vertical rhythm is never touched):
 *  - body typography (font-size/line-height/color/font-family) lives ONCE on the
 *    article root and is inherited; a post-pass strips duplicate declarations
 *  - font stacks keep only the first (iOS) name + Georgia/serif fallback — the
 *    middle names exist on neither WeChat platform
 *  - labels are uppercased literally instead of via text-transform
 *  - sections, person cards, and non-brand headers keep the canonical's
 *    wide-screen two-column layouts (pure flex-wrap arithmetic — no media
 *    queries), wrapping to the stacked form at phone widths
 */
import type {
  WxPostCompileRequest,
  WxPostCompileResult,
  WxPostDirectiveNode,
  WxPostLayout,
  WxPostMediaAsset,
  WxPostRenderContext,
  WxPostRenderDocument,
} from '../types';
import { escapeAttribute, escapeHtml, safeUrl, styleAttribute } from './html';
import { compileMarkdown, compileSectionMarkdown } from './markdown';
import {
  layoutWidth,
  presentationTokens,
  type PresentationTokens,
} from './presentation';

interface Ctx {
  ctx: WxPostRenderContext;
  t: PresentationTokens;
  layout: WxPostLayout;
  brand: boolean;
}

// Long stack -> short stack with identical fallback behaviour on WeChat
// iOS/Android/desktop clients (the dropped middle names exist on none of them).
const FONT_SHORTENING: Array<[string, string]> = [
  [
    'Baskerville,"Iowan Old Style","Palatino Linotype","Book Antiqua",Georgia,serif',
    'Baskerville,serif',
  ],
  [
    '"Iowan Old Style","Palatino Linotype","Book Antiqua",Georgia,"Times New Roman",serif',
    'Iowan Old Style,Georgia,serif',
  ],
  [
    '"Avenir Next","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif',
    'Avenir Next,Segoe UI,Roboto,sans-serif',
  ],
  [
    'Charter,"Bitstream Charter","Sitka Text",Cambria,Georgia,serif',
    'Charter,Sitka Text,Cambria,serif',
  ],
];

function shortFont(stack: string) {
  for (const [long, short] of FONT_SHORTENING) if (long === stack) return short;
  return stack;
}

// The quotes appear attribute-escaped as &quot; (styleAttribute) or &#x22;
// (rehype-stringify), so replace both escapings. After this pass no style
// value contains an entity, which compactStyles' `;`-splitting relies on.
function shortenFonts(html: string) {
  for (const [long, short] of FONT_SHORTENING) {
    for (const escaped of [
      long.replace(/"/g, '&quot;'),
      long.replace(/"/g, '&#x22;'),
    ]) {
      html = html.split(escaped).join(short);
    }
  }
  return html;
}

// tags whose UA stylesheet already renders these declarations' effect
const UA_BLOCK_TAGS = new Set([
  'div',
  'section',
  'article',
  'header',
  'figure',
  'figcaption',
  'blockquote',
  'p',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'ul',
  'ol',
]);
const UA_BOLD_TAGS = new Set(['strong', 'b', 'h4', 'h5', 'h6', 'th']);

// shave value bytes without changing the rendering perceptibly: drop leading
// zeros, and collapse 6-digit hex to 3-digit ONLY when near-exact (channel
// error ≤ 3/255) — larger tolerances turn pale tints gray, because a tint's
// channel deltas are smaller than the rounding error
function minifyValue(value: string) {
  return value
    .replace(/(^|[\s,(])0\.(\d)/g, '$1.$2')
    .replace(/#([0-9a-f]{6})\b/gi, (whole, hex: string) => {
      const channels = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
      const nibbles = channels.map((v) => Math.round(v / 17));
      if (channels.some((v, i) => Math.abs(v - nibbles[i] * 17) > 3))
        return whole;
      return `#${nibbles.map((n) => n.toString(16)).join('')}`;
    });
}

/**
 * Dedup style declarations (last-wins, matching CSS) and compact them:
 *  - strip values equal to the article root's inherited default (descendants
 *    inherit the same computed value); tags whose UA stylesheet overrides the
 *    property (strong's bold, h5's 0.83em) keep theirs
 *  - strip declarations the UA stylesheet already provides (display:block on
 *    block tags; font-weight:600 on bold tags — the serif faces have no 600,
 *    so 600 and the UA's 700 resolve to the same rendered face)
 *  - strip min-width:0 on non-flex elements (flex columns keep it — they need
 *    it to shrink below their content's min width)
 *  - merge font longhands / key-point decoration longhands into shorthands
 *  - minify values (leading zeros, 3-digit hex)
 */
function compactStyles(html: string, t: PresentationTokens) {
  const inherited: Record<string, string[]> = {
    'font-size:16px': [
      'h1',
      'h2',
      'h3',
      'h5',
      'h6',
      'code',
      'pre',
      'small',
      'sup',
      'sub',
    ],
    'line-height:1.85': [],
    [`color:${t.text}`]: ['a'],
    'font-weight:400': [
      'strong',
      'b',
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'h6',
      'th',
    ],
    [`font-family:${shortFont(t.bodyFont)}`]: ['code', 'pre', 'kbd', 'samp'],
  };
  return html.replace(
    /<([a-z][a-z0-9]*)([^>]*)>/g,
    (whole, tag: string, attrs: string) => {
      const m = attrs.match(/ style="([^"]*)"/);
      if (!m) return whole;
      // entities like &#x22; contain ';' and would corrupt the decl split —
      // shortenFonts removes all of them, but fail safe if one slips through
      if (m[1].includes('&')) return whole;
      const map = new Map<string, string>();
      for (const decl of m[1].split(';')) {
        const i = decl.indexOf(':');
        if (i > 0) map.set(decl.slice(0, i).trim(), decl.slice(i + 1).trim());
      }
      for (const [prop, value] of map) {
        const uaSensitiveTags = inherited[`${prop}:${value}`];
        if (uaSensitiveTags && !uaSensitiveTags.includes(tag)) map.delete(prop);
      }
      if (map.get('display') === 'block' && UA_BLOCK_TAGS.has(tag))
        map.delete('display');
      if (map.get('font-weight') === '600' && UA_BOLD_TAGS.has(tag))
        map.delete('font-weight');
      if (map.get('min-width') === '0' && !map.has('flex'))
        map.delete('min-width');
      // heading tracking (-0.02em ≈ 0.4px at 20px) is below perception
      const tracking = map.get('letter-spacing');
      if (tracking === '-0.02em' || tracking === '-0.015em')
        map.delete('letter-spacing');
      if (map.has('text-decoration-line')) {
        const parts = [
          map.get('text-decoration-line'),
          map.get('text-decoration-thickness'),
          map.get('text-decoration-color'),
        ];
        map.delete('text-decoration-line');
        map.delete('text-decoration-thickness');
        map.delete('text-decoration-color');
        map.delete('text-decoration-skip-ink');
        map.set('text-decoration', parts.filter(Boolean).join(' '));
      }
      // font shorthand only when line-height is present — the shorthand RESETS
      // an omitted line-height to `normal` instead of inheriting
      if (
        map.has('font-family') &&
        map.has('font-size') &&
        map.has('line-height')
      ) {
        const weight = map.get('font-weight');
        const font = `${weight ? `${weight} ` : ''}${map.get('font-size')}/${map.get('line-height')} ${map.get('font-family')}`;
        map.delete('font-family');
        map.delete('font-size');
        map.delete('font-weight');
        map.delete('line-height');
        map.set('font', font);
      }
      const kept = [...map].map(
        ([prop, value]) => `${prop}:${minifyValue(value)}`
      );
      const newAttrs = attrs.replace(
        m[0],
        kept.length ? ` style="${kept.join(';')}"` : ''
      );
      return `<${tag}${newAttrs}>`;
    }
  );
}

function assetUrl(
  media: WxPostMediaAsset | undefined,
  ctx: WxPostRenderContext
) {
  if (!media) return '';
  return safeUrl(ctx.assetUrls?.[media.id] ?? media.sourceUrl, {
    allowBlob: true,
  });
}

function articleTypeLabel(a: WxPostRenderDocument) {
  if (a.articleType === 'custom')
    return a.customArticleType || 'Custom article';
  return a.articleType
    .split('-')
    .map((p) => p[0].toUpperCase() + p.slice(1))
    .join(' ');
}

// 1px ≈ the canonical's 0.08em (1.28px at 16px) at fewer bytes
const LABEL_TRACKING: [string, string] = ['letter-spacing', '1px'];

// directive labels (GALLERY, TIMELINE, …) are 600 in the canonical — one step
// heavier than the 400 section kickers, so they can't share MODULE_LABEL
function moduleLabel(text: string, t: PresentationTokens) {
  return `<p ${styleAttribute([
    ['margin', '0 0 6px'],
    ['color', t.accent],
    ['font-weight', '600'],
    LABEL_TRACKING,
  ])}>${escapeHtml(text.toUpperCase())}</p>`;
}

function heading(text: string, t: PresentationTokens, size = '20px') {
  return `<h2 ${styleAttribute([
    ['margin', '0 0 14px'],
    ['font-family', t.titleFont],
    ['font-size', size],
    ['font-weight', '500'],
    ['line-height', '1.35'],
  ])}>${escapeHtml(text)}</h2>`;
}

function imageMarkup(media: WxPostMediaAsset | undefined, c: Ctx) {
  const url = assetUrl(media, c.ctx);
  if (!url || media?.kind !== 'image') {
    return `<div ${styleAttribute([
      ['padding', '16px'],
      ['border', `1px solid ${c.t.border}`],
      ['background', c.t.soft],
      ['color', c.t.muted],
      ['text-align', 'center'],
    ])}>Missing image</div>`;
  }
  // no alt: captions carry the description visually, and WeChat exposes no
  // alternative text anyway.
  // vs canonical: no border-radius / box-shadow (flat, bordered images)
  return `<img src="${escapeAttribute(url)}" ${styleAttribute([
    ['display', 'block'],
    ['width', '100%'],
    ['border', `1px solid ${c.t.border}`],
  ])}>`;
}

// caption typography, without margin — hoistable onto a shared container
const CAPTION_TYPE: Array<[string, string]> = [
  ['font-size', '14px'],
  ['font-style', 'italic'],
];

// a styled div: WeChat ignores figure/figcaption semantics, and divs carry no
// UA margins to reset
function captionEl(text: string, c: Ctx, lean = false) {
  return `<div ${styleAttribute([
    ['margin', '8px 0 0'],
    ...(lean
      ? []
      : ([['color', c.t.muted], ...CAPTION_TYPE] as Array<[string, string]>)),
  ])}>${escapeHtml(text)}</div>`;
}

const MODULE_LABEL: Array<[string, string]> = [
  ['font-weight', '400'],
  LABEL_TRACKING,
];

// Section: heading box (kicker + number + title) beside a gap-driven copy
// column. Like the canonical, field-notes/editorial go two-column on wide
// screens via pure flex-wrap arithmetic (no media queries — WeChat strips
// them); at phone widths the columns wrap into today's stacked form. Brand is
// single-column at every width in the canonical too, so it carries no flex
// scaffold. Vertical rhythm (32px between sections, 16px heading gap from the
// row-gap, 12px paragraph gap) matches the canonical exactly.
function renderSection(kicker: string, number: number, source: string, c: Ctx) {
  const { t } = c;
  const isFieldNotes = c.layout === 'field-notes';
  const md = compileSectionMarkdown(source, t, c.layout);
  // brand/field-notes: kicker + number + title share a baseline row (wraps when
  // long); editorial: the canonical stacks them vertically
  // no align-items:baseline — kicker/number/title are close enough in size
  // that baseline vs stretch renders the same at these font sizes
  const headingBox: Array<[string, string | false]> = [
    ['display', 'flex'],
    ...(c.brand || isFieldNotes
      ? ([
          ['flex-wrap', 'wrap'],
          ['justify-content', c.brand ? 'space-between' : false],
          ['column-gap', '12px'],
        ] as Array<[string, string | false]>)
      : ([['flex-direction', 'column']] as Array<[string, string]>)),
    ...(c.brand
      ? ([
          ['margin', '0 0 16px'],
          ['padding', '12px 14px'],
          ['border-left', `4px solid ${t.accent}`],
          ['border-radius', '0 8px 8px 0'],
          ['background', t.soft],
        ] as Array<[string, string]>)
      : isFieldNotes
        ? ([
            ['flex', '1 1 120px'],
            ['min-width', '120px'],
          ] as Array<[string, string]>)
        : ([
            ['flex', '1 1 200px'],
            ['min-width', '160px'],
            ['padding-top', '12px'],
            ['border-top', `3px solid ${t.accent}`],
          ] as Array<[string, string]>)),
  ];
  const label = (text: string, color: string) =>
    `<span ${styleAttribute([...MODULE_LABEL, ['color', color]])}>${escapeHtml(text)}</span>`;
  const headingHtml = `<div ${styleAttribute(headingBox)}>${label(
    kicker.toUpperCase(),
    t.accent
  )}${label(String(number).padStart(2, '0'), c.brand ? t.accent : t.muted)}${md.heading}</div>`;
  const copyHtml = `<div ${styleAttribute([
    ['display', 'grid'],
    ['gap', '12px'],
    ...(c.brand
      ? ([['margin', '0 0 32px']] as Array<[string, string]>)
      : ([
          ['flex', isFieldNotes ? '3 1 360px' : '2 1 360px'],
          ['min-width', '0'],
        ] as Array<[string, string]>)),
  ])}>${md.body}</div>`;
  if (c.brand) return `${headingHtml}${copyHtml}`;
  // align-items:flex-start is load-bearing: without it the heading column
  // stretches to the copy's height, and the field-notes heading box (a
  // wrapping flex row) then spreads its kicker and title lines apart via
  // align-content:stretch
  const rootStyles: Array<[string, string]> = [
    ['display', 'flex'],
    ['flex-wrap', 'wrap'],
    ['align-items', 'flex-start'],
    ['gap', '16px 24px'],
    ['margin', '0 0 32px'],
  ];
  if (isFieldNotes)
    rootStyles.push(
      ['padding-top', '16px'],
      ['border-top', `1px solid ${t.border}`]
    );
  return `<div ${styleAttribute(rootStyles)}>${headingHtml}${copyHtml}</div>`;
}

export function compileWxPostForWechat(
  request: WxPostCompileRequest
): WxPostCompileResult {
  const { renderDocument: article, presentation, context } = request;
  const t = presentationTokens({ ...presentation, appearance: 'light' }); // WeChat is light-only
  const c: Ctx = {
    ctx: context,
    t,
    layout: presentation.layout,
    brand: presentation.layout === 'brand-default',
  };
  const mediaById = new Map(
    article.media.filter((m) => m.include).map((m) => [m.id, m])
  );

  // ---- header (per-layout; field-notes/editorial keep the canonical's
  // wide-screen columns via flex-wrap — cost-free on WeChat, whose sanitizer
  // strips the header entirely and surfaces title/author/digest natively) ----
  const publisher =
    article.byline || context.publisherName || 'SoarHigh Toastmasters';
  const topBorder: Array<[string, string]> =
    presentation.palette === 'brand-blue'
      ? [
          ['border-top', '4px solid transparent'],
          [
            'border-image',
            `linear-gradient(90deg,${t.accent},${t.accentSecondary}) 1`,
          ],
        ]
      : presentation.palette === 'warm-terracotta'
        ? [['border-top', `4px solid ${t.accent}`]]
        : [['border-top', `1px solid ${t.text}`]];
  const spread = (extra: Array<[string, string]>) =>
    styleAttribute([
      ['display', 'flex'],
      ['flex-wrap', 'wrap'],
      ['justify-content', 'space-between'],
      ['gap', '8px'],
      ['color', t.muted],
      ...extra,
    ]);
  const metaContext = c.layout === 'field-notes' ? null : context.contextLabel;
  const meta = `<div ${spread([
    ['letter-spacing', '0.08em'],
    ['margin-bottom', '16px'],
  ])}><span>${escapeHtml(
    articleTypeLabel(article).toUpperCase()
  )}</span>${metaContext ? `<span>${escapeHtml(metaContext.toUpperCase())}</span>` : ''}</div>`;
  const heroMark =
    c.layout === 'field-notes' && context.contextLabel
      ? `<div ${styleAttribute([['flex', '1 1 120px'], ['min-width', '120px'], ['color', t.muted], LABEL_TRACKING])}>${escapeHtml(
          context.contextLabel.toUpperCase()
        )}</div>`
      : '';
  const title = `<h1 ${styleAttribute([
    ['margin', '0 0 16px'],
    ['color', t.text],
    ['font-family', t.titleFont],
    ['font-size', '24px'],
    ['font-weight', '500'],
    ['line-height', '1.35'],
    ['letter-spacing', '-0.02em'],
  ])}>${escapeHtml(article.title)}</h1>`;
  const deck = article.excerpt
    ? `<p ${styleAttribute([
        ['margin', '0 0 16px'],
        ['color', t.muted],
      ])}>${escapeHtml(article.excerpt)}</p>`
    : '';
  const foot = `<div ${spread([])}><span>${escapeHtml(publisher)}</span>${
    context.displayDate ? `<span>${escapeHtml(context.displayDate)}</span>` : ''
  }</div>`;
  const headerChrome: Array<[string, string]> = [
    ...topBorder,
    ['border-bottom', `1px solid ${t.border}`],
    ['margin', '0 0 32px'],
  ];
  const header = c.brand
    ? `<header ${styleAttribute([['display', 'block'], ['padding', '24px 0'], ...headerChrome])}>${meta}${title}${deck}${foot}</header>`
    : c.layout === 'field-notes'
      ? `<header ${styleAttribute([
          ['display', 'flex'],
          ['flex-wrap', 'wrap'],
          ['gap', '16px 24px'],
          ['padding', '12px 0 24px'],
          ...headerChrome,
        ])}>${heroMark}<div ${styleAttribute([
          ['flex', '3 1 360px'],
          ['min-width', '0'],
        ])}>${meta}${title}${deck}${foot}</div></header>`
      : `<header ${styleAttribute([
          ['display', 'flex'],
          ['flex-wrap', 'wrap'],
          ['align-items', 'flex-end'],
          ['gap', '18px 24px'],
          ['padding', '0 0 24px'],
          ...headerChrome,
        ])}><div ${styleAttribute([
          ['flex', '2 1 320px'],
          ['min-width', '0'],
        ])}>${meta}${title}${foot}</div>${
          deck
            ? `<div ${styleAttribute([
                ['flex', '1 1 220px'],
                ['min-width', '0'],
                ['padding-left', '16px'],
                ['border-left', `1px solid ${t.border}`],
              ])}>${deck}</div>`
            : ''
        }</header>`;

  // ---- body ----
  const parts: string[] = [];
  let sectionNumber = 0;
  for (let i = 0; i < article.body.length; i += 1) {
    const node = article.body[i];
    if (node.kind === 'directive' && node.name === 'section') {
      const next = article.body[i + 1];
      if (next?.kind === 'markdown') {
        sectionNumber += 1;
        parts.push(
          renderSection(node.payload.kicker, sectionNumber, next.source, c)
        );
        i += 1;
        continue;
      }
    }
    if (node.kind === 'directive') {
      parts.push(renderDirective(node, mediaById, c));
      continue;
    }
    parts.push(
      `<div ${styleAttribute([['margin', '0 0 32px']])}>${compileMarkdown(node.source, t, { layout: c.layout })}</div>`
    );
  }

  const inner = compactStyles(shortenFonts(`${header}${parts.join('')}`), t);
  const html = `<article data-wxpost-emitter="wechat" ${styleAttribute([
    ['box-sizing', 'border-box'],
    ['max-width', layoutWidth(c.layout)],
    ['margin', '0 auto'],
    ['padding', '29.44px clamp(12px,calc(5.0405% - 7.6578px),29.44px)'],
    ['border', `1px solid ${t.border}`],
    ['background', t.background],
    ['color', t.text],
    ['font', `430 16px/1.85 ${shortFont(t.bodyFont)}`],
  ])}>${inner}</article>`;

  return { renderVersion: 1, html };
}

// field-notes indents text modules 18px (layoutModuleInset); media modules
// (image/gallery/video) stay full-bleed like the canonical
const moduleMargin = (c: Ctx) =>
  c.layout === 'field-notes' ? '0 0 32px 18px' : '0 0 32px';
const sectionWrap = (body: string, c: Ctx, fullBleed = false) =>
  `<section ${styleAttribute([['margin', fullBleed ? '0 0 32px' : moduleMargin(c)]])}>${body}</section>`;

function renderDirective(
  node: WxPostDirectiveNode,
  mediaById: Map<string, WxPostMediaAsset>,
  c: Ctx
): string {
  const { t } = c;
  switch (node.name) {
    case 'gallery': {
      // vs canonical: no scroll-snap (plain horizontal scroll); caption
      // typography lives once on the strip and inherits into figcaptions
      const figures = node.payload.items
        .map((id) => mediaById.get(id))
        .filter((m): m is WxPostMediaAsset => Boolean(m))
        // figure, not div: the backend sanitizer injects font-size:0 into any
        // <div> that directly wraps an <img>, which would zero the inherited
        // caption size on WeChat. scroll-snap keeps slides (and their
        // captions) pinned to the container edge after a swipe.
        .map(
          (m) =>
            `<figure ${styleAttribute([
              ['flex', '0 0 100%'],
              ['margin', '0'],
              ['scroll-snap-align', 'start'],
            ])}>${imageMarkup(m, c)}${captionEl(m.description, c, true)}</figure>`
        )
        .join('');
      const cap = node.payload.caption ? heading(node.payload.caption, t) : '';
      return sectionWrap(
        `${moduleLabel('Gallery', t)}${cap}<div ${styleAttribute([
          ['display', 'flex'],
          ['gap', '12px'],
          ['overflow', 'auto'],
          ['scroll-snap-type', 'x mandatory'],
          ['color', t.muted],
          ...CAPTION_TYPE,
        ])}>${figures}</div>`,
        c,
        true
      );
    }
    case 'image': {
      const media = mediaById.get(node.payload.media);
      if (!media) return '';
      const cap = node.payload.caption ?? media.description;
      return `<figure ${styleAttribute([['margin', '0 0 32px']])}>${imageMarkup(media, c)}${cap ? captionEl(cap, c) : ''}</figure>`;
    }
    case 'video': {
      const media = mediaById.get(node.payload.media);
      const url = assetUrl(media, c.ctx);
      const vid =
        media?.kind === 'video' && url
          ? `<video controls preload="metadata"${
              media.posterUrl
                ? ` poster="${escapeAttribute(safeUrl(media.posterUrl, { allowBlob: true }))}"`
                : ''
            } ${styleAttribute([
              ['display', 'block'],
              ['width', '100%'],
              ['background', '#000000'],
            ])}><source src="${escapeAttribute(url)}"></video>`
          : `<div ${styleAttribute([
              ['padding', '16px'],
              ['border', `1px solid ${t.border}`],
              ['background', t.soft],
              ['color', t.muted],
              ['text-align', 'center'],
            ])}>Missing video</div>`;
      return sectionWrap(
        `${moduleLabel('Video', t)}${node.payload.caption ? heading(node.payload.caption, t) : ''}${vid}${
          media ? captionEl(media.description, c) : ''
        }`,
        c,
        true
      );
    }
    case 'takeaway': {
      const box: Array<[string, string]> = c.brand
        ? [
            ['margin', '0 0 32px'],
            ['padding', '16px'],
            ['border-left', `3px solid ${t.accent}`],
            ['border-radius', '0 8px 8px 0'],
            ['background', t.soft],
          ]
        : c.layout === 'editorial-feature'
          ? [
              ['margin', '0 0 32px'],
              ['padding', '20px 0'],
              ['border-top', `1px solid ${t.border}`],
              ['border-bottom', `1px solid ${t.border}`],
              ['text-align', 'center'],
            ]
          : [
              ['margin', moduleMargin(c)],
              ['padding-left', '16px'],
              ['border-left', `3px solid ${t.accent}`],
            ];
      return `<section ${styleAttribute(box)}>${moduleLabel('Takeaway', t)}${
        node.payload.title ? heading(node.payload.title, t) : ''
      }<p ${styleAttribute([
        ['margin', '0'],
        ['color', t.text],
      ])}>${escapeHtml(node.payload.text)}</p></section>`;
    }
    case 'person': {
      const media = node.payload.media
        ? mediaById.get(node.payload.media)
        : undefined;
      const portrait = node.payload.media ? imageMarkup(media, c) : '';
      const copy = `${heading(node.payload.name, t)}${
        node.payload.role
          ? `<p ${styleAttribute([
              ['margin', '0 0 8px'],
              ['color', t.muted],
              ['font-size', '14px'],
              ['font-style', 'italic'],
            ])}>${escapeHtml(node.payload.role)}</p>`
          : ''
      }${
        node.payload.summary
          ? `<p ${styleAttribute([
              ['margin', '8px 0 0'],
              ['color', t.text],
            ])}>${escapeHtml(node.payload.summary)}</p>`
          : ''
      }${
        node.payload.quote
          ? `<blockquote ${styleAttribute([
              ['margin', '12px 0 0'],
              ['padding-left', '12px'],
              ['border-left', `2px solid ${t.accent}`],
              ['color', t.muted],
            ])}>“${escapeHtml(node.payload.quote)}”</blockquote>`
          : ''
      }`;
      // portrait beside copy on wide screens (canonical column arithmetic:
      // 1 1 180px / 2 1 260px wraps to stacked at phone widths). figure, not
      // div, so the sanitizer's wrapper injection doesn't target it.
      const inner = `${moduleLabel('Profile', t)}${
        portrait
          ? `<div ${styleAttribute([
              ['display', 'flex'],
              ['flex-wrap', 'wrap'],
              ['gap', '20px'],
            ])}><figure ${styleAttribute([
              ['flex', '1 1 180px'],
              ['min-width', '0'],
              ['margin', '0'],
            ])}>${portrait}</figure><div ${styleAttribute([
              ['flex', '2 1 260px'],
              ['min-width', '0'],
            ])}>${copy}</div></div>`
          : copy
      }`;
      const box: Array<[string, string]> = c.brand
        ? [
            ['margin', '0 0 32px'],
            ['padding', '16px'],
            ['border', `1px solid ${t.border}`],
            ['border-radius', '8px'],
            ['background', t.soft],
          ]
        : [['margin', moduleMargin(c)]];
      return `<section ${styleAttribute(box)}>${inner}</section>`;
    }
    case 'info-grid': {
      const items = node.payload.items
        .map(
          (item) =>
            `<div ${styleAttribute([
              ['flex', '1 1 140px'],
              ['min-width', '0'],
            ])}><span ${styleAttribute([
              ['display', 'block'],
              ['color', t.muted],
            ])}>${escapeHtml(item.label)}</span><strong ${styleAttribute([
              ['color', t.text],
              ['font-weight', '600'],
            ])}>${escapeHtml(item.value)}</strong></div>`
        )
        .join('');
      return sectionWrap(
        `${moduleLabel('At a glance', t)}${node.payload.title ? heading(node.payload.title, t) : ''}<div ${styleAttribute(
          [
            ['display', 'flex'],
            ['flex-wrap', 'wrap'],
            ['gap', '16px'],
            ['padding', c.brand ? '16px' : '16px 0'],
            ['border-top', `1px solid ${t.border}`],
            ['border-bottom', `1px solid ${t.border}`],
            ['background', c.brand ? t.soft : 'transparent'],
          ]
        )}>${items}</div>`,
        c
      );
    }
    case 'timeline': {
      const items = node.payload.items
        .map(
          (item, index) =>
            `<div ${styleAttribute([
              ['display', 'flex'],
              ['flex-wrap', 'wrap'],
              ['gap', '8px 16px'],
              ['padding', '14px 0'],
              ['border-top', index > 0 ? `1px solid ${t.border}` : false],
            ])}><strong ${styleAttribute([
              ['flex', '0 1 80px'],
              ['color', c.layout === 'field-notes' ? t.accent : t.muted],
              LABEL_TRACKING,
            ])}>${escapeHtml(item.label.toUpperCase())}</strong><div ${styleAttribute(
              [
                ['flex', '1 1 220px'],
                ['min-width', '0'],
              ]
            )}><strong ${styleAttribute([
              ['color', t.text],
              ['font-weight', '600'],
            ])}>${escapeHtml(item.title)}</strong>${
              item.description
                ? `<p ${styleAttribute([
                    ['margin', '4px 0 0'],
                    ['color', t.text],
                  ])}>${escapeHtml(item.description)}</p>`
                : ''
            }</div></div>`
        )
        .join('');
      return sectionWrap(
        `${moduleLabel('Timeline', t)}${node.payload.title ? heading(node.payload.title, t) : ''}<div ${styleAttribute(
          [
            ['padding-left', '16px'],
            ['border-left', `1px solid ${t.border}`],
          ]
        )}>${items}</div>`,
        c
      );
    }
    case 'pull-quote': {
      const box: Array<[string, string]> = [
        ['margin', '0 0 32px'],
        ['max-width', c.layout === 'editorial-feature' ? '544px' : 'none'],
        [
          'margin-left',
          c.layout === 'editorial-feature'
            ? 'auto'
            : c.layout === 'field-notes'
              ? '18px'
              : '0',
        ],
        ['margin-right', c.layout === 'editorial-feature' ? 'auto' : '0'],
        ['padding', '20px 0'],
        ['border-top', `1px solid ${t.border}`],
        ['border-bottom', `1px solid ${t.border}`],
        ['text-align', 'center'],
      ];
      return `<section ${styleAttribute(box)}>${moduleLabel('Quote', t)}<blockquote ${styleAttribute(
        [
          ['margin', '0'],
          ['color', t.text],
          ['font-family', t.titleFont],
          ['font-size', '20px'],
          ['line-height', '1.45'],
        ]
      )}>“${escapeHtml(node.payload.text)}”</blockquote>${
        node.payload.attribution
          ? `<p ${styleAttribute([
              ['margin', '10px 0 0'],
              ['color', t.muted],
            ])}>— ${escapeHtml(node.payload.attribution)}</p>`
          : ''
      }</section>`;
    }
    default:
      return '';
  }
}
