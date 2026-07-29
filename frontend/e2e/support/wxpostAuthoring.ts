import { expect, type Page } from '@playwright/test';

import {
  MEETING_462,
  MEETING_461,
  MEETING_449,
  FIRST_FILE_KEY,
  MEETING_OPTIONS,
} from './wxpostFixtures';

export {
  MEETING_462,
  MEETING_461,
  MEETING_449,
  FIRST_SOURCE_KEY,
  FIRST_FILE_KEY,
  MEETING_OPTIONS,
} from './wxpostFixtures';

export type WorkspaceManifest = {
  schemaVersion: 3;
  workspaceId: string;
  manifestVersion: number;
  nextMaterialNumber: number;
  createdBy: { id: string; name: string };
  createdAt: string;
  updatedAt: string;
  meetingId: string | null;
  draft: null;
  editorial: {
    articleType: string;
    customArticleType: string | null;
    writingApproach: 'chronological';
    transcript: string;
    extraNotes: string;
    writingGuidance: string;
  };
  sources: Array<{
    id: string;
    kind: 'image' | 'video';
    origin:
      | { type: 'meeting-library'; fileKey: string }
      | { type: 'web-upload' };
    filename: string;
    mimeType: string;
    sizeBytes: number;
    workspaceReady: boolean;
    included: boolean;
    description: string;
    descriptionSource: 'user' | null;
    descriptionStatus: 'confirmed' | 'missing';
  }>;
};

export type WorkspaceMock = {
  contexts: Map<
    string,
    { workspaceId: string; manifest: WorkspaceManifest; draft: null }
  >;
  requests: string[];
  conflictNextMutation: boolean;
  contextDelayMs: number;
  referencedSourceIds: Set<string>;
};

export function meetingSources(
  meetingId: string | null,
  firstMaterialNumber = 1
): WorkspaceManifest['sources'] {
  const media =
    meetingId === 'meeting-462'
      ? [
          ['meeting-room.jpg', 'image', FIRST_FILE_KEY],
          ['group-photo.jpg', 'image', 'meetings/462/group-photo.jpg'],
          ['closing-video.mp4', 'video', 'meetings/462/closing-video.mp4'],
        ]
      : meetingId === 'meeting-461'
        ? [['workshop-stage.jpg', 'image', 'meetings/461/workshop-stage.jpg']]
        : [];
  return media.map(([filename, kind, fileKey], index) => ({
    id: `M${String(firstMaterialNumber + index).padStart(2, '0')}`,
    kind: kind as 'image' | 'video',
    origin: { type: 'meeting-library' as const, fileKey },
    filename,
    mimeType: kind === 'image' ? 'image/jpeg' : 'video/mp4',
    sizeBytes: 100 + index,
    workspaceReady: false,
    included: false,
    description: '',
    descriptionSource: null,
    descriptionStatus: 'missing' as const,
  }));
}

