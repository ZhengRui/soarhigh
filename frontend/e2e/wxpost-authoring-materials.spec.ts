import { expect, test } from '@playwright/test';

import {
  FIRST_FILE_KEY,
  FIRST_SOURCE_KEY,
  MEETING_462,
  MEETING_OPTIONS,
  mockAuthenticatedMember,
  mockWxPostReadApis,
  mockWxPostWorkspaceApi,
  openAuthoringPage,
} from './support/wxpostAuthoring';

test('saves up to three preset and custom Voice & tone profiles', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  const saveMaterials = page.getByTestId('save-materials');

  await page.getByTestId('voice-tone-encouraging').click();
  await page.getByTestId('voice-tone-reflective').click();
  await page.getByTestId('voice-tone-celebratory').click();
  await expect(page.getByText('3/3 selected')).toBeVisible();
  await expect(page.getByTestId('voice-tone-heartfelt')).toBeDisabled();
  await expect(page.getByTestId('add-custom-voice-tone')).toBeDisabled();

  await page.getByTestId('voice-tone-celebratory').click();
  await page.getByTestId('add-custom-voice-tone').click();
  const dialog = page.getByTestId('voice-tone-dialog');
  await expect(dialog).toContainText('current workspace');
  await dialog.getByTestId('custom-voice-tone-name').fill('Warm and candid');
  await dialog.getByTestId('suggest-voice-tone-instruction').click();
  await expect(dialog.getByTestId('custom-voice-tone-instruction')).toHaveValue(
    /Use a warm, specific voice/
  );
  await dialog
    .getByTestId('custom-voice-tone-instruction')
    .fill(
      'Sound warm and candid, using precise human details without becoming sentimental.'
    );
  await dialog.getByTestId('save-custom-voice-tone').click();

  await expect(page.getByText('3/3 selected')).toBeVisible();
  await expect(page.getByTestId('voice-tone-details')).toContainText(
    'Warm and candid:'
  );
  await expect(saveMaterials).toBeEnabled();
  expect(context.manifest.editorial.voiceTone).toEqual({
    presets: [],
    customProfiles: [],
  });
  expect(workspace.requests).toContain('POST /voice-tone/suggestion');
  expect(workspace.requests).not.toContain('PATCH /');

  await page.getByRole('button', { name: 'Edit Warm and candid' }).click();
  await page
    .getByTestId('custom-voice-tone-instruction')
    .fill(
      'Sound warm and candid, and use precise human details without becoming sentimental.'
    );
  await page.getByTestId('save-custom-voice-tone').click();
  await saveMaterials.click();
  await expect(
    page.getByText('Materials saved successfully!', { exact: true })
  ).toBeVisible();
  expect(context.manifest.editorial.voiceTone).toEqual({
    presets: ['encouraging', 'reflective'],
    customProfiles: [
      {
        name: 'Warm and candid',
        instruction:
          'Sound warm and candid, and use precise human details without becoming sentimental.',
        selected: true,
      },
    ],
  });

  await page.reload();
  await expect(page.getByTestId('voice-tone-encouraging')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('voice-tone-reflective')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('custom-voice-tone-0')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('voice-tone-details')).toContainText(
    'Sound warm and candid'
  );
  await expect(page.getByTestId('save-materials')).toBeDisabled();
});

