import { expect, test } from '@playwright/test';

import {
  MEETING_OPTIONS,
  mockAuthenticatedMember,
  mockWxPostReadApis,
  mockWxPostWorkspaceApi,
} from './support/wxpostAuthoring';
import type { WorkspaceSummary } from '../src/utils/wxpostWorkspace';

const WORKSPACES_API_URL =
  /^http:\/\/localhost:5000\/posts\/wxposts\/workspaces(?:\?.*)?$/;

function workspaceSummary(
  workspaceId: string,
  overrides: Partial<WorkspaceSummary> = {}
): WorkspaceSummary {
  return {
    workspaceId,
    createdBy: { id: 'member-123', name: 'Test Member' },
    createdAt: '2026-07-29T03:00:00Z',
    updatedAt: '2026-07-29T03:15:00Z',
    meetingId: null,
    articleType: 'custom',
    customArticleType: null,
    manifestVersion: 1,
    sourceCount: 0,
    readySourceCount: 0,
    includedSourceCount: 0,
    draftVersion: null,
    draftExcerpt: null,
    publication: {
      state: 'not-synced',
      workspaceId,
      slug: null,
      publicRevision: null,
      sourceDraftVersion: null,
      currentDraftVersion: null,
      publishedAt: null,
      publicUrl: null,
    },
    ...overrides,
  };
}

function workspacePage(
  items: WorkspaceSummary[],
  {
    total = items.length,
    page = 1,
    pageSize = 10,
  }: { total?: number; page?: number; pageSize?: number } = {}
) {
  return {
    items,
    total,
    page,
    page_size: pageSize,
    pages: total > 0 ? Math.ceil(total / pageSize) : 1,
  };
}

test('keeps the workspaces page aligned with the new WxPost page', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await page.route(WORKSPACES_API_URL, async (route) => {
    await route.fulfill({ status: 200, json: workspacePage([]) });
  });

  await page.goto('/posts/wxposts/new');
  const newPageShell = await page
    .getByTestId('wxpost-page-shell')
    .boundingBox();
  const newPageBackLink = await page
    .getByRole('link', { name: 'Back to Posts' })
    .boundingBox();

  await expect(page.getByTestId('wxpost-workspaces-link')).toHaveAttribute(
    'href',
    '/posts/wxposts/workspaces?from=new'
  );
  await page.getByTestId('wxpost-workspaces-link').click();
  const workspacesPageShell = await page
    .getByTestId('wxpost-page-shell')
    .boundingBox();
  const workspacesPageBackLink = page.getByRole('link', {
    name: 'Back to New WxPost',
  });

  await expect(workspacesPageBackLink).toHaveAttribute(
    'href',
    '/posts/wxposts/new'
  );
  expect(workspacesPageShell?.x).toBe(newPageShell?.x);
  expect(workspacesPageShell?.width).toBe(newPageShell?.width);
  expect((await workspacesPageBackLink.boundingBox())?.x).toBe(
    newPageBackLink?.x
  );

  await page.goto('/posts/wxposts/workspaces?from=edit&workspace=4f2c9a7bd861');
  await expect(
    page.getByRole('link', { name: 'Back to WxPost' })
  ).toHaveAttribute('href', '/posts/wxposts/edit/4f2c9a7bd861');

  await page.goto('/posts/wxposts/workspaces');
  await expect(
    page.getByRole('link', { name: 'Back to Posts' })
  ).toHaveAttribute('href', '/posts');
});

