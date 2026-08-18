import { expect, test, type Page } from '@playwright/test';

import { createAndGenerateDraft } from './support/wxpostDraft';
import { openAuthoringPage } from './support/wxpostAuthoring';

const MOCK_PUT_URL =
  'https://mock-oss.invalid/public/wxposts/x/assets/y/original.jpg';
const UPLOAD_SOURCE_ID = 'M04';
// Matches the fixed 'b'.repeat(64) contentSha256 the workspace mock assigns
// to every source created by POST .../uploads, regardless of origin.
const UPLOAD_SOURCE_SHA = 'b'.repeat(64);

// Builds a workspace whose one non-library material is included in the
// saved Draft: uploads a file (immediate mutation), marks it included
// (working-copy only), saves Materials (PATCH, bumps manifestVersion), then
// generates the Draft. Mirrors the real authoring flow end to end instead of
// poking the mock's internal state directly, so the frontend's own
// manifestVersion/sources bookkeeping stays authoritative.
async function createDraftWithIncludedUpload(page: Page) {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();

  await page.getByTestId('material-file-input').setInputFiles({
    name: 'promo.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.from('promo-bytes'),
  });
  await expect(page.getByTestId(`material-${UPLOAD_SOURCE_ID}`)).toBeVisible();
  await page.getByTestId(`include-${UPLOAD_SOURCE_ID}`).click();
  await page.getByTestId('save-materials').click();
  await expect(page.getByTestId('save-materials')).toBeDisabled();
  await expect(page.getByTestId('generate-draft')).toBeEnabled();
  await page.getByTestId('generate-draft').click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();

  return { workspace, sourceId: UPLOAD_SOURCE_ID };
}

test('publishes only the saved Draft and exposes a stable public link', async ({
  page,
}) => {
  await createAndGenerateDraft(page);

  let postsRequests = 0;
  await page.route(/\/posts\?.*kind=/, async (route) => {
    postsRequests += 1;
    const items =
      postsRequests === 1
        ? []
        : [
            {
              kind: 'wxpost',
              id: 'public-wxpost-1',
              title: 'Unsaved public title',
              slug: 'public-wxpost-1',
              excerpt: 'Published from the saved Draft.',
              author: { member_id: null, name: 'SoarHigh Toastmasters' },
              is_public: true,
              cover_image_url: null,
              article_revision: 1,
              created_at: '2026-08-01T08:00:00Z',
            },
          ];
    await route.fulfill({
      status: 200,
      json: {
        items,
        total: items.length,
        page: 1,
        page_size: 10,
        pages: items.length,
      },
    });
  });

  await page.getByRole('link', { name: 'Back to Posts' }).click();
  await expect(page).toHaveURL(/\/posts$/);
  await expect(page.getByText('No content found.')).toBeVisible();
  expect(postsRequests).toBe(1);
  await page.goBack();
  await page.getByRole('button', { name: 'Draft' }).click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();

  await expect(page.getByTestId('publication-status')).toHaveText(
    'Not published · Draft v1'
  );
  await page
    .getByTestId('wxpost-article')
    .getByRole('heading', { level: 1 })
    .click();
  await page
    .getByRole('textbox', { name: 'Edit draft title' })
    .fill('Unsaved public title');
  await expect(page.getByTestId('sync-public-wxpost')).toBeDisabled();
  await expect(page.getByTestId('sync-public-wxpost')).toHaveAttribute(
    'title',
    'Save Draft before updating the public WxPost.'
  );

  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(page.getByTestId('sync-public-wxpost')).toBeEnabled();
  await page.getByTestId('sync-public-wxpost').click();
  const confirmation = page.getByTestId('publication-confirm-dialog');
  await expect(confirmation).toContainText('Publish this saved Draft?');
  await expect(confirmation).toContainText('Anyone with the link');
  await confirmation.getByRole('button', { name: 'Publish WxPost' }).click();

  await expect(
    page.getByText('Public WxPost published successfully!', { exact: true })
  ).toBeVisible();
  await expect(page.getByTestId('publication-status')).toHaveText(
    'Public revision 1 · from Draft v2 · up to date'
  );
  await expect(page.getByTestId('publication-status-link')).toHaveCount(0);
  await expect(page.getByTestId('view-public-wxpost')).toHaveAttribute(
    'href',
    /\/posts\/wxposts\/public-wxpost-/
  );
  await page.getByRole('link', { name: 'Back to Posts' }).click();
  await expect(page).toHaveURL(/\/posts$/);
  await expect(
    page.locator('article').getByRole('heading', {
      name: 'Unsaved public title',
    })
  ).toBeVisible();
  expect(postsRequests).toBe(2);

  await page.goBack();
  await page.getByRole('button', { name: 'Draft' }).click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  await page.setViewportSize({ width: 615, height: 844 });
  const viewPublicBox = await page
    .getByTestId('view-public-wxpost')
    .boundingBox();
  const updatePublicBox = await page
    .getByTestId('sync-public-wxpost')
    .boundingBox();
  expect(viewPublicBox).not.toBeNull();
  expect(updatePublicBox).not.toBeNull();
  expect(viewPublicBox!.width).toBe(36);
  expect(viewPublicBox!.height).toBe(36);
  expect(updatePublicBox!.width).toBe(36);
  expect(updatePublicBox!.height).toBe(36);
});

