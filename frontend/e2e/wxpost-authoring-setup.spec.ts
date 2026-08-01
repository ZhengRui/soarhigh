import { expect, test } from '@playwright/test';

import {
  FIRST_SOURCE_KEY,
  mockAuthenticatedMember,
  mockWxPostReadApis,
  mockWxPostWorkspaceApi,
  openAuthoringPage,
} from './support/wxpostAuthoring';

test('opens the WxPost setup flow from the authenticated Posts page', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await page.route(/\/posts\?.*kind=/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        pages: 0,
      },
    });
  });

  await page.goto('/posts');
  await expect(page.getByTestId('new-post-menu')).not.toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Wx Workspaces' })
  ).toHaveAttribute('href', '/posts/wxposts/workspaces');
  await page.getByTestId('new-post-menu-trigger').click();
  await expect(
    page.getByRole('menuitem', { name: 'Regular Post' })
  ).toHaveAttribute('href', '/posts/new');
  await page.getByTestId('new-wxpost-link').click();
  await expect(page).toHaveURL('/posts/wxposts/new');
  await expect(page.getByRole('heading', { name: 'New WxPost' })).toBeVisible();
});

test('lays out the Posts actions responsively', async ({ page }) => {
  await mockAuthenticatedMember(page);
  await page.route(/\/posts\?.*kind=/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        pages: 0,
      },
    });
  });

  await page.goto('/posts');
  const desktopNewPost = await page
    .getByTestId('new-post-menu-trigger')
    .boundingBox();
  const desktopWorkspaces = await page
    .getByRole('link', { name: 'Wx Workspaces' })
    .boundingBox();

  expect(desktopWorkspaces?.x).toBeLessThan(desktopNewPost?.x ?? 0);
  expect(desktopWorkspaces?.y).toBe(desktopNewPost?.y);
  expect(desktopWorkspaces?.height).toBe(desktopNewPost?.height);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileNewPost = await page
    .getByTestId('new-post-menu-trigger')
    .boundingBox();
  const mobileWorkspaces = await page
    .getByRole('link', { name: 'Wx Workspaces' })
    .boundingBox();

  expect(mobileNewPost?.x).toBeLessThan(mobileWorkspaces?.x ?? 0);
  expect(mobileWorkspaces?.y).toBe(mobileNewPost?.y);
  expect(mobileWorkspaces?.height).toBe(mobileNewPost?.height);
  expect(
    (mobileWorkspaces?.x ?? 0) -
      ((mobileNewPost?.x ?? 0) + (mobileNewPost?.width ?? 0))
  ).toBeGreaterThan(32);
});

test('keeps the Posts and Meetings create actions vertically aligned', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await page.route(/\/posts\?.*kind=/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        pages: 0,
      },
    });
  });
  await page.route(/\/meetings\?page=1&page_size=10$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        pages: 0,
      },
    });
  });

  await page.goto('/posts');
  const postsButton = await page
    .getByTestId('new-post-menu-trigger')
    .boundingBox();
  await page.goto('/meetings');
  const meetingsButton = await page
    .getByRole('link', { name: 'Create Meeting' })
    .boundingBox();

  expect(postsButton?.y).toBe(meetingsButton?.y);
});

