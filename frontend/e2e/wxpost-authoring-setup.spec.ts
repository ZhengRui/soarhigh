import { expect, test } from '@playwright/test';

import {
  FIRST_SOURCE_KEY,
  mockAuthenticatedMember,
  mockWxPostReadApis,
  mockWxPostWorkspaceApi,
  openAuthoringPage,
} from './support/wxpostAuthoring';

test('opens the WXPost setup flow from the authenticated Posts page', async ({
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
  await page.getByTestId('new-post-menu-trigger').click();
  await expect(
    page.getByRole('menuitem', { name: 'Regular Post' })
  ).toHaveAttribute('href', '/posts/new');
  await page.getByTestId('new-wxpost-link').click();
  await expect(page).toHaveURL('/posts/wxposts/new');
  await expect(
    page.getByRole('heading', { name: 'New WeChat Post' })
  ).toBeVisible();
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

test('uses real meeting data from the dropdown and keeps source independent from article type', async ({
  page,
}) => {
  await openAuthoringPage(page);

  const setup = page.getByTestId('setup-stage');
  await expect(setup.getByTestId('article-type-meeting-recap')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('association-linked')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await page.getByTestId('meeting-select-trigger').click();
  const meetingOptions = page
    .getByTestId('meeting-select-options')
    .getByRole('option');
  await expect(meetingOptions).toHaveCount(50);
  await page
    .getByTestId('meeting-select-options')
    .getByRole('listbox')
    .evaluate((list) => {
      list.scrollTop = list.scrollHeight;
      list.dispatchEvent(new Event('scroll', { bubbles: true }));
    });
  await expect(meetingOptions).toHaveCount(100);
  await page
    .getByTestId('meeting-select-options')
    .getByRole('listbox')
    .evaluate((list) => {
      list.scrollTop = list.scrollHeight;
      list.dispatchEvent(new Event('scroll', { bubbles: true }));
    });
  await expect(meetingOptions).toHaveCount(101);
  await expect(page.getByTestId('meeting-option-meeting-449')).toContainText(
    'Beyond the Mask'
  );
  await expect(page.getByTestId('meeting-option-meeting-449')).toContainText(
    'Special Event · Apr 8, 2026'
  );
  await expect(
    page.getByTestId('meeting-option-meeting-449')
  ).not.toContainText('Special Event · Special Event');
  await page.getByTestId('meeting-option-meeting-461').click();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#461'
  );

  await setup.getByTestId('article-type-member-story').click();
  await expect(setup.getByTestId('article-type-member-story')).toHaveAttribute(
    'aria-pressed',
    'true'
  );

  await expect(page.getByText('Workshop #461 · Member Story')).toBeVisible();

  await page.getByTestId('association-independent').click();
  await expect(page.getByTestId('meeting-select-trigger')).toHaveCount(0);
  await expect(
    page.getByText('Independent article · Member Story')
  ).toBeVisible();

  await page.getByTestId('continue-to-materials').click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId('meeting-context')).toHaveCount(0);
  await expect(page.getByText('No media', { exact: true })).toBeVisible();
  await expect(
    page.getByText('Independent article · Member Story')
  ).toBeVisible();
  await expect(page).toHaveURL(/workspace=wxpost-[0-9a-f]{12}/);
});

test('shows complete linked meeting context from the API and keeps nested sections collapsed', async ({
  page,
}) => {
  await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();

  const contextToggle = page.getByTestId('meeting-context-toggle');
  await expect(contextToggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByTestId('meeting-description')).toHaveCount(0);

  await contextToggle.click();
  await expect(contextToggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByText('Venue', { exact: true })).toBeVisible();
  await expect(
    page
      .getByTestId('meeting-context')
      .getByText('Gobel Power Energy · Shenzhen', { exact: true })
  ).toBeVisible();

  await page.getByTestId('meeting-description-toggle').click();
  await expect(page.getByTestId('meeting-description')).toContainText(
    '把天南海北的生活都摊开来看看'
  );

  await page.getByTestId('meeting-agenda-toggle').click();
  const agenda = page.getByTestId('meeting-agenda');
  await expect(agenda.getByRole('row')).toHaveCount(8);
  await expect(
    agenda.getByRole('columnheader', { name: 'Role taker' })
  ).toBeVisible();
  await expect(
    agenda.getByRole('columnheader', {
      name: 'Speech / workshop title',
    })
  ).toBeVisible();
  await expect(agenda.getByText('A Tale of Two Homes')).toBeVisible();

  await page.getByTestId('meeting-awards-toggle').click();
  const awards = page.getByTestId('meeting-awards');
  await expect(awards.getByText('Best Prepared Speaker')).toBeVisible();
  await expect(awards.getByText('Rui Zheng')).toBeVisible();
});

test('allows a custom article type without requiring a label', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('article-type-custom').click();
  const articleTypePanel = page.getByTestId('article-type-panel');
  await expect(
    articleTypePanel.getByTestId('custom-article-type')
  ).toBeVisible();
  await page.getByTestId('association-independent').click();
  await expect(page.getByTestId('continue-to-materials')).toBeEnabled();
  await page.getByTestId('continue-to-materials').click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();

  const context = Array.from(workspace.contexts.values())[0];
  expect(context.manifest.editorial.articleType).toBe('custom');
  expect(context.manifest.editorial.customArticleType).toBeNull();
});

test('resumes an existing workspace from the URL without creating a replacement', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  const workspace = await mockWxPostWorkspaceApi(page);

  await page.goto('/posts/wxposts/new?workspace=wxpost-resume');

  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();
  await expect(page).toHaveURL(/workspace=wxpost-resume/);
  expect(workspace.requests).toContain('GET /context');
  expect(workspace.requests).not.toContain('PUT /');
});