test('maps public revisions to Draft versions without shifting while refreshing', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);
  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();
  await expect(page.getByTestId('publication-status')).toContainText(
    'up to date'
  );
  await expect(page.getByTestId('publication-status')).toHaveText(
    'Public revision 1 · from Draft v1 · up to date'
  );
  await expect(page.getByTestId('sync-public-wxpost')).toBeVisible();
  await expect(page.getByTestId('sync-public-wxpost')).toHaveText(
    'Update Public WxPost'
  );
  await expect(page.getByTestId('sync-public-wxpost')).toBeDisabled();

  const draftControls = page
    .getByTestId('draft-workbench')
    .locator(':scope > header');
  const publicationControls = page.getByTestId('draft-publication-controls');
  await expect
    .poll(() =>
      draftControls.evaluate(
        (element) => getComputedStyle(element).borderBottomLeftRadius
      )
    )
    .toBe('0px');
  const publicationHeightBefore = (await publicationControls.boundingBox())!
    .height;

  await page
    .getByTestId('wxpost-article')
    .getByRole('heading', { level: 1 })
    .click();
  await page
    .getByRole('textbox', { name: 'Edit draft title' })
    .fill('A newer saved Draft');
  workspace.publicationStatusDelayMs = 1_500;
  await page.getByTestId('save-draft').click();

  await expect(page.getByTestId('publication-refresh-spinner')).toBeVisible();
  await expect(page.getByTestId('sync-public-wxpost')).toBeDisabled();
  await expect(page.getByTestId('publication-status')).toHaveText(
    'Public revision 1 · from Draft v1 · Draft v2 ready to publish'
  );
  expect((await publicationControls.boundingBox())!.height).toBeCloseTo(
    publicationHeightBefore,
    0
  );
  await expect(page.getByTestId('publication-refresh-spinner')).toBeHidden();
  await expect(page.getByTestId('sync-public-wxpost')).toHaveText(
    'Update Public WxPost'
  );
  await expect(page.getByTestId('sync-public-wxpost')).toBeEnabled();
  await page.getByTestId('sync-public-wxpost').click();
  const updateConfirmation = page.getByTestId('publication-confirm-dialog');
  await expect(updateConfirmation).toContainText(
    'Draft v2 will replace the current public revision'
  );
  const confirmationGeometry = await updateConfirmation.evaluate((overlay) => {
    const overlayRect = overlay.getBoundingClientRect();
    const dialogRect = overlay.firstElementChild!.getBoundingClientRect();
    return {
      overlay: {
        left: overlayRect.left,
        top: overlayRect.top,
        width: overlayRect.width,
        height: overlayRect.height,
      },
      dialogCenter: {
        x: dialogRect.left + dialogRect.width / 2,
        y: dialogRect.top + dialogRect.height / 2,
      },
    };
  });
  const viewport = page.viewportSize()!;
  expect(confirmationGeometry.overlay).toEqual({
    left: 0,
    top: 0,
    width: viewport.width,
    height: viewport.height,
  });
  expect(confirmationGeometry.dialogCenter.x).toBeCloseTo(
    viewport.width / 2,
    0
  );
  expect(confirmationGeometry.dialogCenter.y).toBeCloseTo(
    viewport.height / 2,
    0
  );
  await updateConfirmation
    .getByRole('button', { name: 'Update Public WxPost' })
    .click();
  await expect(page.getByTestId('publication-status')).toHaveText(
    'Public revision 2 · from Draft v2 · up to date'
  );
});

