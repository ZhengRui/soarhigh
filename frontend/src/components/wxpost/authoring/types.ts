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
  sourceKey: string;
  source: 'Meeting Library' | 'Web upload' | 'Feishu upload';
  kind: 'image' | 'video';
  url: string;
  filename: string;
  description: string;
  workspaceReady: boolean;
  uploading?: boolean;
  included: boolean;
}