test('lists shared WxPost workspaces and lets any member delete one', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  const meetingBatchRequests: string[][] = [];
  const fullMeetingRequests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname === '/meetings/options/batch') {
      meetingBatchRequests.push(
        (request.postDataJSON() as { ids: string[] }).ids
      );
    }
    if (/^\/meetings\/meeting-[^/]+$/.test(url.pathname)) {
      fullMeetingRequests.push(url.pathname);
    }
  });
  let meetingMetadataRequestCount = 0;
  let markRefreshStarted: () => void = () => undefined;
  const refreshStarted = new Promise<void>((resolve) => {
    markRefreshStarted = resolve;
  });
  let releaseRefresh: () => void = () => undefined;
  const refreshReleased = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  await page.route(/\/meetings\/options\/batch$/, async (route) => {
    meetingMetadataRequestCount += 1;
    const requestedIds = new Set(
      (route.request().postDataJSON() as { ids: string[] }).ids
    );
    if (meetingMetadataRequestCount === 2) {
      markRefreshStarted();
      await refreshReleased;
    }
    await route.fulfill({
      status: 200,
      json: {
        items: MEETING_OPTIONS.filter((meeting) =>
          requestedIds.has(meeting.id)
        ).map(({ id, no, type, theme, date }) => ({
          id,
          no,
          type,
          theme,
          date,
        })),
      },
    });
  });
  let deleted = false;
  let listRequests = 0;
  await page.route(WORKSPACES_API_URL, async (route) => {
    listRequests += 1;
    await route.fulfill({
      status: 200,
      json: workspacePage(
        deleted
          ? [
              workspaceSummary('wxpost-second', {
                meetingId: 'meeting-461',
                articleType: 'meeting-recap',
              }),
            ]
          : [
              workspaceSummary('wxpost-4f2c9a7bd861', {
                meetingId: 'meeting-462',
                articleType: 'meeting-recap',
                manifestVersion: 4,
                sourceCount: 3,
                readySourceCount: 1,
                includedSourceCount: 1,
                draftVersion: 14,
                draftExcerpt:
                  'Members found belonging by making room for every voice.',
                publication: {
                  state: 'up-to-date',
                  workspaceId: 'wxpost-4f2c9a7bd861',
                  slug: 'culture-belonging',
                  publicRevision: 3,
                  sourceDraftVersion: 14,
                  currentDraftVersion: 14,
                  publishedAt: '2026-08-01T08:00:00Z',
                  publicUrl:
                    'http://localhost:3000/posts/wxposts/culture-belonging',
                },
              }),
              workspaceSummary('wxpost-second', {
                meetingId: 'meeting-461',
                articleType: 'meeting-recap',
              }),
              workspaceSummary('wxpost-newer-draft', {
                articleType: 'custom',
                customArticleType: 'Field Guide',
                draftVersion: 15,
                draftExcerpt:
                  'A practical guide to noticing what a shared garden needs.',
                publication: {
                  state: 'update-available',
                  workspaceId: 'wxpost-newer-draft',
                  slug: 'newer-draft-ready',
                  publicRevision: 2,
                  sourceDraftVersion: 12,
                  currentDraftVersion: 15,
                  publishedAt: '2026-08-01T08:00:00Z',
                  publicUrl:
                    'http://localhost:3000/posts/wxposts/newer-draft-ready',
                },
              }),
            ]
      ),
    });
  });
  await page.route(
    /\/posts\/wxposts\/workspaces\/wxpost-4f2c9a7bd861$/,
    async (route) => {
      expect(route.request().headers()['x-expected-manifest-version']).toBe(
        '4'
      );
      deleted = true;
      await route.fulfill({
        status: 200,
        json: {
          workspaceId: 'wxpost-4f2c9a7bd861',
          deleted: true,
        },
      });
    }
  );

  await page.goto('/posts/wxposts/workspaces?from=new');
  await expect(
    page.getByRole('heading', { name: 'Workspaces', exact: true })
  ).toBeVisible();
  const workspace = page.getByTestId('workspace-wxpost-4f2c9a7bd861');
  await expect(workspace).toHaveClass(/transition-all/);
  await expect(workspace).not.toHaveClass(/hover:-translate-y-/);
  await expect(
    workspace.getByRole('heading', {
      name: 'Culture, belonging, and the courage to speak',
    })
  ).toBeVisible();
  await expect(workspace.getByText('Linked', { exact: true })).toBeVisible();
  await expect(workspace.getByText('#462', { exact: true })).toBeVisible();
  await expect(workspace.getByText('Workspace', { exact: true })).toHaveCount(
    0
  );
  await expect(
    workspace.getByText('Article type · Meeting Recap', { exact: true })
  ).toBeVisible();
  await expect(
    workspace.locator('span.rounded-full', { hasText: 'Meeting Recap' })
  ).toHaveCount(0);
  await expect(workspace.getByText(/Created by Test Member/)).toBeVisible();
  await expect(workspace.getByText('Draft · v14')).toBeVisible();
  const draftExcerpt = workspace.getByTestId(
    'workspace-draft-excerpt-wxpost-4f2c9a7bd861'
  );
  await expect(draftExcerpt).toHaveText(
    'Members found belonging by making room for every voice.'
  );
  expect(
    await draftExcerpt.evaluate((element) =>
      getComputedStyle(element).getPropertyValue('-webkit-line-clamp')
    )
  ).toBe('2');
  await expect(
    workspace.getByTestId('workspace-publication-icon-wxpost-4f2c9a7bd861')
  ).toHaveClass(/text-blue-600/);
  await expect(
    workspace.getByText('Public revision 3 · from Draft v14')
  ).toBeVisible();
  await expect(
    page
      .getByTestId('workspace-wxpost-newer-draft')
      .getByText('Public revision 2 · from Draft v12')
  ).toBeVisible();
  await expect(
    page.getByTestId('workspace-publication-icon-wxpost-newer-draft')
  ).toHaveClass(/text-amber-500/);
  await expect(
    workspace.getByRole('link', {
      name: 'Open public WxPost for Culture, belonging, and the courage to speak',
    })
  ).toHaveAttribute(
    'href',
    'http://localhost:3000/posts/wxposts/culture-belonging'
  );
  expect(meetingBatchRequests).toEqual([['meeting-462', 'meeting-461']]);
  expect(fullMeetingRequests).toEqual([]);
  const previewDraft = workspace.getByRole('link', {
    name: 'Go to Draft',
  });
  await expect(previewDraft).toHaveAttribute(
    'href',
    '/posts/wxposts/edit/4f2c9a7bd861?view=preview'
  );
  const continueWorkspace = workspace.getByRole('link', {
    name: 'Go to Materials',
  });
  await expect(continueWorkspace).toHaveAttribute(
    'href',
    '/posts/wxposts/edit/4f2c9a7bd861'
  );
  await expect(continueWorkspace).toHaveCSS('border-radius', '9999px');
  await expect(
    workspace.locator(
      'a[aria-label="Go to Materials"] + a[aria-label="Go to Draft"]'
    )
  ).toHaveCount(1);
  await expect(
    page
      .getByTestId('workspace-wxpost-second')
      .getByRole('link', { name: 'Go to Draft' })
  ).toHaveCount(0);

  await page.setViewportSize({ width: 320, height: 720 });
  expect(
    await draftExcerpt.evaluate((element) =>
      getComputedStyle(element).getPropertyValue('-webkit-line-clamp')
    )
  ).toBe('4');
  const navigationGroup = workspace.getByTestId(
    'workspace-navigation-wxpost-4f2c9a7bd861'
  );
  const navigationBox = await navigationGroup.boundingBox();
  const referenceBox = await workspace
    .getByText('#462', { exact: true })
    .boundingBox();
  expect(navigationBox?.y).toBeGreaterThan(referenceBox?.y ?? 0);
  const materialsY = (await continueWorkspace.boundingBox())?.y ?? 0;
  const draftY = (await previewDraft.boundingBox())?.y ?? 0;
  expect(Math.abs(materialsY - draftY)).toBeLessThan(1);
  expect(
    (
      await workspace
        .getByTestId('workspace-publication-icon-wxpost-4f2c9a7bd861')
        .boundingBox()
    )?.width
  ).toBe(16);
  expect((await continueWorkspace.boundingBox())?.y).toBeLessThan(
    (
      await workspace
        .getByRole('heading', {
          name: 'Culture, belonging, and the courage to speak',
        })
        .boundingBox()
    )?.y ?? Number.POSITIVE_INFINITY
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth
    )
  ).toBe(true);

  await workspace
    .getByRole('button', {
      name: /Delete Culture, belonging, and the courage to speak/,
    })
    .click();
  const dialog = page.getByTestId('delete-workspace-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(
    'Any already published WxPost and its public assets will remain available.'
  );
  await dialog.getByRole('button', { name: 'Delete workspace' }).click();
  await refreshStarted;

  const remainingWorkspace = page.getByTestId('workspace-wxpost-second');
  await expect(workspace).toHaveCount(0);
  await expect(remainingWorkspace).toContainText(
    'Build a speech people remember'
  );
  await expect(page.getByTestId('workspaces-loading')).toHaveCount(0);
  await expect(page.getByTestId('workspaces-refreshing')).toBeVisible();

  releaseRefresh();
  await expect(page.getByTestId('workspaces-refreshing')).toHaveCount(0);
  await expect(remainingWorkspace).toContainText(
    'Build a speech people remember'
  );
  expect(listRequests).toBe(2);
});