test('keeps Materials edits local and isolated from the saved Draft', async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();

  const context = Array.from(workspace.contexts.values())[0];
  const savedDraft = {
    draftVersion: 7,
    document: {
      title: 'Previously saved draft',
      bodyMarkdown: 'This must not change.',
    },
  };
  context.manifest.draft = {
    version: 7,
    sourceManifestVersion: context.manifest.manifestVersion,
    sha256: 'saved-draft-sha',
  };
  context.draft = savedDraft;

  await expect(page.getByTestId('generate-draft')).toBeDisabled();
  const saveMaterials = page.getByTestId('save-materials');
  await expect(saveMaterials).toBeDisabled();
  const saveBox = await saveMaterials.boundingBox();
  const generateBox = await page.getByTestId('generate-draft').boundingBox();
  expect(saveBox).not.toBeNull();
  expect(generateBox).not.toBeNull();
  expect(saveBox!.x + saveBox!.width).toBeLessThan(generateBox!.x);
  await expect(page.getByRole('button', { name: 'Change setup' })).toHaveCount(
    0
  );
  await page.getByTestId('article-type-custom').click();
  await page.getByTestId('custom-article-type').fill('Member interview');
  await page
    .getByTestId(`description-${FIRST_SOURCE_KEY}`)
    .fill('Members arrive early and make space for one another.');
  await page.getByTestId('meeting-transcript').fill('Local transcript');
  await page.getByTestId('extra-notes').fill('Local notes');
  await page.getByTestId('writing-guidance').fill('Keep it concise.');
  await page.getByTestId('writing-approach-image-driven').click();

  await page.getByTestId(`include-${FIRST_SOURCE_KEY}`).click();
  await expect(page.getByTestId(`include-${FIRST_SOURCE_KEY}`)).toContainText(
    'Included'
  );
  await expect(
    page
      .getByTestId(`material-${FIRST_SOURCE_KEY}`)
      .getByText(FIRST_SOURCE_KEY, {
        exact: true,
      })
  ).toBeVisible();

  let releaseImport = () => {};
  const importGate = new Promise<void>((resolve) => {
    releaseImport = resolve;
  });
  await page.route(
    /\/posts\/wxposts\/workspaces\/[^/]+\/sources\/M02\/import$/,
    async (route) => {
      await importGate;
      await route.fallback();
    }
  );
  await page.getByTestId('workspace-M02').click();
  await expect(
    page.getByTestId('workspace-M02').locator('.animate-spin')
  ).toHaveCount(1);
  await expect(
    page.getByTestId('workspace-M01').locator('.animate-spin')
  ).toHaveCount(0);
  await page
    .getByTestId(`description-${FIRST_SOURCE_KEY}`)
    .fill('Description edited while another import is pending.');
  releaseImport();
  await expect(
    page
      .getByTestId('material-M02')
      .getByRole('button', { name: 'Use material' })
  ).toBeVisible();
  await expect(page.getByTestId(`description-${FIRST_SOURCE_KEY}`)).toHaveValue(
    'Description edited while another import is pending.'
  );

  await page.getByRole('button', { name: /Setup/ }).click();
  await expect(page.getByTestId('source-locked-message')).toBeVisible();
  await page.getByRole('button', { name: /Materials/ }).click();
  await expect(page.getByTestId('article-type-custom')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('custom-article-type')).toHaveValue(
    'Member interview'
  );
  await expect(page.getByTestId('meeting-transcript')).toHaveValue(
    'Local transcript'
  );
  await expect(page.getByTestId('extra-notes')).toHaveValue('Local notes');
  await expect(page.getByTestId('writing-guidance')).toHaveValue(
    'Keep it concise.'
  );
  await expect(
    page.getByTestId('writing-approach-image-driven')
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(saveMaterials).toBeEnabled();

  expect(context.manifest.editorial).toMatchObject({
    articleType: 'meeting-recap',
    customArticleType: null,
    writingApproach: 'chronological',
    transcript: '',
    extraNotes: '',
    writingGuidance: '',
    voiceTone: { presets: [], customProfiles: [] },
  });
  expect(context.manifest.sources[0]).toMatchObject({
    included: false,
    description: '',
  });
  expect(context.draft).toBe(savedDraft);
  expect(context.draft.document).toEqual({
    title: 'Previously saved draft',
    bodyMarkdown: 'This must not change.',
  });
  expect(workspace.requests).not.toContain('PATCH /sources');
  expect(workspace.requests).not.toContain('PUT /sources/M01/inclusion');
  expect(workspace.requests).not.toContain('PATCH /');
  expect(pageErrors).toEqual([]);

  await saveMaterials.click();
  await expect(
    page.getByText('Materials saved successfully!', { exact: true })
  ).toBeVisible();
  await expect(saveMaterials).toBeDisabled();
  expect(context.manifest.editorial).toMatchObject({
    articleType: 'custom',
    customArticleType: 'Member interview',
    writingApproach: 'image-driven',
    transcript: 'Local transcript',
    extraNotes: 'Local notes',
    writingGuidance: 'Keep it concise.',
    voiceTone: { presets: [], customProfiles: [] },
  });
  expect(context.manifest.sources[0]).toMatchObject({
    included: true,
    description: 'Description edited while another import is pending.',
    descriptionSource: 'user',
    descriptionStatus: 'confirmed',
  });
  expect(context.draft).toBe(savedDraft);
  expect(context.draft.document).toEqual({
    title: 'Previously saved draft',
    bodyMarkdown: 'This must not change.',
  });
  expect(
    workspace.requests.filter((request) => request === 'PATCH /')
  ).toHaveLength(1);
  expect(workspace.requests).not.toContain('PATCH /sources');

  await page.reload();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId('article-type-custom')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('custom-article-type')).toHaveValue(
    'Member interview'
  );
  await expect(page.getByTestId(`description-${FIRST_SOURCE_KEY}`)).toHaveValue(
    'Description edited while another import is pending.'
  );
  await expect(page.getByTestId('meeting-transcript')).toHaveValue(
    'Local transcript'
  );
  await expect(page.getByTestId('extra-notes')).toHaveValue('Local notes');
  await expect(page.getByTestId('writing-guidance')).toHaveValue(
    'Keep it concise.'
  );
  await expect(
    page.getByTestId('writing-approach-image-driven')
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId(`include-${FIRST_SOURCE_KEY}`)).toContainText(
    'Included'
  );
  await expect(page.getByTestId('save-materials')).toBeDisabled();
  expect(context.draft).toBe(savedDraft);
});

