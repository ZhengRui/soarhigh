import { expect, test } from '@playwright/test';

import { createAndGenerateDraft } from './support/wxpostDraft';
import { openAuthoringPage } from './support/wxpostAuthoring';

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