test('keeps linked workspaces usable when meeting details fail', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await page.route(WORKSPACES_API_URL, async (route) => {
    await route.fulfill({
      status: 200,
      json: workspacePage([
        workspaceSummary('wxpost-linked', {
          meetingId: 'meeting-462',
          articleType: 'meeting-recap',
        }),
      ]),
    });
  });
  let meetingDetailsAvailable = false;
  await page.route(/\/meetings\/options\/batch$/, async (route) => {
    if (!meetingDetailsAvailable) {
      await route.fulfill({
        status: 503,
        json: { detail: 'Meeting details unavailable' },
      });
      return;
    }
    await route.fulfill({
      status: 200,
      json: {
        items: [
          {
            id: 'meeting-462',
            no: 462,
            type: 'Regular',
            theme: 'Culture, belonging, and the courage to speak',
            date: '2026-07-15',
          },
        ],
      },
    });
  });

  await page.goto('/posts/wxposts/workspaces');

  const workspace = page.getByTestId('workspace-wxpost-linked');
  await expect(workspace.getByRole('heading')).toHaveText('Linked meeting');
  await expect(
    workspace.getByRole('link', { name: 'Go to Materials' })
  ).toHaveAttribute('href', '/posts/wxposts/edit/linked');
  await expect(
    workspace.getByRole('button', { name: /Delete Linked meeting/ })
  ).toBeEnabled();
  await expect(page.getByTestId('meeting-metadata-warning')).toBeVisible();

  meetingDetailsAvailable = true;
  await page.getByRole('button', { name: 'Retry meeting details' }).click();
  await expect(workspace.getByRole('heading')).toHaveText(
    'Culture, belonging, and the courage to speak'
  );
  await expect(page.getByTestId('meeting-metadata-warning')).toHaveCount(0);
});

