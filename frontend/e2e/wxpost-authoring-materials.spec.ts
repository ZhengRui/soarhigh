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

test('runs mocked material operations and recovers from a version conflict', async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  const workspace = await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();

  const firstMaterial = page.getByTestId(`material-${FIRST_SOURCE_KEY}`);
  await expect(firstMaterial.getByText('Meeting Library')).toHaveCount(1);
  await expect(firstMaterial.getByText('meeting-room.jpg')).toHaveCount(1);
  await expect(
    firstMaterial.getByRole('button', { name: 'Use material' })
  ).toBeVisible();
  await expect(
    firstMaterial.getByRole('button', { name: 'Generate description' })
  ).toBeVisible();
  await expect(
    firstMaterial.getByRole('button', { name: 'Generate description' })
  ).toBeDisabled();
  await expect(
    firstMaterial.getByText(FIRST_SOURCE_KEY, { exact: true })
  ).toHaveCount(0);
  await expect(
    firstMaterial.getByRole('button', {
      name: 'Import meeting-room.jpg into workspace',
    })
  ).toBeVisible();
  await expect(
    firstMaterial.getByRole('button', { name: 'Move material earlier' })
  ).toHaveCount(0);
  await expect(
    firstMaterial.getByRole('button', { name: 'Move material later' })
  ).toHaveCount(0);

  const secondMaterial = page.getByTestId('material-M02');
  const firstResizeHandle = page.getByTestId(
    `description-${FIRST_SOURCE_KEY}-resize-handle`
  );
  const description = page.getByTestId(`description-${FIRST_SOURCE_KEY}`);
  const firstCardBeforeResize = await firstMaterial.boundingBox();
  const secondCardBeforeResize = await secondMaterial.boundingBox();
  const descriptionBeforeResize = await description.boundingBox();
  const firstHandleBox = await firstResizeHandle.boundingBox();
  expect(firstCardBeforeResize).not.toBeNull();
  expect(secondCardBeforeResize).not.toBeNull();
  expect(descriptionBeforeResize).not.toBeNull();
  expect(firstHandleBox).not.toBeNull();
  await page.mouse.move(
    firstHandleBox!.x + firstHandleBox!.width / 2,
    firstHandleBox!.y + firstHandleBox!.height / 2
  );
  await page.mouse.down();
  await page.mouse.move(
    firstHandleBox!.x + firstHandleBox!.width / 2,
    firstHandleBox!.y + firstHandleBox!.height / 2 + 80
  );
  await page.mouse.up();
  const firstCardAfterResize = await firstMaterial.boundingBox();
  const secondCardAfterResize = await secondMaterial.boundingBox();
  expect(firstCardAfterResize).not.toBeNull();
  expect(secondCardAfterResize).not.toBeNull();
  expect(firstCardAfterResize!.height).toBeGreaterThan(
    firstCardBeforeResize!.height + 60
  );
  expect(secondCardAfterResize!.height).toBe(secondCardBeforeResize!.height);

  const expandedHandleBox = await firstResizeHandle.boundingBox();
  expect(expandedHandleBox).not.toBeNull();
  await page.mouse.move(
    expandedHandleBox!.x + expandedHandleBox!.width / 2,
    expandedHandleBox!.y + expandedHandleBox!.height / 2
  );
  await page.mouse.down();
  await page.mouse.move(
    expandedHandleBox!.x + expandedHandleBox!.width / 2,
    expandedHandleBox!.y + expandedHandleBox!.height / 2 - 200
  );
  await page.mouse.up();
  await expect
    .poll(async () =>
      Math.round((await description.boundingBox())?.height ?? 0)
    )
    .toBe(Math.round(descriptionBeforeResize!.height));

  await description.fill(
    'Members arrive early and make space for one another.'
  );
  await expect(description).toHaveValue(
    'Members arrive early and make space for one another.'
  );
  await expect(firstMaterial.getByText('Saved', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Preview meeting-room.jpg' }).click();
  await expect(page.getByTestId('material-lightbox')).toBeVisible();
  await expect(page.getByTestId('material-lightbox')).toContainText(
    'Members arrive early and make space for one another.'
  );
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('material-lightbox')).toHaveCount(0);

  let releaseImport = () => {};
  const importGate = new Promise<void>((resolve) => {
    releaseImport = resolve;
  });
  await page.route(
    /\/posts\/wxposts\/workspaces\/[^/]+\/sources\/M01\/import$/,
    async (route) => {
      await importGate;
      await route.fallback();
    }
  );

  await page.getByTestId(`workspace-${FIRST_SOURCE_KEY}`).click();
  await expect(
    page.getByTestId(`workspace-${FIRST_SOURCE_KEY}`).locator('.animate-spin')
  ).toHaveCount(1);
  await expect(
    page.getByTestId('workspace-M02').locator('.animate-spin')
  ).toHaveCount(0);
  releaseImport();
  await expect(
    firstMaterial.getByRole('button', {
      name: 'Delete meeting-room.jpg from workspace',
    })
  ).toBeEnabled();
  await expect(
    firstMaterial.getByText(FIRST_SOURCE_KEY, { exact: true })
  ).toBeVisible();
  await page.getByTestId(`include-${FIRST_SOURCE_KEY}`).click();
  await expect(page.getByTestId(`include-${FIRST_SOURCE_KEY}`)).toContainText(
    'Included'
  );
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
  await expect(
    firstMaterial.getByText(FIRST_SOURCE_KEY, { exact: true })
  ).toHaveCount(0);
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
  await expect(page.getByTestId('delete-material-dialog')).toBeVisible();
  await expect(page.getByTestId('delete-material-dialog')).toContainText(
    'used by the saved draft'
  );
  await page
    .getByTestId('delete-material-dialog')
    .getByRole('button', { name: 'Delete' })
    .click();
  await expect(page.getByTestId('material-M04')).toHaveCount(0);

  await page.getByRole('button', { name: 'Change setup' }).click();
  await page.getByRole('button', { name: '2 Materials', exact: true }).click();
  await expect(page.getByTestId(`description-${FIRST_SOURCE_KEY}`)).toHaveValue(
    'Members arrive early and make space for one another.'
  );

  await page.getByTestId('writing-approach-image-driven').click();
  await expect(
    page.getByTestId('writing-approach-image-driven')
  ).toHaveAttribute('aria-pressed', 'true');

  const transcriptBox = await page
    .getByTestId('meeting-transcript')
    .boundingBox();
  const notesBox = await page.getByTestId('extra-notes').boundingBox();
  expect(transcriptBox).not.toBeNull();
  expect(notesBox).not.toBeNull();
  expect(notesBox!.y).toBeGreaterThan(transcriptBox!.y + transcriptBox!.height);

  workspace.conflictNextMutation = true;
  await page.getByTestId('include-M02').click();
  await expect(page.getByTestId('material-operation-notice')).toContainText(
    'Materials changed in another session'
  );

  expect(workspace.requests).toEqual(
    expect.arrayContaining([
      'PUT /',
      'PATCH /sources',
      'POST /sources/M01/import',
      'PUT /sources/M01/inclusion',
      'GET /sources/M01/delete-preflight',
      'DELETE /sources/M01',
      'POST /uploads',
      'GET /sources/M04/delete-preflight',
      'DELETE /sources/M04',
      'GET /context',
    ])
  );
  expect(pageErrors).toEqual([]);
});