test('confirms before a stale Materials save replaces local edits', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  const description = page.getByTestId('description-M02');
  const saveMaterials = page.getByTestId('save-materials');

  await description.fill('Keep this local description.');
  const contextRequestsBeforeConflict = workspace.requests.filter(
    (request) => request === 'GET /context'
  ).length;
  context.manifest.sources = context.manifest.sources.filter(
    (source) => source.id !== 'M02'
  );
  context.manifest.manifestVersion += 1;

  await saveMaterials.click();
  const conflictDialog = page.getByTestId('materials-conflict-dialog');
  await expect(conflictDialog).toBeVisible();
  await expect(description).toHaveValue('Keep this local description.');
  await expect(page.getByText(/unknown source/i)).toHaveCount(0);
  expect(
    workspace.requests.filter((request) => request === 'GET /context')
  ).toHaveLength(contextRequestsBeforeConflict);

  await conflictDialog
    .getByRole('button', { name: 'Keep current edits' })
    .click();
  await expect(description).toHaveValue('Keep this local description.');
  await expect(saveMaterials).toBeEnabled();

  await saveMaterials.click();
  await expect(conflictDialog).toBeVisible();
  await conflictDialog.getByRole('button', { name: 'Load latest' }).click();
  await expect(conflictDialog).toHaveCount(0);
  await expect(page.getByTestId('material-M02')).toHaveCount(0);
  expect(
    workspace.requests.filter((request) => request === 'GET /context')
  ).toHaveLength(contextRequestsBeforeConflict + 1);
  expect(
    workspace.requests.filter((request) => request === 'PATCH /')
  ).toHaveLength(2);
});

test('checks the Materials version before opening a delete confirmation', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];

  await page.getByTestId('material-file-input').setInputFiles({
    name: 'stale-photo.png',
    mimeType: 'image/png',
    buffer: Buffer.from('stale-photo'),
  });
  await expect(page.getByTestId('material-M04')).toBeVisible();

  context.manifest.sources = context.manifest.sources.filter(
    (source) => source.id !== 'M04'
  );
  context.manifest.manifestVersion += 1;
  const contextRequestsBeforeConflict = workspace.requests.filter(
    (request) => request === 'GET /context'
  ).length;

  await page
    .getByTestId('material-M04')
    .getByRole('button', {
      name: 'Delete stale-photo.png from workspace',
    })
    .click();

  await expect(page.getByTestId('delete-material-dialog')).toHaveCount(0);
  const conflictDialog = page.getByTestId('materials-conflict-dialog');
  await expect(conflictDialog).toBeVisible();
  await expect(page.getByText(/unknown source/i)).toHaveCount(0);
  await expect(
    page.getByText('Could not check whether this material is in the draft.')
  ).toHaveCount(0);
  await expect(page.getByTestId('material-M04')).toBeVisible();
  expect(
    workspace.requests.filter((request) => request === 'GET /context')
  ).toHaveLength(contextRequestsBeforeConflict);

  await conflictDialog.getByRole('button', { name: 'Load latest' }).click();
  await expect(conflictDialog).toHaveCount(0);
  await expect(page.getByTestId('material-M04')).toHaveCount(0);
  expect(
    workspace.requests.filter((request) => request === 'GET /context')
  ).toHaveLength(contextRequestsBeforeConflict + 1);
});