test('keeps the initial loader until linked meeting titles are ready', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await page.route(WORKSPACES_API_URL, async (route) => {
    await route.fulfill({
      status: 200,
      json: workspacePage([
        workspaceSummary('wxpost-linked', {
          meetingId: 'meeting-462',
          articleType: 'meeting-recap',
        }),
      ]),
    });
  });
  let releaseMeetingDetails: () => void = () => undefined;
  const meetingDetailsReleased = new Promise<void>((resolve) => {
    releaseMeetingDetails = resolve;
  });
  await page.route(/\/meetings\/options\/batch$/, async (route) => {
    await meetingDetailsReleased;
    await route.fulfill({
      status: 200,
      json: {
        items: [
          {
            id: 'meeting-462',
            no: 462,
            type: 'Regular',
            theme: 'Culture, belonging, and the courage to speak',
            date: '2026-07-15',
          },
        ],
      },
    });
  });

  await page.goto('/posts/wxposts/workspaces');
  await expect(page.getByTestId('workspaces-loading')).toBeVisible();
  await expect(page.getByText('Linked meeting', { exact: true })).toHaveCount(
    0
  );

  releaseMeetingDetails();
  await expect(page.getByTestId('workspaces-loading')).toHaveCount(0);
  await expect(
    page.getByRole('heading', {
      name: 'Culture, belonging, and the courage to speak',
    })
  ).toBeVisible();
});