test('keeps Setup source-only and creates one immutable workspace', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  const setup = page.getByTestId('setup-stage');

  await expect(setup.getByTestId('article-type-panel')).toHaveCount(0);
  await expect(page.getByTestId('association-linked')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await page.getByTestId('meeting-select-trigger').click();
  const options = page
    .getByTestId('meeting-select-options')
    .getByRole('option');
  await expect(options).toHaveCount(50);
  await page
    .getByTestId('meeting-select-options')
    .getByRole('listbox')
    .evaluate((list) => {
      list.scrollTop = list.scrollHeight;
      list.dispatchEvent(new Event('scroll', { bubbles: true }));
    });
  await expect(options).toHaveCount(100);
  await page.getByTestId('meeting-option-meeting-461').click();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#461'
  );

  await page.getByTestId('create-workspace').click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId('article-type-panel')).toBeVisible();
  await expect(page.getByTestId('article-type-meeting-recap')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page).toHaveURL(/\/posts\/wxposts\/edit\/[0-9a-f]{12}$/);
  await expect(
    page.getByRole('heading', { name: 'WxPost', exact: true })
  ).toBeVisible();
  const workspaceKey = new URL(page.url()).pathname.split('/').at(-1);
  await expect(page.getByTestId('wxpost-workspaces-link')).toHaveAttribute(
    'href',
    `/posts/wxposts/workspaces?from=edit&workspace=${workspaceKey}`
  );
  expect(workspace.contexts.size).toBe(1);
  const context = Array.from(workspace.contexts.values())[0];
  expect(context.manifest.meetingId).toBe('meeting-461');
  expect(context.manifest.editorial.articleType).toBe('meeting-recap');

  await page.getByRole('button', { name: /Setup/ }).click();
  await expect(page.getByTestId('source-locked-message')).toBeVisible();
  await expect(page.getByTestId('association-linked')).toBeDisabled();
  await expect(page.getByTestId('association-independent')).toBeDisabled();
  await expect(page.getByTestId('meeting-select-trigger')).toBeDisabled();
  await expect(page.getByTestId('create-workspace')).toHaveCount(0);
  expect(
    workspace.requests.filter((request) => request === 'PUT /')
  ).toHaveLength(1);
  expect(
    workspace.requests.filter((request) => request === 'PATCH /')
  ).toHaveLength(0);
});

test('creates an independent workspace without meeting context', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('association-independent').click();
  await expect(page.getByTestId('meeting-select-trigger')).toHaveCount(0);
  await expect(page.locator('header p')).toHaveText('Independent article');
  await page.getByTestId('create-workspace').click();

  await expect(page.getByTestId('article-type-custom')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('custom-article-type')).toHaveValue('');
  await expect(page.getByTestId('meeting-context')).toHaveCount(0);
  await expect(page.getByText('No media', { exact: true })).toBeVisible();
  const context = Array.from(workspace.contexts.values())[0];
  expect(context.manifest.meetingId).toBeNull();
  expect(context.manifest.editorial.articleType).toBe('custom');
  expect(context.manifest.editorial.customArticleType).toBeNull();
});

test('defaults event-number workspaces to a custom Event Recap', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('meeting-select-trigger').click();
  const options = page
    .getByTestId('meeting-select-options')
    .getByRole('option');
  const listbox = page
    .getByTestId('meeting-select-options')
    .getByRole('listbox');

  await listbox.evaluate((list) => {
    list.scrollTop = list.scrollHeight;
    list.dispatchEvent(new Event('scroll', { bubbles: true }));
  });
  await expect(options).toHaveCount(100);
  await listbox.evaluate((list) => {
    list.scrollTop = list.scrollHeight;
    list.dispatchEvent(new Event('scroll', { bubbles: true }));
  });
  await expect(options).toHaveCount(101);
  await page.getByTestId('meeting-option-meeting-449').click();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#100001'
  );

  await page.getByTestId('create-workspace').click();

  await expect(page.getByTestId('article-type-custom')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('custom-article-type')).toHaveValue(
    'Event Recap'
  );
  await expect(page.getByTestId('wxpost-header-subtitle')).toContainText(
    'Event #100001 · Event Recap'
  );
  await expect(page.getByTestId('meeting-context')).toContainText(
    'Event · #100001'
  );
  await expect(page.getByTestId('article-type-event-preview')).toHaveAttribute(
    'aria-pressed',
    'false'
  );
  const context = Array.from(workspace.contexts.values())[0];
  expect(context.manifest.meetingId).toBe('meeting-449');
  expect(context.manifest.editorial.articleType).toBe('custom');
  expect(context.manifest.editorial.customArticleType).toBe('Event Recap');
});