export async function mockWxPostWorkspaceApi(
  page: Page
): Promise<WorkspaceMock> {
  const mock: WorkspaceMock = {
    contexts: new Map(),
    requests: [],
    conflictNextMutation: false,
    contextDelayMs: 0,
    referencedSourceIds: new Set(),
  };

  await page.route(/\/posts\/wxposts\/workspaces\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const marker = '/posts/wxposts/workspaces/';
    const suffix = url.pathname.slice(
      url.pathname.indexOf(marker) + marker.length
    );
    const [encodedWorkspaceId, ...parts] = suffix.split('/');
    const workspaceId = decodeURIComponent(encodedWorkspaceId);
    const method = request.method();
    mock.requests.push(`${method} /${parts.join('/')}`);

    if (method === 'PUT' && parts.length === 0) {
      const input = request.postDataJSON() as {
        meetingId: string | null;
        editorial: WorkspaceManifest['editorial'];
      };
      const existing = mock.contexts.get(workspaceId);
      const context =
        existing ??
        ({
          workspaceId,
          manifest: {
            schemaVersion: 3,
            workspaceId,
            manifestVersion: 1,
            nextMaterialNumber: meetingSources(input.meetingId).length + 1,
            createdBy: { id: 'member-123', name: 'Test Member' },
            createdAt: '2026-07-29T03:00:00Z',
            updatedAt: '2026-07-29T03:00:00Z',
            meetingId: input.meetingId,
            draft: null,
            editorial: input.editorial,
            sources: meetingSources(input.meetingId),
          },
          draft: null,
        } as const);
      mock.contexts.set(workspaceId, context);
      await route.fulfill({ status: 200, json: context });
      return;
    }

    let context = mock.contexts.get(workspaceId);
    if (!context) {
      context = {
        workspaceId,
        manifest: {
          schemaVersion: 3,
          workspaceId,
          manifestVersion: 4,
          nextMaterialNumber: 4,
          createdBy: { id: 'member-123', name: 'Test Member' },
          createdAt: '2026-07-29T03:00:00Z',
          updatedAt: '2026-07-29T03:15:00Z',
          meetingId: 'meeting-462',
          draft: null,
          editorial: {
            articleType: 'meeting-recap',
            customArticleType: null,
            writingApproach: 'chronological',
            transcript: '',
            extraNotes: '',
            writingGuidance: '',
          },
          sources: meetingSources('meeting-462'),
        },
        draft: null,
      };
      mock.contexts.set(workspaceId, context);
    }

    if (method === 'PATCH' && parts.length === 0) {
      const input = request.postDataJSON() as {
        expectedManifestVersion: number;
        meetingId: string | null;
        editorial: WorkspaceManifest['editorial'];
      };
      if (input.expectedManifestVersion !== context.manifest.manifestVersion) {
        await route.fulfill({
          status: 409,
          json: {
            error: {
              code: 'version_conflict',
              message: 'manifest changed',
              actualVersion: context.manifest.manifestVersion,
            },
          },
        });
        return;
      }
      const manifest = context.manifest;
      if (manifest.meetingId !== input.meetingId) {
        const uploads = manifest.sources.filter(
          (source) => source.origin.type !== 'meeting-library'
        );
        const replacements = meetingSources(
          input.meetingId,
          manifest.nextMaterialNumber
        );
        manifest.sources = [...uploads, ...replacements];
        manifest.nextMaterialNumber += replacements.length;
        manifest.meetingId = input.meetingId;
      }
      manifest.editorial = input.editorial;
      manifest.manifestVersion += 1;
      await route.fulfill({ status: 200, json: context });
      return;
    }

    if (method === 'GET' && parts[0] === 'context') {
      if (mock.contextDelayMs > 0) {
        await new Promise((resolve) =>
          setTimeout(resolve, mock.contextDelayMs)
        );
      }
      await route.fulfill({ status: 200, json: context });
      return;
    }
    if (method === 'GET' && parts[2] === 'content') {
      await route.fulfill({
        status: 200,
        contentType: 'image/png',
        body: Buffer.from(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
          'base64'
        ),
      });
      return;
    }
    if (method === 'GET' && parts[2] === 'delete-preflight') {
      const referenced = mock.referencedSourceIds.has(parts[1]);
      await route.fulfill({
        status: 200,
        json: {
          sourceId: parts[1],
          manifestVersion: context.manifest.manifestVersion,
          draftVersion: 0,
          referenced,
          requiresConfirmation: referenced,
          references: referenced ? ['media.0', 'coverMediaId'] : [],
        },
      });
      return;
    }

    if (mock.conflictNextMutation) {
      mock.conflictNextMutation = false;
      context.manifest.manifestVersion += 1;
      await route.fulfill({
        status: 409,
        json: {
          error: {
            code: 'version_conflict',
            message: 'manifest changed',
            actualVersion: context.manifest.manifestVersion,
          },
        },
      });
      return;
    }

    const manifest = context.manifest;
    if (method === 'POST' && parts[2] === 'import') {
      const source = manifest.sources.find((item) => item.id === parts[1])!;
      source.workspaceReady = true;
    } else if (method === 'PUT' && parts[2] === 'inclusion') {
      const source = manifest.sources.find((item) => item.id === parts[1])!;
      const input = request.postDataJSON() as { included: boolean };
      source.included = input.included;
      if (input.included) source.workspaceReady = true;
    } else if (method === 'PATCH' && parts[0] === 'sources') {
      const input = request.postDataJSON() as {
        updates: Array<{
          sourceId: string;
          moveToIndex?: number;
          description?: string;
          descriptionSource?: 'user' | null;
          descriptionStatus?: 'confirmed' | 'missing';
        }>;
      };
      for (const update of input.updates) {
        const index = manifest.sources.findIndex(
          (source) => source.id === update.sourceId
        );
        const source = manifest.sources[index];
        if (update.description !== undefined) {
          source.description = update.description;
          source.descriptionSource = update.descriptionSource ?? null;
          source.descriptionStatus = update.descriptionStatus ?? 'missing';
        }
        if (update.moveToIndex !== undefined) {
          manifest.sources.splice(index, 1);
          manifest.sources.splice(update.moveToIndex, 0, source);
        }
      }
    } else if (method === 'POST' && parts[0] === 'uploads') {
      const id = `M${String(manifest.nextMaterialNumber).padStart(2, '0')}`;
      const filename = url.searchParams.get('filename')!;
      const mimeType = request.headers()['content-type'];
      manifest.sources.push({
        id,
        kind: mimeType.startsWith('video/') ? 'video' : 'image',
        origin: { type: 'web-upload' },
        filename,
        mimeType,
        sizeBytes: request.postDataBuffer()?.length ?? 1,
        workspaceReady: true,
        included: false,
        description: '',
        descriptionSource: null,
        descriptionStatus: 'missing',
      });
      manifest.nextMaterialNumber += 1;
    } else if (method === 'DELETE' && parts[0] === 'sources') {
      const input = request.postDataJSON() as { confirmReferenced: boolean };
      if (mock.referencedSourceIds.has(parts[1]) && !input.confirmReferenced) {
        await route.fulfill({
          status: 409,
          json: { error: { code: 'confirmation_required' } },
        });
        return;
      }
      const source = manifest.sources.find((item) => item.id === parts[1])!;
      if (source.origin.type === 'meeting-library') {
        source.workspaceReady = false;
        source.included = false;
      } else {
        manifest.sources = manifest.sources.filter(
          (item) => item.id !== source.id
        );
      }
    } else {
      await route.fulfill({ status: 404, json: { detail: 'not mocked' } });
      return;
    }
    manifest.manifestVersion += 1;
    await route.fulfill({ status: 200, json: manifest });
  });

  return mock;
}