test('refreshes the workspace list when a delete is stale or already completed', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  let listRequests = 0;
  let staleVersion = 4;
  let missingWorkspaceVisible = true;
  await page.route(WORKSPACES_API_URL, async (route) => {
    listRequests += 1;
    await route.fulfill({
      status: 200,
      json: workspacePage([
        workspaceSummary('wxpost-stale', {
          manifestVersion: staleVersion,
          sourceCount: staleVersion,
        }),
        ...(missingWorkspaceVisible
          ? [
              workspaceSummary('wxpost-missing', {
                manifestVersion: 2,
              }),
            ]
          : []),
      ]),
    });
  });
  await page.route(
    /\/posts\/wxposts\/workspaces\/wxpost-(stale|missing)$/,
    async (route) => {
      const workspaceId = route.request().url().split('/').at(-1);
      if (workspaceId === 'wxpost-stale') {
        staleVersion = 5;
        await route.fulfill({
          status: 409,
          json: {
            error: {
              code: 'version_conflict',
              message: 'manifest changed',
            },
          },
        });
        return;
      }
      missingWorkspaceVisible = false;
      await route.fulfill({
        status: 404,
        json: {
          error: {
            code: 'workspace_not_found',
            message: 'workspace not found',
          },
        },
      });
    }
  );

  await page.goto('/posts/wxposts/workspaces');
  const staleWorkspace = page.getByTestId('workspace-wxpost-stale');
  await staleWorkspace
    .getByRole('button', { name: /Delete Independent article Custom/ })
    .click();
  await page
    .getByTestId('delete-workspace-dialog')
    .getByRole('button', { name: 'Delete workspace' })
    .click();
  await expect(page.getByTestId('delete-workspace-dialog')).toHaveCount(0);
  await expect(staleWorkspace).toContainText('0 of 5 materials ready');
  await expect(page.getByText('manifest changed')).toHaveCount(0);

  const missingWorkspace = page.getByTestId('workspace-wxpost-missing');
  await missingWorkspace
    .getByRole('button', { name: /Delete Independent article Custom/ })
    .click();
  await page
    .getByTestId('delete-workspace-dialog')
    .getByRole('button', { name: 'Delete workspace' })
    .click();
  await expect(page.getByTestId('delete-workspace-dialog')).toHaveCount(0);
  await expect(missingWorkspace).toHaveCount(0);
  await expect(page.getByText('workspace not found')).toHaveCount(0);
  expect(listRequests).toBe(3);
});

test('keeps cached workspace cards when a background refresh fails', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  let listRequests = 0;
  await page.route(WORKSPACES_API_URL, async (route) => {
    listRequests += 1;
    if (listRequests > 1) {
      await route.fulfill({
        status: 503,
        json: { detail: 'Workspace refresh failed' },
      });
      return;
    }
    await route.fulfill({
      status: 200,
      json: workspacePage([
        workspaceSummary('wxpost-cached', {
          manifestVersion: 4,
        }),
      ]),
    });
  });
  await page.route(
    /\/posts\/wxposts\/workspaces\/wxpost-cached$/,
    async (route) => {
      await route.fulfill({
        status: 409,
        json: {
          error: {
            code: 'version_conflict',
            message: 'manifest changed',
          },
        },
      });
    }
  );

  await page.goto('/posts/wxposts/workspaces');
  const workspace = page.getByTestId('workspace-wxpost-cached');
  await expect(workspace).toBeVisible();
  await workspace
    .getByRole('button', { name: /Delete Independent article Custom/ })
    .click();
  await page
    .getByTestId('delete-workspace-dialog')
    .getByRole('button', { name: 'Delete workspace' })
    .click();

  await expect(page.getByTestId('delete-workspace-dialog')).toHaveCount(0);
  await expect(workspace).toBeVisible();
  await expect(page.getByText('Workspace refresh failed')).toHaveCount(0);
  expect(listRequests).toBe(2);
});