test('shows complete linked meeting context with nested sections collapsed', async ({
  page,
}) => {
  await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();

  const contextToggle = page.getByTestId('meeting-context-toggle');
  await expect(contextToggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByTestId('meeting-description')).toHaveCount(0);
  await contextToggle.click();
  await page.getByTestId('meeting-description-toggle').click();
  await expect(page.getByTestId('meeting-description')).toContainText(
    '把天南海北的生活都摊开来看看'
  );
  await page.getByTestId('meeting-agenda-toggle').click();
  const agenda = page.getByTestId('meeting-agenda');
  await expect(agenda.getByRole('row')).toHaveCount(8);
  await expect(agenda.getByText('A Tale of Two Homes')).toBeVisible();
  await page.getByTestId('meeting-awards-toggle').click();
  await expect(page.getByTestId('meeting-awards')).toContainText(
    'Best Prepared Speaker'
  );
});

test('resumes an existing workspace without creating or unlocking it', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  const workspace = await mockWxPostWorkspaceApi(page);
  workspace.contextDelayMs = 2000;

  await page.goto('/posts/wxposts/edit/resume');
  await expect(
    page.getByRole('heading', { name: 'WxPost', exact: true })
  ).toBeVisible();
  const headerSubtitle = page.locator('header p');
  await expect(
    page.getByTestId('wxpost-header-subtitle-loading')
  ).toBeVisible();
  await expect(headerSubtitle).not.toContainText('Independent article');
  await expect(page.getByTestId('wxpost-workspaces-link')).toHaveAttribute(
    'href',
    '/posts/wxposts/workspaces?from=edit&workspace=resume'
  );
  const materialsTab = page.getByRole('button', { name: /Materials/ });
  await materialsTab.waitFor();
  expect(await materialsTab.getAttribute('aria-current')).toBe('step');
  const resumeStatus = page.getByTestId('workspace-resume-status');
  await expect(resumeStatus).toHaveText('Loading workspace…');
  await expect(resumeStatus.locator('svg')).toHaveClass(/animate-spin/);
  await expect(page.getByTestId('setup-stage')).toBeHidden();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();
  await expect(page.getByTestId('wxpost-header-subtitle-loading')).toHaveCount(
    0
  );
  await expect(headerSubtitle).toHaveText('Regular #462 · Meeting Recap');
  await page.getByRole('button', { name: /Setup/ }).click();
  await expect(page.getByTestId('source-locked-message')).toBeVisible();
  await expect(page.getByTestId('association-linked')).toBeDisabled();
  await expect(page.getByTestId('meeting-select-trigger')).toBeDisabled();
  expect(workspace.requests).toContain('GET /context');
  expect(workspace.requests).not.toContain('PUT /');
  expect(workspace.requests).not.toContain('PATCH /');
});

test('does not substitute the first meeting when a resumed source is unavailable', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  const workspace = await mockWxPostWorkspaceApi(page);
  workspace.contexts.set('wxpost-missing-meeting', {
    workspaceId: 'wxpost-missing-meeting',
    manifest: {
      schemaVersion: 4,
      workspaceId: 'wxpost-missing-meeting',
      manifestVersion: 3,
      nextMaterialNumber: 1,
      createdBy: { id: 'member-123', name: 'Test Member' },
      createdAt: '2026-07-29T03:00:00Z',
      updatedAt: '2026-07-29T03:15:00Z',
      meetingId: 'meeting-no-longer-visible',
      draft: null,
      editorial: {
        articleType: 'meeting-recap',
        customArticleType: null,
        writingApproach: 'chronological',
        transcript: '',
        extraNotes: '',
        writingGuidance: '',
        voiceTone: { presets: [], customProfiles: [] },
      },
      sources: [],
    },
    draft: null,
  });

  await page.goto('/posts/wxposts/edit/missing-meeting');
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await page.getByRole('button', { name: /Setup/ }).click();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    'Choose a meeting or event'
  );
  await expect(page.getByTestId('meeting-select-trigger')).toBeDisabled();
  expect(workspace.requests).not.toContain('PATCH /');
});
