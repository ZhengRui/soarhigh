import type {
  WxPostArticleDocument,
  WxPostArticleType,
  WxPostRenderDocument,
} from '@/components/wxpost/types';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT ?? '';
const WORKSPACE_ID_PREFIX = 'wxpost-';

function workspaceEditorKey(workspaceId: string) {
  return workspaceId.startsWith(WORKSPACE_ID_PREFIX)
    ? workspaceId.slice(WORKSPACE_ID_PREFIX.length)
    : workspaceId;
}

export function workspaceEditorPath(workspaceId: string) {
  return `/posts/wxposts/edit/${encodeURIComponent(
    workspaceEditorKey(workspaceId)
  )}`;
}

export function workspaceDraftPreviewPath(workspaceId: string) {
  return `${workspaceEditorPath(workspaceId)}?view=preview`;
}

export function workspaceListPath(workspaceId: string | null) {
  if (!workspaceId) return '/posts/wxposts/workspaces?from=new';
  return `/posts/wxposts/workspaces?from=edit&workspace=${encodeURIComponent(
    workspaceEditorKey(workspaceId)
  )}`;
}

export function workspaceIdFromEditorKey(workspaceKey: string) {
  return `${WORKSPACE_ID_PREFIX}${workspaceKey}`;
}

export type WorkspaceArticleType = WxPostArticleType;

export type WorkspaceWritingApproach =
  | 'chronological'
  | 'theme-driven'
  | 'image-driven'
  | 'highlights-first';

export type WorkspaceVoiceTonePreset =
  | 'encouraging'
  | 'lightly-humorous'
  | 'heartfelt'
  | 'documentary'
  | 'reflective'
  | 'celebratory';

export interface WorkspaceCustomVoiceToneProfile {
  name: string;
  instruction: string;
  selected: boolean;
}

export interface WorkspaceVoiceTone {
  presets: WorkspaceVoiceTonePreset[];
  customProfiles: WorkspaceCustomVoiceToneProfile[];
}

export const WORKSPACE_ARTICLE_TYPE_LABELS: Record<
  WorkspaceArticleType,
  string
> = {
  'meeting-recap': 'Meeting Recap',
  'member-story': 'Member Story',
  'event-preview': 'Event Preview',
  'meeting-review': 'Meeting Review',
  'action-guide': 'Action Guide',
  custom: 'Custom',
};

export const WORKSPACE_WRITING_APPROACH_LABELS: Record<
  WorkspaceWritingApproach,
  string
> = {
  chronological: 'Chronological',
  'theme-driven': 'Theme-driven',
  'image-driven': 'Image-driven',
  'highlights-first': 'Highlights first',
};

export const WORKSPACE_VOICE_TONE_PRESETS: ReadonlyArray<{
  id: WorkspaceVoiceTonePreset;
  label: string;
  instruction: string;
}> = [
  {
    id: 'encouraging',
    label: 'Encouraging',
    instruction:
      'Use an uplifting, supportive voice that gives readers confidence and forward momentum.',
  },
  {
    id: 'lightly-humorous',
    label: 'Lightly humorous',
    instruction:
      'Add gentle, natural wit without turning people or meaningful moments into punchlines.',
  },
  {
    id: 'heartfelt',
    label: 'Heartfelt',
    instruction:
      'Write with warmth and emotional honesty while keeping the language specific and sincere.',
  },
  {
    id: 'documentary',
    label: 'Documentary',
    instruction:
      'Use a clear, observant voice grounded in concrete events, details, and verifiable facts.',
  },
  {
    id: 'reflective',
    label: 'Reflective',
    instruction:
      'Connect specific moments to thoughtful meaning without becoming abstract or overly solemn.',
  },
  {
    id: 'celebratory',
    label: 'Celebratory',
    instruction:
      'Highlight achievement and shared energy with lively language that remains credible and inclusive.',
  },
];

export interface WorkspaceEditorial {
  articleType: WorkspaceArticleType;
  customArticleType: string | null;
  writingApproach: WorkspaceWritingApproach;
  transcript: string;
  extraNotes: string;
  writingGuidance: string;
  voiceTone: WorkspaceVoiceTone;
}

export interface WorkspaceSource {
  id: string;
  kind: 'image' | 'video' | 'audio' | 'transcript' | 'document';
  origin:
    | { type: 'meeting-library'; fileKey: string }
    | { type: 'web-upload' | 'feishu-upload' };
  filename: string;
  mimeType: string;
  sizeBytes: number;
  workspaceReady: boolean;
  included: boolean;
  description: string;
  descriptionSource: 'user' | 'ai' | null;
  descriptionStatus: 'confirmed' | 'needs_confirmation' | 'missing';
}

export interface WorkspaceCreator {
  id: string;
  name: string;
}

export interface WorkspaceManifest {
  schemaVersion: 4;
  workspaceId: string;
  manifestVersion: number;
  nextMaterialNumber: number;
  createdBy: WorkspaceCreator;
  createdAt: string;
  updatedAt: string;
  meetingId: string | null;
  draft: {
    version: number;
    sourceManifestVersion: number;
    sha256: string;
    operationId?: string;
  } | null;
  editorial: WorkspaceEditorial;
  sources: WorkspaceSource[];
}