test('keeps the publication state on failure and uses the shared conflict dialog', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);
  workspace.failNextPublication = true;
  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();
  await expect(page.getByText('Public asset upload failed')).toBeVisible();
  await expect(page.getByTestId('publication-status')).toHaveText(
    'Not published · Draft v1'
  );

  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();
  await expect(page.getByTestId('publication-status')).toContainText(
    'up to date'
  );

  await page
    .getByTestId('wxpost-article')
    .getByRole('heading', { level: 1 })
    .click();
  await page
    .getByRole('textbox', { name: 'Edit draft title' })
    .fill('Conflicting update');
  await page.getByTestId('save-draft').click();
  workspace.conflictNextPublication = true;
  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Update Public WxPost' })
    .click();

  const conflict = page.getByTestId('draft-conflict-dialog');
  await expect(conflict).toContainText(
    'This Draft or public WxPost changed elsewhere.'
  );
  await expect(page.getByTestId('publication-status')).toContainText(
    'Draft v2 ready to publish'
  );
});

test('does not misreport a failed public status check as unpublished', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  workspace.publicationStatusUnavailable = true;
  await page.getByTestId('create-workspace').click();
  await page.getByTestId('generate-draft').click();

  await expect(page.getByTestId('publication-status')).toHaveText(
    'Public status unavailable'
  );
  await expect(page.getByTestId('sync-public-wxpost')).toBeVisible();
  await expect(page.getByTestId('sync-public-wxpost')).toBeDisabled();
  await expect(page.getByTestId('sync-public-wxpost')).toHaveText(
    'Update Public WxPost'
  );
  await expect(
    page.getByText('Public status temporarily unavailable')
  ).toBeVisible();
});

test('uploads a pending upload-origin material to public storage before publishing', async ({
  page,
}) => {
  const { workspace, sourceId } = await createDraftWithIncludedUpload(page);
  workspace.publicationUploadUrls = [
    {
      sourceId,
      contentSha256: UPLOAD_SOURCE_SHA,
      putUrl: MOCK_PUT_URL,
      headers: { 'Content-MD5': 'AA==', 'Content-Type': 'image/jpeg' },
    },
  ];

  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();

  await expect(
    page.getByText('Public WxPost published successfully!', { exact: true })
  ).toBeVisible();
  expect(workspace.publicationUploadUrlCalls).toBe(1);
  expect(workspace.publicationUploadPuts).toEqual([MOCK_PUT_URL]);
});

test('aborts the publish before submitting when an OSS upload fails, and lets the member retry', async ({
  page,
}) => {
  const { workspace, sourceId } = await createDraftWithIncludedUpload(page);
  workspace.publicationUploadUrls = [
    {
      sourceId,
      contentSha256: UPLOAD_SOURCE_SHA,
      putUrl: MOCK_PUT_URL,
      headers: { 'Content-MD5': 'AA==', 'Content-Type': 'image/jpeg' },
    },
  ];
  workspace.failNextPublicationUpload = true;

  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();

  await expect(
    page.getByText(
      'Uploading materials to public storage failed. Retry the publish.'
    )
  ).toBeVisible();
  expect(workspace.publicationOperations.size).toBe(0);
  expect(workspace.publicationUploadPuts).toHaveLength(1);
  await expect(page.getByTestId('publication-status')).toHaveText(
    'Not published · Draft v1'
  );

  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();

  await expect(
    page.getByText('Public WxPost published successfully!', { exact: true })
  ).toBeVisible();
  expect(workspace.publicationUploadPuts).toHaveLength(2);
});

test('makes no presign call when every included material is meeting-library', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);

  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();

  await expect(
    page.getByText('Public WxPost published successfully!', { exact: true })
  ).toBeVisible();
  expect(workspace.publicationUploadUrlCalls).toBe(0);
  expect(workspace.publicationUploadPuts).toHaveLength(0);
});

test('goes straight to submit when the presign call reports nothing pending', async ({
  page,
}) => {
  // workspace.publicationUploadUrls stays at its default [] — the presign
  // step still runs (the material is included and not meeting-library), but
  // reports every byte already in public storage, so there is nothing to PUT.
  const { workspace } = await createDraftWithIncludedUpload(page);

  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();

  await expect(
    page.getByText('Public WxPost published successfully!', { exact: true })
  ).toBeVisible();
  expect(workspace.publicationUploadUrlCalls).toBe(1);
  expect(workspace.publicationUploadPuts).toHaveLength(0);
});
