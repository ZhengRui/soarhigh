export const ARTICLE_TYPES = [
  'meeting-recap',
  'member-story',
  'event-preview',
  'meeting-review',
  'action-guide',
  'custom',
] as const;

export type WxPostArticleType = (typeof ARTICLE_TYPES)[number];

export const WXPOST_LAYOUTS = [
  'brand-default',
  'field-notes',
  'editorial-feature',
] as const;
export const WXPOST_PALETTES = [
  'brand-blue',
  'paper-neutral',
  'warm-terracotta',
] as const;
export const WXPOST_APPEARANCES = ['light', 'dark'] as const;
export const WXPOST_TYPEFACES = [
  'modern-sans',
  'editorial-serif',
  'humanist-mix',
] as const;
export const WXPOST_PREVIEW_SIZES = ['mobile-390', 'desktop-760'] as const;

export type WxPostLayout = (typeof WXPOST_LAYOUTS)[number];
export type WxPostPalette = (typeof WXPOST_PALETTES)[number];
export type WxPostAppearance = (typeof WXPOST_APPEARANCES)[number];
export type WxPostTypeface = (typeof WXPOST_TYPEFACES)[number];
export type WxPostPreviewSize = (typeof WXPOST_PREVIEW_SIZES)[number];

export interface WxPostPresentation {
  layout: WxPostLayout;
  palette: WxPostPalette;
  appearance: WxPostAppearance;
  typeface: WxPostTypeface;
}

export interface WxPostMediaAsset {
  id: string;
  kind: 'image' | 'video';
  sourceUrl: string;
  posterUrl?: string | null;
  description: string;
  credit?: string | null;
  people?: string[];
  include: boolean;
  order: number;
  descriptionSource: 'user' | 'ai';
  descriptionStatus: 'confirmed' | 'needs_confirmation';
}

export interface WxPostArticleMetadata {
  schemaVersion: 1;
  title: string;
  slug?: string | null;
  excerpt?: string | null;
  byline?: string | null;
  articleType: WxPostArticleType;
  customArticleType?: string | null;
  /** Opaque association ID. Resolve user-facing meeting copy separately. */
  sourceMeetingId?: string | null;
  media: WxPostMediaAsset[];
  coverMediaId?: string | null;
  presentation: WxPostPresentation;
}

export interface WxPostRenderDocument extends WxPostArticleMetadata {
  renderVersion: 1;
  body: WxPostBodyNode[];
}

export interface WxPostPublicDetail {
  id: string;
  slug: string;
  is_public: true;
  article_revision: number;
  context_label: string;
  created_at: string;
  updated_at: string;
  render_document: WxPostRenderDocument;
}

export interface GalleryDirectivePayload {
  items: string[];
  caption?: string;
}

export interface VideoDirectivePayload {
  media: string;
  caption?: string;
}

export interface TakeawayDirectivePayload {
  text: string;
  title?: string;
}

export interface PersonDirectivePayload {
  name: string;
  role?: string;
  media?: string;
  summary?: string;
  quote?: string;
}

export interface InfoGridDirectivePayload {
  title?: string;
  items: Array<{
    label: string;
    value: string;
  }>;
}

export interface TimelineDirectivePayload {
  title?: string;
  items: Array<{
    label: string;
    title: string;
    description?: string;
  }>;
}

export interface PullQuoteDirectivePayload {
  text: string;
  attribution?: string;
}

export interface WxPostDirectivePayloadMap {
  gallery: GalleryDirectivePayload;
  video: VideoDirectivePayload;
  takeaway: TakeawayDirectivePayload;
  person: PersonDirectivePayload;
  'info-grid': InfoGridDirectivePayload;
  timeline: TimelineDirectivePayload;
  'pull-quote': PullQuoteDirectivePayload;
}

export type WxPostDirectiveName = keyof WxPostDirectivePayloadMap;

export type WxPostDirectiveNode = {
  [Name in WxPostDirectiveName]: {
    kind: 'directive';
    name: Name;
    payload: WxPostDirectivePayloadMap[Name];
    line: number;
  };
}[WxPostDirectiveName];

export interface WxPostMarkdownNode {
  kind: 'markdown';
  source: string;
  line: number;
}

export type WxPostBodyNode = WxPostMarkdownNode | WxPostDirectiveNode;
