export const ARTICLE_TYPES = [
  'meeting-recap',
  'member-story',
  'event-preview',
  'meeting-review',
  'action-guide',
  'custom',
] as const;

export type WePostArticleType = (typeof ARTICLE_TYPES)[number];

export const WEPOST_LAYOUTS = [
  'brand-default',
  'field-notes',
  'editorial-feature',
] as const;
export const WEPOST_PALETTES = [
  'brand-blue',
  'paper-neutral',
  'warm-terracotta',
] as const;
export const WEPOST_APPEARANCES = ['light', 'dark'] as const;
export const WEPOST_TYPEFACES = [
  'modern-sans',
  'editorial-serif',
  'humanist-mix',
] as const;
export const WEPOST_PREVIEW_SIZES = ['mobile-390', 'desktop-760'] as const;

export type WePostLayout = (typeof WEPOST_LAYOUTS)[number];
export type WePostPalette = (typeof WEPOST_PALETTES)[number];
export type WePostAppearance = (typeof WEPOST_APPEARANCES)[number];
export type WePostTypeface = (typeof WEPOST_TYPEFACES)[number];
export type WePostPreviewSize = (typeof WEPOST_PREVIEW_SIZES)[number];

export interface WePostPresentation {
  layout: WePostLayout;
  palette: WePostPalette;
  appearance: WePostAppearance;
  typeface: WePostTypeface;
}

export interface WePostMediaAsset {
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

export interface WePostArticleMetadata {
  schemaVersion: 1;
  title: string;
  slug?: string | null;
  excerpt?: string | null;
  byline?: string | null;
  articleType: WePostArticleType;
  customArticleType?: string | null;
  /** Opaque association ID. Resolve user-facing meeting copy separately. */
  sourceMeetingId?: string | null;
  media: WePostMediaAsset[];
  coverMediaId?: string | null;
  presentation: WePostPresentation;
}

export interface WePostRenderDocument extends WePostArticleMetadata {
  renderVersion: 1;
  body: WePostBodyNode[];
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

export interface WePostDirectivePayloadMap {
  gallery: GalleryDirectivePayload;
  video: VideoDirectivePayload;
  takeaway: TakeawayDirectivePayload;
  person: PersonDirectivePayload;
  'info-grid': InfoGridDirectivePayload;
  timeline: TimelineDirectivePayload;
  'pull-quote': PullQuoteDirectivePayload;
}

export type WePostDirectiveName = keyof WePostDirectivePayloadMap;

export type WePostDirectiveNode = {
  [Name in WePostDirectiveName]: {
    kind: 'directive';
    name: Name;
    payload: WePostDirectivePayloadMap[Name];
    line: number;
  };
}[WePostDirectiveName];

export interface WePostMarkdownNode {
  kind: 'markdown';
  source: string;
  line: number;
}

export type WePostBodyNode = WePostMarkdownNode | WePostDirectiveNode;
