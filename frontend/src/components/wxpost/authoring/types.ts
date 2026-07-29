export type WxPostAuthoringStage = 'setup' | 'materials';

export type WxPostArticleType =
  | 'Meeting Recap'
  | 'Member Story'
  | 'Event Preview'
  | 'Meeting Review'
  | 'Action Guide'
  | 'Custom';

export type WxPostWritingApproach =
  | 'Chronological'
  | 'Theme-driven'
  | 'Image-driven'
  | 'Highlights first';

export interface WxPostMaterial {
  sourceId: string;
  source: 'Meeting Library' | 'Web upload' | 'Feishu upload';
  kind: 'image' | 'video';
  previewUrl: string | null;
  filename: string;
  description: string;
  workspaceReady: boolean;
  included: boolean;
}