test('runs immediate import, upload, and delete operations without UI regressions', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  const firstMaterial = page.getByTestId(`material-${FIRST_SOURCE_KEY}`);
  const secondMaterial = page.getByTestId('material-M02');

  await expect(firstMaterial.getByText('Meeting Library')).toHaveCount(1);
  await expect(
    firstMaterial.getByRole('button', { name: 'Generate description' })
  ).toBeDisabled();
  await expect(
    firstMaterial.getByRole('button', {
      name: 'Import meeting-room.jpg into workspace',
    })
  ).toBeVisible();

  const description = page.getByTestId(`description-${FIRST_SOURCE_KEY}`);
  const resizeHandle = page.getByTestId(
    `description-${FIRST_SOURCE_KEY}-resize-handle`
  );
  const firstCardBefore = await firstMaterial.boundingBox();
  const secondCardBefore = await secondMaterial.boundingBox();
  const descriptionBefore = await description.boundingBox();
  const handleBefore = await resizeHandle.boundingBox();
  expect(firstCardBefore).not.toBeNull();
  expect(secondCardBefore).not.toBeNull();
  expect(descriptionBefore).not.toBeNull();
  expect(handleBefore).not.toBeNull();
  const handleX = handleBefore!.x + handleBefore!.width / 2;
  const handleY = handleBefore!.y + handleBefore!.height / 2;
  await resizeHandle.dispatchEvent('pointerdown', {
    pointerId: 1,
    pointerType: 'mouse',
    button: 0,
    clientX: handleX,
    clientY: handleY,
  });
  await resizeHandle.dispatchEvent('pointermove', {
    pointerId: 1,
    pointerType: 'mouse',
    clientX: handleX,
    clientY: handleY + 80,
  });
  await resizeHandle.dispatchEvent('pointerup', {
    pointerId: 1,
    pointerType: 'mouse',
    clientX: handleX,
    clientY: handleY + 80,
  });
  expect((await firstMaterial.boundingBox())!.height).toBeGreaterThan(
    firstCardBefore!.height + 60
  );
  expect((await secondMaterial.boundingBox())!.height).toBe(
    secondCardBefore!.height
  );

  await description.fill('Visible in the image lightbox.');
  await page.getByRole('button', { name: 'Preview meeting-room.jpg' }).click();
  await expect(page.getByTestId('material-lightbox')).toContainText(
    'Visible in the image lightbox.'
  );
  await page.keyboard.press('Escape');

  await page.getByTestId(`workspace-${FIRST_SOURCE_KEY}`).click();
  await expect(
    firstMaterial.getByRole('button', {
      name: 'Delete meeting-room.jpg from workspace',
    })
  ).toBeEnabled();
  await page.getByTestId(`include-${FIRST_SOURCE_KEY}`).click();
  await firstMaterial
    .getByRole('button', {
      name: 'Delete meeting-room.jpg from workspace',
    })
    .click();
  await expect(page.getByTestId('delete-material-dialog')).toContainText(
    'This removes the workspace copy.'
  );
  await page
    .getByTestId('delete-material-dialog')
    .getByRole('button', { name: 'Delete' })
    .click();
  await expect(page.getByTestId(`include-${FIRST_SOURCE_KEY}`)).toContainText(
    'Use material'
  );
  await expect(
    firstMaterial.getByRole('button', {
      name: 'Import meeting-room.jpg into workspace',
    })
  ).toBeVisible();

  await page.getByTestId('material-file-input').setInputFiles({
    name: 'web-photo.png',
    mimeType: 'image/png',
    buffer: Buffer.from('web-photo'),
  });
  await expect(page.getByTestId('material-M04')).toBeVisible();
  workspace.referencedSourceIds.add('M04');
  await page
    .getByTestId('material-M04')
    .getByRole('button', { name: 'Delete web-photo.png from workspace' })
    .click();
  await expect(page.getByTestId('delete-material-dialog')).toContainText(
    'used by the saved draft'
  );
  await page
    .getByTestId('delete-material-dialog')
    .getByRole('button', { name: 'Delete' })
    .click();
  await expect(page.getByTestId('material-M04')).toHaveCount(0);

  await description.fill('Do not lose this local text on conflict.');
  context.manifest.sources[0].description = 'Latest saved description.';
  context.manifest.sources[0].descriptionSource = 'user';
  context.manifest.sources[0].descriptionStatus = 'confirmed';
  const contextRequestsBeforeConflict = workspace.requests.filter(
    (request) => request === 'GET /context'
  ).length;
  workspace.conflictNextMutation = true;
  await page.getByTestId('workspace-M02').click();
  const conflictDialog = page.getByTestId('materials-conflict-dialog');
  await expect(conflictDialog).toContainText(
    'Loading the latest version will discard your unsaved changes'
  );
  await expect(conflictDialog).toContainText(
    'The material change you just attempted was not applied.'
  );
  await expect(description).toHaveValue(
    'Do not lose this local text on conflict.'
  );
  expect(
    workspace.requests.filter((request) => request === 'GET /context')
  ).toHaveLength(contextRequestsBeforeConflict);

  await conflictDialog
    .getByRole('button', { name: 'Keep current edits' })
    .click();
  await expect(conflictDialog).toHaveCount(0);
  await expect(page.getByTestId('material-operation-notice')).toHaveCount(0);
  await expect(description).toHaveValue(
    'Do not lose this local text on conflict.'
  );
  expect(
    workspace.requests.filter((request) => request === 'GET /context')
  ).toHaveLength(contextRequestsBeforeConflict);

  workspace.conflictNextMutation = true;
  await page.getByTestId('workspace-M02').click();
  await expect(conflictDialog).toBeVisible();
  await expect(description).toHaveValue(
    'Do not lose this local text on conflict.'
  );
  await conflictDialog.getByRole('button', { name: 'Load latest' }).click();
  await expect(conflictDialog).toHaveCount(0);
  await expect(page.getByTestId('material-operation-notice')).toHaveCount(0);
  await expect(description).toHaveValue('Latest saved description.');

  expect(workspace.requests).toEqual(
    expect.arrayContaining([
      'PUT /',
      'POST /sources/M01/import',
      'GET /sources/M01/delete-preflight',
      'DELETE /sources/M01',
      'POST /uploads',
      'GET /sources/M04/delete-preflight',
      'DELETE /sources/M04',
      'POST /sources/M02/import',
      'POST /sources/M02/import',
      'GET /context',
    ])
  );
  expect(
    workspace.requests.filter((request) => request === 'GET /context')
  ).toHaveLength(contextRequestsBeforeConflict + 1);
  expect(
    workspace.requests.filter(
      (request) => request === 'POST /sources/M02/import'
    )
  ).toHaveLength(2);
  expect(workspace.requests).not.toContain('PATCH /sources');
  expect(
    workspace.requests.some((request) => request.endsWith('/inclusion'))
  ).toBe(false);
});