test('shows the meeting error instead of staying in a loading state', async ({
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
        ? {
            status: 500,
            json: { detail: 'Unable to load meeting' },
          }
        : {
            status: 200,
            json: MEETING_462,
          }
    );
  });
  await page.route(/\/meetings\/meeting-462\/media$/, async (route) => {
    await route.fulfill(
      mediaShouldFail
        ? {
            status: 500,
            json: { detail: 'Unable to load meeting media' },
          }
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
  await page.getByTestId('continue-to-materials').click();

  await expect(
    page.getByText('Meeting details are temporarily unavailable.')
  ).toBeVisible();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();

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
  await page.getByTestId('continue-to-materials').click();
  const firstMaterial = page.getByTestId('material-M01');
  await expect(firstMaterial.getByText('Preview unavailable')).toBeVisible();
  await expect(firstMaterial.getByText('Loading preview…')).toHaveCount(0);
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

test('resets meeting-specific inputs when the selected meeting changes', async ({
  page,
}) => {
  await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();
  await page
    .getByTestId('meeting-transcript')
    .fill('Transcript that belongs only to meeting 462');

  await page.getByRole('button', { name: 'Change setup' }).click();
  await page.getByTestId('meeting-select-trigger').click();
  await page.getByTestId('meeting-option-meeting-461').click();
  await page
    .getByTestId('change-meeting-dialog')
    .getByRole('button', { name: 'Change meeting' })
    .click();
  await page.getByTestId('continue-to-materials').click();

  await expect(page.getByTestId('meeting-transcript')).toHaveValue('');
  await expect(page.getByTestId('extra-notes')).toHaveValue('');
  await expect(page.getByTestId('writing-guidance')).toHaveValue('');
});

test('keeps the single-column setup responsive on narrow phones', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await mockWxPostWorkspaceApi(page);

  for (const width of [320, 360, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/posts/wxposts/new');
    await expect(
      page.locator('button[data-testid^="article-type-"]')
    ).toHaveCount(6);

    const geometry = await page.evaluate(() => {
      const options = Array.from(
        document.querySelectorAll<HTMLElement>(
          'button[data-testid^="article-type-"]'
        )
      ).map((option) => option.getBoundingClientRect());
      return {
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        overflowers: Array.from(
          document.querySelectorAll<HTMLElement>('body *')
        )
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return {
              tag: element.tagName,
              testId: element.dataset.testid ?? null,
              text: element.textContent?.trim().slice(0, 80) ?? '',
              left: rect.left,
              right: rect.right,
              width: rect.width,
            };
          })
          .filter(
            (element) =>
              element.left < -0.5 || element.right > window.innerWidth + 0.5
          )
          .sort((left, right) => right.width - left.width)
          .slice(0, 10),
        first: { x: options[0].x, y: options[0].y },
        second: { x: options[1].x, y: options[1].y },
        third: { x: options[2].x, y: options[2].y },
      };
    });

    expect(
      geometry.documentWidth,
      JSON.stringify(geometry.overflowers, null, 2)
    ).toBeLessThanOrEqual(geometry.viewportWidth);
    expect(geometry.second.x).toBe(geometry.first.x);
    expect(geometry.second.y).toBeGreaterThan(geometry.first.y);
    expect(geometry.third.x).toBe(geometry.first.x);
    expect(geometry.third.y).toBeGreaterThan(geometry.second.y);
  }
});

test('keeps the full materials workflow readable on a 390px mobile viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();

  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();

  const geometry = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    materialWidths: Array.from(
      document.querySelectorAll<HTMLElement>('[data-testid^="material-"]')
    ).map((material) => material.getBoundingClientRect().width),
  }));

  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.materialWidths.length).toBeGreaterThan(0);
  expect(
    geometry.materialWidths.every(
      (width) => width <= geometry.viewportWidth - 20
    )
  ).toBe(true);

  await expect(
    page.getByTestId(`description-${FIRST_SOURCE_KEY}-resize-handle`)
  ).toBeVisible();
  const transcript = page.getByTestId('meeting-transcript');
  const transcriptHandle = page.getByTestId('meeting-transcript-resize-handle');
  await transcriptHandle.scrollIntoViewIfNeeded();
  const initialTranscriptBox = await transcript.boundingBox();
  const handleBox = await transcriptHandle.boundingBox();
  expect(initialTranscriptBox).not.toBeNull();
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
    .toBeGreaterThan(initialTranscriptBox!.height + 60);

  await page.getByTestId('meeting-context-toggle').click();
  await page.getByTestId('meeting-agenda-toggle').click();
  await expect(page.getByText('Listening Across Cultures')).toBeVisible();
});