test('does not replace an unresolved resumed meeting with the first option', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  const workspace = await mockWxPostWorkspaceApi(page);
  workspace.contextDelayMs = 200;
  workspace.contexts.set('wxpost-missing-meeting', {
    workspaceId: 'wxpost-missing-meeting',
    manifest: {
      schemaVersion: 3,
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
      },
      sources: [],
    },
    draft: null,
  });

  await page.goto('/posts/wxposts/new?workspace=wxpost-missing-meeting');
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await page.getByRole('button', { name: 'Change setup' }).click();

  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    'Choose a meeting or event'
  );
  await expect(page.getByTestId('continue-to-materials')).toBeDisabled();
  expect(
    workspace.requests.filter((request) => request === 'PATCH /')
  ).toHaveLength(0);
});

test('updates article type and meeting without replacing the workspace', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();
  await expect(page.getByTestId('material-M01')).toBeVisible();

  const initialUrl = page.url();
  const initialWorkspaceId = new URL(initialUrl).searchParams.get('workspace');
  expect(initialWorkspaceId).toMatch(/^wxpost-[0-9a-f]{12}$/);
  expect(workspace.contexts.size).toBe(1);

  const description = page.getByTestId('description-M01');
  await description.fill('Keep this description when only the type changes.');
  await expect(
    page.getByTestId('material-M01').getByText('Saved', { exact: true })
  ).toBeVisible();
  await page.getByTestId('include-M01').click();
  await expect(page.getByTestId('include-M01')).toContainText('Included');

  await page.getByRole('button', { name: 'Change setup' }).click();
  await page.getByTestId('article-type-member-story').click();
  await page.getByTestId('continue-to-materials').click();

  await expect(page).toHaveURL(initialUrl);
  await expect(page.getByTestId('description-M01')).toHaveValue(
    'Keep this description when only the type changes.'
  );
  await expect(page.getByTestId('include-M01')).toContainText('Included');
  expect(workspace.contexts.size).toBe(1);
  expect(
    workspace.contexts.get(initialWorkspaceId!)?.manifest.editorial.articleType
  ).toBe('member-story');

  await page.getByRole('button', { name: 'Change setup' }).click();
  await page.getByTestId('meeting-select-trigger').click();
  await page.getByTestId('meeting-option-meeting-461').click();
  const changeMeetingDialog = page.getByTestId('change-meeting-dialog');
  await expect(changeMeetingDialog).toBeVisible();
  await expect(changeMeetingDialog).toContainText('Regular #462');
  await expect(changeMeetingDialog).toContainText('Workshop #461');
  await expect(changeMeetingDialog).toContainText(
    'Files you uploaded yourself will be kept.'
  );
  await changeMeetingDialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(changeMeetingDialog).toHaveCount(0);
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#462'
  );
  expect(
    workspace.requests.filter((request) => request === 'PATCH /')
  ).toHaveLength(1);

  await page.getByTestId('meeting-select-trigger').click();
  await page.getByTestId('meeting-option-meeting-461').click();
  await expect(changeMeetingDialog).toBeVisible();
  await changeMeetingDialog
    .getByRole('button', { name: 'Change meeting' })
    .click();
  await expect(changeMeetingDialog).toHaveCount(0);
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#461'
  );
  await page.getByTestId('continue-to-materials').click();

  await expect(page).toHaveURL(initialUrl);
  await expect(page.getByTestId('material-M01')).toHaveCount(0);
  await expect(page.getByTestId('material-M04')).toContainText(
    'workshop-stage.jpg'
  );
  expect(workspace.contexts.size).toBe(1);
  expect(workspace.contexts.get(initialWorkspaceId!)?.manifest.meetingId).toBe(
    'meeting-461'
  );
  expect(
    workspace.requests.filter((request) => request === 'PATCH /')
  ).toHaveLength(2);
});

test('confirms before making a linked workspace independent', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  const workspaceId = new URL(page.url()).searchParams.get('workspace')!;

  await page.getByRole('button', { name: 'Change setup' }).click();
  await page.getByTestId('association-independent').click();
  const dialog = page.getByTestId('change-meeting-dialog');
  await expect(dialog).toContainText('Make this article independent?');
  await expect(dialog).toContainText(
    'Files you uploaded yourself will be kept.'
  );
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByTestId('association-linked')).toHaveAttribute(
    'aria-pressed',
    'true'
  );

  await page.getByTestId('association-independent').click();
  await dialog.getByRole('button', { name: 'Make independent' }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByTestId('continue-to-materials').click();

  expect(workspace.contexts.get(workspaceId)?.manifest.meetingId).toBeNull();
  expect(
    workspace.contexts
      .get(workspaceId)
      ?.manifest.sources.some(
        (source) => source.origin.type === 'meeting-library'
      )
  ).toBe(false);
});