test('shows meeting and media errors instead of staying in a loading state', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await mockWxPostWorkspaceApi(page);
  let meetingShouldFail = true;
  let mediaShouldFail = true;
  await page.route(/\/meetings\/meeting-462$/, async (route) => {
    await route.fulfill(
      meetingShouldFail
        ? { status: 500, json: { detail: 'Unable to load meeting' } }
        : { status: 200, json: MEETING_462 }
    );
  });
  await page.route(/\/meetings\/meeting-462\/media$/, async (route) => {
    await route.fulfill(
      mediaShouldFail
        ? { status: 500, json: { detail: 'Unable to load meeting media' } }
        : {
            status: 200,
            json: {
              items: [
                {
                  filename: 'meeting-room.jpg',
                  url: '/images/toastmasters.png',
                  fileKey: FIRST_FILE_KEY,
                  uploadedAt: '2026-07-15T12:00:00Z',
                },
              ],
            },
          }
    );
  });

  await page.goto('/posts/wxposts/new');
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#462'
  );
  await page.getByTestId('create-workspace').click();
  await expect(
    page.getByText('Meeting details are temporarily unavailable.')
  ).toBeVisible();

  meetingShouldFail = false;
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(
    page.getByText('Original meeting previews are temporarily unavailable.')
  ).toBeVisible();
  mediaShouldFail = false;
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(
    page.getByRole('button', { name: 'Preview meeting-room.jpg' })
  ).toBeVisible();
});