export interface WorkspaceContext {
  workspaceId: string;
  manifest: WorkspaceManifest;
  draft: {
    draftVersion: number;
    document: WxPostArticleDocument;
  } | null;
}

export interface WorkspaceDraftSession {
  workspaceId: string;
  sessionId: string | null;
  messages: Array<{ role: 'user' | 'assistant'; text: string }>;
}

interface WorkspaceDraftTurn {
  workspaceId: string;
  sessionId: string;
  reply: string;
  context: WorkspaceContext;
}

interface WxPostValidationResult {
  valid: true;
  document: WxPostArticleDocument;
  renderDocument: WxPostRenderDocument;
}

export interface WorkspaceDeletePreflight {
  sourceId: string;
  manifestVersion: number;
  draftVersion: number;
  blockedByDraft: boolean;
  references: string[];
}

export interface WorkspaceSourceUpdate {
  sourceId: string;
  included?: boolean;
  description?: string;
  descriptionSource?: WorkspaceSource['descriptionSource'];
  descriptionStatus?: WorkspaceSource['descriptionStatus'];
}

export interface WorkspaceSourceDescriptionSuggestion {
  workspaceId: string;
  sourceId: string;
  description: string;
}

export interface WorkspaceSummary {
  workspaceId: string;
  createdBy: WorkspaceCreator;
  createdAt: string;
  updatedAt: string;
  meetingId: string | null;
  articleType: WorkspaceArticleType;
  customArticleType: string | null;
  manifestVersion: number;
  sourceCount: number;
  readySourceCount: number;
  includedSourceCount: number;
  draftVersion: number | null;
  draftExcerpt: string | null;
  publication: WorkspacePublicationStatus;
}

export type WorkspacePublicationStatus = {
  state: 'unavailable' | 'not-synced' | 'up-to-date' | 'update-available';
  workspaceId: string;
  slug: string | null;
  publicRevision: number | null;
  sourceDraftVersion: number | null;
  currentDraftVersion: number | null;
  publishedAt: string | null;
  publicUrl: string | null;
};

export interface PaginatedWorkspaceSummaries {
  items: WorkspaceSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export class WorkspaceApiError extends Error {
  status: number;
  code: string | null;

  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.name = 'WorkspaceApiError';
    this.status = status;
    this.code = code;
  }
}

function memberHeaders(headers?: HeadersInit) {
  const result = new Headers(headers);
  const token = localStorage.getItem('token');
  if (!token) throw new WorkspaceApiError(401, 'Not authorized');
  result.set('Authorization', `Bearer ${token}`);
  return result;
}

async function errorFromResponse(response: Response) {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return new WorkspaceApiError(
      response.status,
      `Request failed (${response.status})`
    );
  }
  if (payload && typeof payload === 'object') {
    const value = payload as {
      detail?: unknown;
      error?: { code?: unknown; message?: unknown };
    };
    if (value.error && typeof value.error.message === 'string') {
      return new WorkspaceApiError(
        response.status,
        value.error.message,
        typeof value.error.code === 'string' ? value.error.code : null
      );
    }
    if (typeof value.detail === 'string') {
      return new WorkspaceApiError(response.status, value.detail);
    }
    if (Array.isArray(value.detail)) {
      const first = value.detail.find((item): item is { message: string } =>
        Boolean(
          item &&
            typeof item === 'object' &&
            'message' in item &&
            typeof item.message === 'string'
        )
      );
      if (first) return new WorkspaceApiError(response.status, first.message);
    }
    if (
      'errors' in value &&
      Array.isArray(value.errors) &&
      value.errors[0] &&
      typeof value.errors[0] === 'object' &&
      'message' in value.errors[0] &&
      typeof value.errors[0].message === 'string'
    ) {
      return new WorkspaceApiError(response.status, value.errors[0].message);
    }
  }
  return new WorkspaceApiError(
    response.status,
    `Request failed (${response.status})`
  );
}

async function requestJson<T>(path: string, init: RequestInit = {}) {
  const response = await fetch(`${apiEndpoint}${path}`, {
    ...init,
    headers: memberHeaders(init.headers),
  });
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as T;
}

function workspacePath(workspaceId: string) {
  return `/posts/wxposts/workspaces/${encodeURIComponent(workspaceId)}`;
}

export function bootstrapWorkspace(
  workspaceId: string,
  input: {
    meetingId: string | null;
    editorial: WorkspaceEditorial;
  }
) {
  return requestJson<WorkspaceContext>(workspacePath(workspaceId), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
}

export function getWorkspaceContext(workspaceId: string) {
  return requestJson<WorkspaceContext>(`${workspacePath(workspaceId)}/context`);
}

export function getWorkspacePublication(workspaceId: string) {
  return requestJson<WorkspacePublicationStatus>(
    `${workspacePath(workspaceId)}/publication`
  );
}

export function syncWorkspacePublication(
  workspaceId: string,
  input: {
    expectedManifestVersion: number;
    expectedDraftVersion: number;
    expectedPublicRevision: number | null;
  }
) {
  return requestJson<WorkspacePublicationStatus>(
    `${workspacePath(workspaceId)}/publication/sync`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }
  );
}