test('paginates workspaces and returns to the previous page after deleting its last item', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  let items = Array.from({ length: 11 }, (_, index) =>
    workspaceSummary(`wxpost-page-${index + 1}`, {
      updatedAt: `2026-07-30T03:${String(59 - index).padStart(2, '0')}:00Z`,
    })
  );
  const requestedPages: number[] = [];
  await page.route(WORKSPACES_API_URL, async (route) => {
    const url = new URL(route.request().url());
    const currentPage = Number(url.searchParams.get('page'));
    const pageSize = Number(url.searchParams.get('page_size'));
    requestedPages.push(currentPage);
    const start = (currentPage - 1) * pageSize;
    await route.fulfill({
      status: 200,
      json: workspacePage(items.slice(start, start + pageSize), {
        total: items.length,
        page: currentPage,
        pageSize,
      }),
    });
  });
  await page.route(
    /\/posts\/wxposts\/workspaces\/wxpost-page-11$/,
    async (route) => {
      items = items.filter(
        (workspace) => workspace.workspaceId !== 'wxpost-page-11'
      );
      await route.fulfill({
        status: 200,
        json: { workspaceId: 'wxpost-page-11', deleted: true },
      });
    }
  );

  await page.goto('/posts/wxposts/workspaces');
  await expect(
    page.getByText('Showing 1 to 10 of 11 workspaces')
  ).toBeVisible();
  await expect(page.getByTestId('workspace-wxpost-page-1')).toBeVisible();
  await expect(page.getByTestId('workspace-wxpost-page-11')).toHaveCount(0);

  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page.getByTestId('workspace-wxpost-page-11')).toBeVisible();
  await expect(
    page.getByText('Showing 11 to 11 of 11 workspaces')
  ).toBeVisible();

  await page
    .getByTestId('workspace-wxpost-page-11')
    .getByRole('button', { name: /Delete Independent article Custom/ })
    .click();
  await page
    .getByTestId('delete-workspace-dialog')
    .getByRole('button', { name: 'Delete workspace' })
    .click();

  await expect(page.getByTestId('workspace-wxpost-page-1')).toBeVisible();
  await expect(
    page.getByText('Showing 1 to 10 of 10 workspaces')
  ).toBeVisible();
  expect(requestedPages).toEqual([1, 2, 1]);
});

test('refreshes a cached empty list after creating an independent workspace', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  const workspaceApi = await mockWxPostWorkspaceApi(page);
  let listRequests = 0;
  await page.route(WORKSPACES_API_URL, async (route) => {
    listRequests += 1;
    await route.fulfill({
      status: 200,
      json: workspacePage(
        Array.from(workspaceApi.contexts.values()).map((context) => ({
          workspaceId: context.workspaceId,
          createdBy: context.manifest.createdBy,
          createdAt: context.manifest.createdAt,
          updatedAt: context.manifest.updatedAt,
          meetingId: context.manifest.meetingId,
          articleType: context.manifest.editorial
            .articleType as WorkspaceSummary['articleType'],
          customArticleType: context.manifest.editorial.customArticleType,
          manifestVersion: context.manifest.manifestVersion,
          sourceCount: context.manifest.sources.length,
          readySourceCount: context.manifest.sources.filter(
            (source) => source.workspaceReady
          ).length,
          includedSourceCount: context.manifest.sources.filter(
            (source) => source.included
          ).length,
          draftVersion: context.manifest.draft?.version ?? null,
          draftExcerpt: context.draft?.document.excerpt ?? null,
          publication: {
            state: 'not-synced' as const,
            workspaceId: context.workspaceId,
            slug: null,
            publicRevision: null,
            sourceDraftVersion: null,
            currentDraftVersion: context.manifest.draft?.version ?? null,
            publishedAt: null,
            publicUrl: null,
          },
        }))
      ),
    });
  });

  await page.goto('/posts/wxposts/workspaces?from=new');
  await expect(page.getByText('No WxPost workspaces yet.')).toBeVisible();
  await page.getByRole('link', { name: 'Back to New WxPost' }).click();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#462'
  );
  await page.getByTestId('association-independent').click();
  await page.getByTestId('create-workspace').click();
  await page.getByTestId('wxpost-workspaces-link').click();

  await expect(
    page
      .getByTestId('wxpost-workspaces-list')
      .getByRole('heading', { name: 'Independent article' })
  ).toBeVisible();
  await expect(
    page
      .getByTestId('wxpost-workspaces-list')
      .getByText('Independent', { exact: true })
  ).toBeVisible();
  expect(listRequests).toBe(2);

  await page.evaluate(() => {
    document.body.style.minHeight = '2400px';
    window.scrollTo(0, 900);
  });
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  await page.getByRole('link', { name: 'Go to Materials' }).click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.getByTestId('wxpost-workspaces-link').click();
  await expect(page.getByTestId('wxpost-workspaces-list')).toBeVisible();
  expect(listRequests).toBe(2);
});