test('shows an unavailable state when a meeting preview is missing', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await mockWxPostWorkspaceApi(page);
  await page.route(/\/meetings\/meeting-462\/media$/, async (route) => {
    await route.fulfill({ status: 200, json: { items: [] } });
  });

  await page.goto('/posts/wxposts/new');
  await page.getByTestId('create-workspace').click();
  const firstMaterial = page.getByTestId('material-M01');
  await expect(firstMaterial.getByText('Preview unavailable')).toBeVisible();
  await expect(firstMaterial.getByText('Loading preview…')).toHaveCount(0);
});

test('shows a breathing placeholder while meeting previews load', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await mockWxPostWorkspaceApi(page);
  let releasePreviewRequest: () => void = () => undefined;
  const previewRequestReleased = new Promise<void>((resolve) => {
    releasePreviewRequest = resolve;
  });
  await page.route(/\/meetings\/meeting-462\/media$/, async (route) => {
    await previewRequestReleased;
    await route.fulfill({
      status: 200,
      json: {
        items: [
          {
            filename: 'meeting-room.jpg',
            url: '/images/toastmasters.png',
            fileKey: FIRST_FILE_KEY,
            uploadedAt: '2026-07-15T12:00:00Z',
          },
        ],
      },
    });
  });

  await page.goto('/posts/wxposts/new');
  await page.getByTestId('create-workspace').click();
  const firstMaterial = page.getByTestId('material-M01');

  try {
    const loadingPreview = firstMaterial.getByTestId(
      'material-preview-loading'
    );
    await expect(loadingPreview).toBeVisible();
    await expect(loadingPreview).toHaveCSS('animation-name', 'pulse');
    await expect(loadingPreview).toHaveCSS('animation-duration', '2s');
    await expect(loadingPreview.locator('svg')).toHaveCount(0);
    await expect(firstMaterial.getByText('Preview unavailable')).toHaveCount(0);
    await expect(firstMaterial.locator('svg.animate-spin')).toHaveCount(0);
  } finally {
    releasePreviewRequest();
  }

  await expect(
    firstMaterial.getByRole('button', { name: 'Preview meeting-room.jpg' })
  ).toBeVisible();
  await expect(
    firstMaterial.getByTestId('material-preview-loading')
  ).toHaveCount(0);
});

test('retries the meeting options request without reloading the page', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  let shouldFail = true;
  await page.route(
    /\/meetings\/options\?page=1&page_size=50$/,
    async (route) => {
      await route.fulfill(
        shouldFail
          ? {
              status: 500,
              json: { detail: 'Unable to load meeting options' },
            }
          : {
              status: 200,
              json: {
                items: MEETING_OPTIONS.slice(0, 50).map(
                  ({ id, no, type, theme, date }) => ({
                    id,
                    no,
                    type,
                    theme,
                    date,
                  })
                ),
                total: 101,
                page: 1,
                page_size: 50,
                pages: 3,
              },
            }
      );
    }
  );

  await page.goto('/posts/wxposts/new');
  await expect(page.getByText('Unable to load meetings')).toBeVisible();
  shouldFail = false;
  await page.getByTestId('retry-meeting-options').click();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#462'
  );
});