export function getWorkspaceDraftSession(workspaceId: string) {
  return requestJson<WorkspaceDraftSession>(
    `${workspacePath(workspaceId)}/draft/session`
  );
}

export function validateWorkspaceDraft(document: WxPostArticleDocument) {
  return requestJson<WxPostValidationResult>('/posts/wxposts/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(document),
  });
}

export function saveWorkspaceDraft(
  workspaceId: string,
  input: {
    expectedManifestVersion: number;
    expectedDraftVersion: number;
    document: WxPostArticleDocument;
  }
) {
  return requestJson<WorkspaceContext>(
    `${workspacePath(workspaceId)}/draft/save`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }
  );
}

export function generateWorkspaceDraft(
  workspaceId: string,
  input: {
    expectedManifestVersion: number;
    expectedDraftVersion: number;
  }
) {
  return requestJson<WorkspaceDraftTurn>(
    `${workspacePath(workspaceId)}/draft/generate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }
  );
}

export function reviseWorkspaceDraft(
  workspaceId: string,
  input: {
    expectedManifestVersion: number;
    expectedDraftVersion: number;
    message: string;
    selectedText: string | null;
  }
) {
  return requestJson<WorkspaceDraftTurn>(
    `${workspacePath(workspaceId)}/draft/chat`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }
  );
}

export function saveWorkspaceMaterials(
  workspaceId: string,
  input: {
    expectedManifestVersion: number;
    meetingId: string | null;
    editorial: WorkspaceEditorial;
    sourceUpdates: WorkspaceSourceUpdate[];
  }
) {
  return requestJson<WorkspaceContext>(workspacePath(workspaceId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
}

export function suggestWorkspaceVoiceToneInstruction(
  workspaceId: string,
  name: string
) {
  return requestJson<{ instruction: string }>(
    `${workspacePath(workspaceId)}/voice-tone/suggestion`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }
  );
}

export function listWorkspaces({
  page = 1,
  pageSize = 10,
}: {
  page?: number;
  pageSize?: number;
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return requestJson<PaginatedWorkspaceSummaries>(
    `/posts/wxposts/workspaces?${params.toString()}`
  );
}

export function deleteWorkspace(
  workspaceId: string,
  expectedManifestVersion: number
) {
  return requestJson<{ workspaceId: string; deleted: true }>(
    workspacePath(workspaceId),
    {
      method: 'DELETE',
      headers: {
        'X-Expected-Manifest-Version': String(expectedManifestVersion),
      },
    }
  );
}

export function importWorkspaceSource(
  workspaceId: string,
  sourceId: string,
  expectedManifestVersion: number
) {
  return requestJson<WorkspaceManifest>(
    `${workspacePath(workspaceId)}/sources/${encodeURIComponent(sourceId)}/import`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expectedManifestVersion,
      }),
    }
  );
}

export function suggestWorkspaceSourceDescription(
  workspaceId: string,
  sourceId: string,
  expectedManifestVersion: number,
  currentDescription: string
) {
  return requestJson<WorkspaceSourceDescriptionSuggestion>(
    `${workspacePath(workspaceId)}/sources/${encodeURIComponent(sourceId)}/description-suggestion`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expectedManifestVersion,
        currentDescription,
      }),
    }
  );
}

export function uploadWorkspaceSource(
  workspaceId: string,
  expectedManifestVersion: number,
  file: File
) {
  return requestJson<WorkspaceManifest>(
    `${workspacePath(workspaceId)}/uploads?filename=${encodeURIComponent(file.name)}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': file.type || 'application/octet-stream',
        'X-Expected-Manifest-Version': String(expectedManifestVersion),
      },
      body: file,
    }
  );
}

export function preflightWorkspaceSourceDelete(
  workspaceId: string,
  sourceId: string,
  expectedManifestVersion: number
) {
  return requestJson<WorkspaceDeletePreflight>(
    `${workspacePath(workspaceId)}/sources/${encodeURIComponent(sourceId)}/delete-preflight`,
    {
      headers: {
        'X-Expected-Manifest-Version': String(expectedManifestVersion),
      },
    }
  );
}

export function deleteWorkspaceSource(
  workspaceId: string,
  sourceId: string,
  expectedManifestVersion: number
) {
  return requestJson<WorkspaceManifest>(
    `${workspacePath(workspaceId)}/sources/${encodeURIComponent(sourceId)}`,
    {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expectedManifestVersion }),
    }
  );
}

export async function getWorkspaceSourceContent(
  workspaceId: string,
  sourceId: string
) {
  const response = await fetch(
    `${apiEndpoint}${workspacePath(workspaceId)}/sources/${encodeURIComponent(sourceId)}/content`,
    { headers: memberHeaders() }
  );
  if (!response.ok) throw await errorFromResponse(response);
  return response.blob();
}
