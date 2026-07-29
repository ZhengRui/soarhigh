const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT ?? '';

export type WorkspaceArticleType =
  | 'meeting-recap'
  | 'member-story'
  | 'event-preview'
  | 'meeting-review'
  | 'action-guide'
  | 'custom';

export interface WorkspaceEditorial {
  articleType: WorkspaceArticleType;
  customArticleType: string | null;
  writingApproach: 'chronological';
  transcript: string;
  extraNotes: string;
  writingGuidance: string;
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
  schemaVersion: 3;
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
  } | null;
  editorial: WorkspaceEditorial;
  sources: WorkspaceSource[];
}

export interface WorkspaceContext {
  workspaceId: string;
  manifest: WorkspaceManifest;
  draft: {
    draftVersion: number;
    document: Record<string, unknown>;
  } | null;
}

export interface WorkspaceDeletePreflight {
  sourceId: string;
  manifestVersion: number;
  draftVersion: number;
  referenced: boolean;
  requiresConfirmation: boolean;
  references: string[];
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
  hasDraft: boolean;
}

export interface WorkspaceSourceUpdate {
  sourceId: string;
  moveToIndex?: number;
  description?: string;
  descriptionSource?: 'user' | null;
  descriptionStatus?: 'confirmed' | 'missing';
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

export function updateWorkspace(
  workspaceId: string,
  input: {
    expectedManifestVersion: number;
    meetingId: string | null;
    editorial: WorkspaceEditorial;
  }
) {
  return requestJson<WorkspaceContext>(workspacePath(workspaceId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
}

export function getWorkspaceContext(workspaceId: string) {
  return requestJson<WorkspaceContext>(`${workspacePath(workspaceId)}/context`);
}

export function listWorkspaces() {
  return requestJson<{ items: WorkspaceSummary[] }>(
    '/posts/wxposts/workspaces'
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

export function setWorkspaceSourceIncluded(
  workspaceId: string,
  sourceId: string,
  expectedManifestVersion: number,
  included: boolean
) {
  return requestJson<WorkspaceManifest>(
    `${workspacePath(workspaceId)}/sources/${encodeURIComponent(sourceId)}/inclusion`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expectedManifestVersion,
        included,
      }),
    }
  );
}

export function updateWorkspaceSources(
  workspaceId: string,
  expectedManifestVersion: number,
  updates: WorkspaceSourceUpdate[]
) {
  return requestJson<WorkspaceManifest>(
    `${workspacePath(workspaceId)}/sources`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expectedManifestVersion,
        updates,
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
  sourceId: string
) {
  return requestJson<WorkspaceDeletePreflight>(
    `${workspacePath(workspaceId)}/sources/${encodeURIComponent(sourceId)}/delete-preflight`
  );
}

export function deleteWorkspaceSource(
  workspaceId: string,
  sourceId: string,
  expectedManifestVersion: number,
  confirmReferenced: boolean
) {
  return requestJson<WorkspaceManifest>(
    `${workspacePath(workspaceId)}/sources/${encodeURIComponent(sourceId)}`,
    {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expectedManifestVersion,
        confirmReferenced,
      }),
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