test('keeps Setup and Materials single-column on narrow phones', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthoringPage(page);

  const sourceGeometry = await page.evaluate(() =>
    Array.from(
      document.querySelectorAll<HTMLElement>('[data-testid^="association-"]')
    ).map((element) => {
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, height: rect.height };
    })
  );
  expect(sourceGeometry[1].x).toBe(sourceGeometry[0].x);
  expect(sourceGeometry[1].y).toBeGreaterThan(sourceGeometry[0].y);
  expect(sourceGeometry[0].height).toBe(40);
  expect(sourceGeometry[1].height).toBe(40);
  expect(sourceGeometry[1].y - sourceGeometry[0].y).toBe(50);
  await expect(page.getByTestId('meeting-select-trigger')).toHaveCSS(
    'height',
    '40px'
  );
  await expect(page.getByTestId('create-workspace')).toHaveCSS(
    'height',
    '44px'
  );

  await page.getByTestId('create-workspace').click();
  const articleTypes = page.locator('button[data-testid^="article-type-"]');
  await expect(articleTypes).toHaveCount(6);
  const geometry = await page.evaluate(() => {
    const options = Array.from(
      document.querySelectorAll<HTMLElement>(
        'button[data-testid^="article-type-"]'
      )
    ).map((option) => option.getBoundingClientRect());
    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      stageHeight:
        document
          .querySelector<HTMLElement>(
            'nav[aria-label="WxPost authoring progress"] button'
          )
          ?.getBoundingClientRect().height ?? 0,
      panelHeaderHeight:
        document
          .querySelector<HTMLElement>(
            '[data-testid="article-type-panel"] > div'
          )
          ?.getBoundingClientRect().height ?? 0,
      first: { x: options[0].x, y: options[0].y, height: options[0].height },
      second: { x: options[1].x, y: options[1].y },
      third: { x: options[2].x, y: options[2].y },
    };
  });
  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.stageHeight).toBe(52);
  expect(geometry.panelHeaderHeight).toBe(52);
  expect(geometry.first.height).toBe(40);
  expect(geometry.second.x).toBe(geometry.first.x);
  expect(geometry.second.y - geometry.first.y).toBe(50);
  expect(geometry.third.x).toBe(geometry.first.x);
  expect(geometry.third.y).toBeGreaterThan(geometry.second.y);
});

test('keeps the full Materials workflow readable on a 390px viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();

  const geometry = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    materialImageHeight:
      document
        .querySelector<HTMLElement>('[data-testid^="material-"] > div')
        ?.getBoundingClientRect().height ?? 0,
    descriptionHeight:
      document
        .querySelector<HTMLElement>('[data-testid^="description-"]')
        ?.getBoundingClientRect().height ?? 0,
    transcriptHeight:
      document
        .querySelector<HTMLElement>('[data-testid="meeting-transcript"]')
        ?.getBoundingClientRect().height ?? 0,
    addFilesHeight:
      Array.from(document.querySelectorAll<HTMLButtonElement>('button'))
        .find((button) => button.textContent?.includes('Add files'))
        ?.getBoundingClientRect().height ?? 0,
    useMaterialHeight:
      document
        .querySelector<HTMLElement>('[data-testid^="include-"]')
        ?.getBoundingClientRect().height ?? 0,
    approachHeight:
      document
        .querySelector<HTMLElement>(
          '[data-testid="writing-approach-chronological"]'
        )
        ?.getBoundingClientRect().height ?? 0,
    toneHeight:
      document
        .querySelector<HTMLElement>('[data-testid="voice-tone-encouraging"]')
        ?.getBoundingClientRect().height ?? 0,
    materialWidths: Array.from(
      document.querySelectorAll<HTMLElement>('[data-testid^="material-"]')
    ).map((material) => material.getBoundingClientRect().width),
  }));
  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.materialImageHeight).toBe(185);
  expect(geometry.descriptionHeight).toBe(84);
  expect(geometry.transcriptHeight).toBe(108);
  expect(geometry.addFilesHeight).toBe(38);
  expect(geometry.useMaterialHeight).toBe(36);
  expect(geometry.approachHeight).toBe(34);
  expect(geometry.toneHeight).toBe(34);
  expect(geometry.materialWidths.length).toBeGreaterThan(0);
  expect(
    geometry.materialWidths.every(
      (width) => width <= geometry.viewportWidth - 20
    )
  ).toBe(true);

  const transcript = page.getByTestId('meeting-transcript');
  const handle = page.getByTestId('meeting-transcript-resize-handle');
  await handle.scrollIntoViewIfNeeded();
  const initialBox = await transcript.boundingBox();
  const handleBox = await handle.boundingBox();
  expect(initialBox).not.toBeNull();
  expect(handleBox).not.toBeNull();
  await page.mouse.move(
    handleBox!.x + handleBox!.width / 2,
    handleBox!.y + handleBox!.height / 2
  );
  await page.mouse.down();
  await page.mouse.move(
    handleBox!.x + handleBox!.width / 2,
    handleBox!.y + handleBox!.height / 2 + 80
  );
  await page.mouse.up();
  await expect
    .poll(async () => (await transcript.boundingBox())?.height ?? 0)
    .toBeGreaterThan(initialBox!.height + 60);

  await page.getByTestId('meeting-context-toggle').click();
  await page.getByTestId('meeting-agenda-toggle').click();
  await expect(page.getByText('Listening Across Cultures')).toBeVisible();
});