export async function mockAuthenticatedMember(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'wxpost-authoring-e2e-token');

    const removeItem = Storage.prototype.removeItem;
    Storage.prototype.removeItem = function removeItemForAuthoringTest(key) {
      if (key === 'token') return;
      removeItem.call(this, key);
    };
  });

  await page.route(/\/whoami$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        uid: 'member-e2e',
        username: 'e2e',
        full_name: 'WXPost E2E',
      },
    });
  });
}

export async function mockWxPostReadApis(page: Page) {
  await page.route(
    /\/meetings\/options\?page=(1|2|3)&page_size=50$/,
    async (route) => {
      const pageNumber = Number(
        new URL(route.request().url()).searchParams.get('page')
      );
      const pageStart = (pageNumber - 1) * 50;
      await route.fulfill({
        status: 200,
        json: {
          items: MEETING_OPTIONS.slice(pageStart, pageStart + 50).map(
            ({ id, no, type, theme, date }) => ({
              id,
              no,
              type,
              theme,
              date,
            })
          ),
          total: 101,
          page: pageNumber,
          page_size: 50,
          pages: 3,
        },
      });
    }
  );

  await page.route(/\/meetings\/meeting-462$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: MEETING_462,
    });
  });

  await page.route(/\/meetings\/meeting-461$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: MEETING_461,
    });
  });

  await page.route(/\/meetings\/meeting-449$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: MEETING_449,
    });
  });

  await page.route(/\/meetings\/meeting-462\/media$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: [
          {
            filename: 'meeting-room.jpg',
            url: '/images/toastmasters.png',
            fileKey: 'meetings/462/meeting-room.jpg',
            uploadedAt: '2026-07-15T12:00:00Z',
          },
          {
            filename: 'group-photo.jpg',
            url: '/images/toastmasters_excel.png',
            fileKey: 'meetings/462/group-photo.jpg',
            uploadedAt: '2026-07-15T12:01:00Z',
          },
          {
            filename: 'closing-video.mp4',
            url: 'https://example.com/closing-video.mp4',
            fileKey: 'meetings/462/closing-video.mp4',
            uploadedAt: '2026-07-15T12:02:00Z',
          },
        ],
      },
    });
  });

  await page.route(/\/meetings\/meeting-461\/media$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: [
          {
            filename: 'workshop-stage.jpg',
            url: '/images/toastmasters.png',
            fileKey: 'meetings/461/workshop-stage.jpg',
            uploadedAt: '2026-07-08T12:00:00Z',
          },
        ],
      },
    });
  });
}

export async function openAuthoringPage(page: Page) {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  const workspace = await mockWxPostWorkspaceApi(page);
  await page.goto('/posts/wxposts/new');
  await expect(
    page.getByRole('heading', { name: 'New WeChat Post' })
  ).toBeVisible();
  await expect(page.getByTestId('wxpost-drafts-link')).toHaveAttribute(
    'href',
    '/posts/wxposts/drafts'
  );
  await expect(page.getByTestId('wxpost-drafts-link')).toHaveCSS(
    'height',
    '36px'
  );
  await expect(
    page.getByRole('heading', { name: 'New WeChat Post' })
  ).toHaveCSS(
    'font-size',
    (page.viewportSize()?.width ?? 1280) >= 640 ? '36px' : '30px'
  );
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#462'
  );
  return workspace;
}
