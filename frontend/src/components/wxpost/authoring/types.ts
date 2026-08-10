import type {
  WorkspaceArticleType,
  WorkspaceCustomVoiceToneProfile,
  WorkspaceVoiceTonePreset,
  WorkspaceWritingApproach,
} from '@/utils/wxpostWorkspace';

export type WxPostAuthoringStage = 'setup' | 'materials' | 'draft';

export interface WxPostMaterial {
  sourceId: string;
  source: 'Meeting Library' | 'Web upload' | 'Feishu upload';
  kind: 'image' | 'video';
  previewUrl: string | null;
  previewLoading: boolean;
  filename: string;
  description: string;
  workspaceReady: boolean;
  contentSha256: string | null;
  included: boolean;
}

export interface WxPostMaterialWorkingState {
  included: boolean;
  description: string;
  descriptionSource: 'user' | 'ai' | null;
  descriptionStatus: 'confirmed' | 'needs_confirmation' | 'missing';
}

export interface WxPostMaterialsWorkingCopy {
  workspaceId: string;
  articleType: WorkspaceArticleType;
  customArticleType: string;
  writingApproach: WorkspaceWritingApproach;
  transcript: string;
  extraNotes: string;
  writingGuidance: string;
  voiceTonePresets: WorkspaceVoiceTonePreset[];
  customVoiceToneProfiles: WorkspaceCustomVoiceToneProfile[];
  sources: Record<string, WxPostMaterialWorkingState>;
}
