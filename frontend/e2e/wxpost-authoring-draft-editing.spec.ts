import { expect, test } from '@playwright/test';

import {
  completeDraftDocument,
  replaceEditableText,
} from './support/wxpostDraft';
import {
  draftDocument,
  openAuthoringPage,
  type DraftDocument,
} from './support/wxpostAuthoring';

test('removes Draft media before allowing its Materials file to be deleted', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];

  await page.getByTestId('include-M01').click();
  await page.getByTestId('save-materials').click();
  workspace.nextGeneratedDocument = {
    ...draftDocument(
      'Draft media dependency',
      'Opening copy.\n\n:::image\nmedia: M01\ncaption: A saved image\n:::'
    ),
    media: [
      {
        id: 'M01',
        kind: 'image',
        sourceUrl: '',
        description: 'A meeting image.',
        include: true,
        order: 1,
        descriptionSource: 'user',
        descriptionStatus: 'confirmed',
      },
    ],
    coverMediaId: 'M01',
  };
  await page.getByTestId('generate-draft').click();
  await expect(page.getByTestId('directive-image')).toBeVisible();

  await page.getByTestId('draft-mode-preview').click();
  await expect(page.locator('[data-wxpost-delete-media]')).toHaveCount(0);
  await page.getByTestId('draft-mode-edit').click();
  await expect(
    page.getByRole('button', { name: 'Remove M01 from Draft' })
  ).toBeVisible();

  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId('workspace-M01').click();
  const blockedDialog = page.getByTestId('delete-material-dialog');
  await expect(blockedDialog).toContainText(
    'This material is the cover of Draft v1.'
  );
  await expect(blockedDialog).toContainText(
    'If it also appears in the article, remove it there too.'
  );
  await expect(
    blockedDialog.getByRole('button', { name: 'Delete' })
  ).toHaveCount(0);
  await blockedDialog.getByRole('button', { name: 'Go to Draft' }).click();

  const removeDraftMedia = page.getByRole('button', {
    name: 'Remove M01 from Draft',
  });
  await removeDraftMedia.locator('..').hover();
  await removeDraftMedia.click();
  const deleteDraftMediaDialog = page.getByTestId('delete-draft-media-dialog');
  await expect(deleteDraftMediaDialog).toContainText(
    'Remove M01 from the article?'
  );
  await expect(deleteDraftMediaDialog).toContainText(
    'M01 will remain selected as the cover'
  );
  const dialogGeometry = await deleteDraftMediaDialog.evaluate((overlay) => {
    const overlayRect = overlay.getBoundingClientRect();
    const panelRect = overlay.firstElementChild!.getBoundingClientRect();
    return {
      overlayTop: overlayRect.top,
      overlayLeft: overlayRect.left,
      overlayWidth: overlayRect.width,
      overlayHeight: overlayRect.height,
      panelCenterX: panelRect.left + panelRect.width / 2,
      panelCenterY: panelRect.top + panelRect.height / 2,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    };
  });
  expect(dialogGeometry.overlayTop).toBe(0);
  expect(dialogGeometry.overlayLeft).toBe(0);
  expect(dialogGeometry.overlayWidth).toBe(dialogGeometry.viewportWidth);
  expect(dialogGeometry.overlayHeight).toBe(dialogGeometry.viewportHeight);
  expect(dialogGeometry.panelCenterX).toBeCloseTo(
    dialogGeometry.viewportWidth / 2,
    0
  );
  expect(dialogGeometry.panelCenterY).toBeCloseTo(
    dialogGeometry.viewportHeight / 2,
    0
  );
  await deleteDraftMediaDialog
    .getByRole('button', { name: 'Remove from article' })
    .click();
  await expect(page.getByTestId('directive-image')).toHaveCount(0);
  await expect(page.getByText('Missing image M01')).toHaveCount(0);
  await expect(page.getByTestId('save-draft')).toBeEnabled();
  expect((context.draft!.document as DraftDocument).media).toHaveLength(1);

  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  expect((context.draft!.document as DraftDocument).media).toHaveLength(1);
  expect((context.draft!.document as DraftDocument).coverMediaId).toBe('M01');
  expect((context.draft!.document as DraftDocument).bodyMarkdown).toBe(
    'Opening copy.\n'
  );

  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId('workspace-M01').click();
  const coverBlockedDialog = page.getByTestId('delete-material-dialog');
  await expect(coverBlockedDialog).toContainText(
    'This material is the cover of Draft v2.'
  );
  await coverBlockedDialog.getByRole('button', { name: 'Go to Draft' }).click();

  await page.getByTestId('open-cover-picker').click();
  await page
    .getByTestId('cover-picker-dialog')
    .getByRole('button', { name: 'Remove cover' })
    .click();
  await page.getByTestId('apply-cover-selection').click();
  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v3')).toBeVisible();
  expect((context.draft!.document as DraftDocument).media).toEqual([]);
  expect((context.draft!.document as DraftDocument).coverMediaId).toBeNull();

  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId('workspace-M01').click();
  const deleteDialog = page.getByTestId('delete-material-dialog');
  await expect(deleteDialog).toContainText('This removes the workspace copy.');
  await deleteDialog.getByRole('button', { name: 'Delete' }).click();
  await expect(
    page.getByRole('button', { name: 'Import meeting-room.jpg into workspace' })
  ).toBeVisible();

  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();
  await expect(page.getByTestId('publication-status')).toHaveText(
    'Public revision 1 · from Draft v3 · up to date'
  );
});

test('removes only the selected occurrence when one image is reused', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  context.manifest.sources.forEach((source) => {
    source.workspaceReady = true;
    source.contentSha256 = 'a'.repeat(64);
    source.dimensions =
      source.kind === 'image' ? { width: 1, height: 1 } : null;
    source.included = true;
  });
  workspace.nextGeneratedDocument = completeDraftDocument();

  await page.getByTestId('generate-draft').click();
  const article = page.getByTestId('wxpost-article');
  const reusedImageDeletes = article.locator(
    '[data-wxpost-delete-media="M01"]'
  );
  await expect(reusedImageDeletes).toHaveCount(2);

  await article
    .getByTestId('directive-person')
    .locator('[data-wxpost-media-frame="M01"]')
    .hover();
  await reusedImageDeletes.nth(1).click();
  await page
    .getByTestId('delete-draft-media-dialog')
    .getByRole('button', { name: 'Remove media' })
    .click();

  await expect(
    article.getByTestId('directive-image').locator('img')
  ).toBeVisible();
  await expect(
    article
      .getByTestId('directive-person')
      .locator('[data-wxpost-media-frame="M01"]')
  ).toHaveCount(0);
  await page.getByTestId('save-draft').click();

  const savedDocument = context.draft!.document as unknown as DraftDocument;
  expect(savedDocument.bodyMarkdown).toContain('media: M01');
  expect(savedDocument.bodyMarkdown).not.toMatch(
    /:::person[\s\S]*?media: M01[\s\S]*?:::/
  );
  expect(savedDocument.media.some((media) => media.id === 'M01')).toBe(true);
});

test('edits every Draft text source precisely and persists it without changing Materials', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  context.manifest.sources.forEach((source, index) => {
    source.workspaceReady = true;
    source.contentSha256 = 'a'.repeat(64);
    source.dimensions =
      source.kind === 'image' ? { width: 1, height: 1 } : null;
    source.included = true;
    source.description = `Saved Materials description ${index + 1}`;
    source.descriptionSource = 'user';
    source.descriptionStatus = 'confirmed';
  });
  const materialDescriptions = context.manifest.sources.map(
    (source) => source.description
  );
  workspace.nextGeneratedDocument = completeDraftDocument();

  await page.getByTestId('generate-draft').click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  const article = page.getByTestId('wxpost-article');

  await expect(
    article.locator('[data-wxpost-edit-label="paragraph"]')
  ).toHaveCount(4);
  await expect(
    article.locator('[data-wxpost-edit-label="section heading"]')
  ).toHaveCount(1);
  await expect(article.locator('[data-wxpost-edit-label="list"]')).toHaveCount(
    1
  );
  await expect(article.locator('[data-wxpost-edit-label="quote"]')).toHaveCount(
    1
  );
  await expect(
    article.getByText('Meeting Recap', { exact: true })
  ).not.toHaveAttribute('data-wxpost-edit-key');
  await expect(article.getByText('01', { exact: true })).not.toHaveAttribute(
    'data-wxpost-edit-key'
  );
  await expect(
    article.getByText('Takeaway', { exact: true })
  ).not.toHaveAttribute('data-wxpost-edit-key');

  await replaceEditableText(page, 'draft title', 'Edited article title');
  await replaceEditableText(page, 'draft excerpt', 'Edited article excerpt.');
  await replaceEditableText(page, 'draft byline', 'Edited editorial team');
  await replaceEditableText(page, 'paragraph', 'Edited opening paragraph.', 0);
  await replaceEditableText(
    page,
    'paragraph',
    'Edited second opening paragraph.',
    1
  );
  await replaceEditableText(page, 'section kicker', 'A new beginning');
  await replaceEditableText(page, 'section heading', 'A revised section');
  await replaceEditableText(
    page,
    'paragraph',
    'Edited first section paragraph.',
    2
  );
  await replaceEditableText(
    page,
    'paragraph',
    'Edited second section paragraph.',
    3
  );
  await replaceEditableText(page, 'image caption', 'Edited standalone caption');
  await replaceEditableText(page, 'gallery caption', 'Edited gallery heading');
  await replaceEditableText(
    page,
    'image description',
    'Edited Draft-only gallery description'
  );
  await replaceEditableText(page, 'video caption', 'Edited video heading');
  await replaceEditableText(
    page,
    'video description',
    'Edited Draft-only video description'
  );
  await replaceEditableText(page, 'takeaway title', 'Edited takeaway');
  await replaceEditableText(page, 'takeaway text', 'Edited takeaway text.');
  await replaceEditableText(page, 'person name', 'Jordan Chen');
  await replaceEditableText(page, 'person role', 'General Evaluator');
  await replaceEditableText(
    page,
    'person summary',
    'Jordan connected each part of the meeting.'
  );
  await replaceEditableText(
    page,
    'person quote',
    'Every voice changes the room.'
  );
  await replaceEditableText(page, 'info grid title', 'Edited facts');
  await replaceEditableText(page, 'info label', 'Attendees', 0);
  await replaceEditableText(page, 'info value', 'Thirty-two', 0);
  await replaceEditableText(page, 'info label', 'Focus', 1);
  await replaceEditableText(page, 'info value', 'Connection', 1);
  await replaceEditableText(page, 'timeline title', 'Edited programme');
  await replaceEditableText(page, 'timeline label', '19:00', 0);
  await replaceEditableText(page, 'timeline item title', 'Arrival', 0);
  await replaceEditableText(
    page,
    'timeline item description',
    'Guests met one another.',
    0
  );
  await replaceEditableText(page, 'timeline label', '20:00', 1);
  await replaceEditableText(page, 'timeline item title', 'Stories', 1);
  await replaceEditableText(
    page,
    'timeline item description',
    'Members told prepared stories.',
    1
  );
  await replaceEditableText(
    page,
    'pull quote',
    'Edited effort remains remarkable.'
  );
  await replaceEditableText(page, 'quote attribution', 'The editorial team');

  await article.click({ position: { x: 5, y: 5 } });
  await expect(page.getByTestId('save-draft')).toBeEnabled();
  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();

  const savedDocument = context.draft!.document as unknown as DraftDocument;
  expect(savedDocument.title).toBe('Edited article title');
  expect(savedDocument.excerpt).toBe('Edited article excerpt.');
  expect(savedDocument.byline).toBe('Edited editorial team');
  expect(savedDocument.bodyMarkdown).toContain(
    '## A revised section\n\nEdited first section paragraph.'
  );
  expect(savedDocument.bodyMarkdown).toContain('kicker: A new beginning');
  expect(savedDocument.bodyMarkdown).toContain(
    'caption: Edited standalone caption'
  );
  expect(savedDocument.bodyMarkdown).toContain(
    'description: Guests met one another.'
  );
  expect(savedDocument.bodyMarkdown).toContain(
    'text: Edited effort remains remarkable.'
  );
  expect(savedDocument.media[1].description).toBe(
    'Edited Draft-only gallery description'
  );
  expect(savedDocument.media[1].descriptionSource).toBe('user');
  expect(savedDocument.media[1].descriptionStatus).toBe('confirmed');
  expect(savedDocument.media[2].description).toBe(
    'Edited Draft-only video description'
  );
  expect(savedDocument.media[2].descriptionSource).toBe('user');
  expect(savedDocument.media[2].descriptionStatus).toBe('confirmed');
  expect(context.manifest.sources.map((source) => source.description)).toEqual(
    materialDescriptions
  );

  for (const layout of [
    'brand-default',
    'field-notes',
    'editorial-feature',
  ] as const) {
    await page.getByTestId('draft-layout-select').click();
    await page.getByTestId(`draft-layout-option-${layout}`).click();
    for (const canvas of ['desktop', 'mobile'] as const) {
      await page.getByTestId(`draft-canvas-${canvas}`).click();
      await expect(article).toHaveAttribute('data-layout', layout);
      await expect
        .poll(() =>
          article.evaluate(
            (element) => element.scrollWidth <= element.clientWidth + 1
          )
        )
        .toBe(true);
      await expect(article.locator('[data-wxpost-edit-key]')).not.toHaveCount(
        0
      );
    }
  }

  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v3')).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Edited article title'
  );
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Edited Draft-only gallery description'
  );
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'The editorial team'
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByTestId('draft-canvas-mobile').click();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth
      )
    )
    .toBe(true);
  await expect(
    page
      .getByTestId('wxpost-article')
      .locator('[data-wxpost-edit-label="section kicker"]')
  ).toBeVisible();
});

test('rejects empty required item fields and deletes structured items explicitly', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  workspace.nextGeneratedDocument = completeDraftDocument();

  await page.getByTestId('generate-draft').click();
  const article = page.getByTestId('wxpost-article');

  const requiredValue = article
    .locator('[data-wxpost-edit-label="info value"]')
    .first();
  await requiredValue.click();
  const requiredEditor = page.getByRole('textbox', {
    name: 'Edit info value',
  });
  await requiredEditor.fill('');
  await expect(requiredEditor).toHaveText('Thirty');
  await expect(
    page.getByText('This field cannot be empty. Use Delete item to remove it.')
  ).toBeVisible();
  await expect(page.getByTestId('save-draft')).toBeDisabled();

  await replaceEditableText(page, 'timeline item description', '');
  await article.click({ position: { x: 5, y: 5 } });
  await expect(
    article.locator('[data-wxpost-edit-label="timeline item description"]')
  ).toHaveCount(1);

  const firstInfoItem = article
    .locator('[data-wxpost-item-container]')
    .filter({ hasText: 'Guests' });
  await firstInfoItem.hover();
  await firstInfoItem.getByRole('button', { name: 'Delete info item' }).click();
  const deleteDialog = page.getByTestId('delete-draft-directive-item-dialog');
  await expect(deleteDialog).toContainText(
    'This removes the item from the local Draft.'
  );
  await deleteDialog.getByRole('button', { name: 'Delete item' }).click();
  await expect(article).not.toContainText('Guests');
  await expect(article).toContainText('Theme');

  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  let savedDocument = context.draft!.document as unknown as DraftDocument;
  expect(savedDocument.bodyMarkdown).not.toContain('label: Guests');
  expect(savedDocument.bodyMarkdown).not.toContain(
    'description: Guests found their seats.'
  );
  expect(savedDocument.bodyMarkdown).toContain(':::info-grid');

  const finalInfoItem = article
    .locator('[data-wxpost-item-container]')
    .filter({ hasText: 'Theme' });
  await finalInfoItem.hover();
  await finalInfoItem.getByRole('button', { name: 'Delete info item' }).click();
  await expect(deleteDialog).toContainText(
    'deleting it will remove the whole block'
  );
  await deleteDialog.getByRole('button', { name: 'Delete item' }).click();
  await expect(article).not.toContainText('At a glance');

  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v3')).toBeVisible();
  savedDocument = context.draft!.document as unknown as DraftDocument;
  expect(savedDocument.bodyMarkdown).not.toContain(':::info-grid');
});

test('round-trips every accepted Markdown block without losing semantics', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  workspace.nextGeneratedDocument = draftDocument(
    'Markdown round trip',
    `#### A smaller heading

Text before ![Reference image](https://assets.example/reference.jpg "Reference") after.

3. Third item
4. Fourth item

| Left | Center | Right |
| :--- | :---: | ---: |
| A | B | C |`
  );

  await page.getByTestId('generate-draft').click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  const article = page.getByTestId('wxpost-article');

  await replaceEditableText(page, 'section heading', 'A revised small heading');

  await article.locator('[data-wxpost-edit-label="paragraph"]').click();
  const paragraphEditor = page.getByRole('textbox', { name: 'Edit paragraph' });
  await paragraphEditor.press('End');
  await paragraphEditor.pressSequentially(' continued');

  await article.locator('[data-wxpost-edit-label="list"]').click();
  const listEditor = page.getByRole('textbox', { name: 'Edit list' });
  await listEditor.press('End');
  await listEditor.pressSequentially('!');

  await article.locator('[data-wxpost-edit-label="table"]').click();
  const tableEditor = page.getByRole('textbox', { name: 'Edit table' });
  await tableEditor.press('End');
  await tableEditor.pressSequentially(' | note!');

  await article.click({ position: { x: 5, y: 5 } });
  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();

  const body = context.draft!.document.bodyMarkdown as string;
  expect(body).toContain('#### A revised small heading');
  expect(body).toContain(
    '![Reference image](https://assets.example/reference.jpg "Reference")'
  );
  expect(body).toContain('3. Third item');
  expect(body).toContain('4. Fourth item!');
  expect(body).toContain('| --- | :---: | ---: |');
  expect(body).toContain('| A | B \\| note! | C |');
});

test('selects, saves, and removes a cover-only workspace image', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  await page.getByTestId('material-file-input').setInputFiles({
    name: 'article-photo.png',
    mimeType: 'image/png',
    buffer: Buffer.from('article-photo'),
  });
  await page.getByTestId('material-file-input').setInputFiles({
    name: 'cover-only.png',
    mimeType: 'image/png',
    buffer: Buffer.from('cover-only'),
  });
  await expect(page.getByTestId('material-M01')).toBeVisible();
  await expect(page.getByTestId('material-M02')).toBeVisible();
  await page.getByTestId('generate-draft').click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  const context = Array.from(workspace.contexts.values())[0];
  const coverSource = context.manifest.sources.find(
    (source) => source.filename === 'cover-only.png'
  );
  expect(coverSource).toBeDefined();
  const coverId = coverSource!.id;

  await page.getByTestId('open-cover-picker').click();
  const coverPicker = page.getByTestId('cover-picker-dialog');
  await expect(coverPicker).toContainText(
    'The cover does not have to appear inside the article.'
  );
  await expect(page.getByTestId(`cover-candidate-${coverId}`)).toContainText(
    'Not in article'
  );
  await page.getByTestId(`cover-candidate-${coverId}`).click();
  await page.getByTestId('apply-cover-selection').click();

  await expect(page.getByTestId('open-cover-picker')).toHaveAccessibleName(
    `Cover: ${coverId}`
  );
  await expect(page.getByTestId('save-draft')).toBeEnabled();
  await expect(page.getByTestId('directive-image')).toHaveCount(0);
  expect(context.draft!.document.coverMediaId).toBeNull();

  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  expect(context.draft!.document.coverMediaId).toBe(coverId);
  expect(
    (context.draft!.document.media ?? []).map((media) => media.id)
  ).toEqual([coverId]);
  expect(context.draft!.document.bodyMarkdown).not.toContain(coverId);

  await page.getByTestId('open-cover-picker').click();
  await expect(page.getByTestId(`cover-candidate-${coverId}`)).toContainText(
    'Current cover'
  );
  await expect(page.getByTestId(`cover-candidate-${coverId}`)).toContainText(
    'Cover only'
  );
  await coverPicker.getByRole('button', { name: 'Cancel' }).click();

  await page.getByTestId('sync-public-wxpost').click();
  await page
    .getByTestId('publication-confirm-dialog')
    .getByRole('button', { name: 'Publish WxPost' })
    .click();
  await expect(page.getByTestId('publication-status')).toHaveText(
    'Public revision 1 · from Draft v2 · up to date'
  );

  await page.getByTestId('draft-mode-preview').click();
  await expect(page.getByTestId('open-cover-picker')).toBeDisabled();
  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId(`workspace-${coverId}`).click();
  const blockedDialog = page.getByTestId('delete-material-dialog');
  await expect(blockedDialog).toContainText(
    'This material is the cover of Draft v2.'
  );
  await expect(blockedDialog).toContainText('Change or remove the cover.');
  await blockedDialog.getByRole('button', { name: 'Go to Draft' }).click();

  await page.getByTestId('draft-mode-edit').click();
  await page.getByTestId('open-cover-picker').click();
  await coverPicker.getByRole('button', { name: 'Remove cover' }).click();
  await page.getByTestId('apply-cover-selection').click();
  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v3')).toBeVisible();
  expect(context.draft!.document.coverMediaId).toBeNull();
  expect(context.draft!.document.media).toEqual([]);

  await page.getByTestId('open-cover-picker').click();
  await expect(
    page.getByTestId(`cover-candidate-${coverId}`)
  ).not.toContainText('Current cover');
  await expect(page.getByTestId(`cover-candidate-${coverId}`)).toContainText(
    'Not in article'
  );
  await coverPicker.getByRole('button', { name: 'Cancel' }).click();

  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId(`workspace-${coverId}`).click();
  await page
    .getByTestId('delete-material-dialog')
    .getByRole('button', { name: 'Delete' })
    .click();
  await expect(page.getByTestId(`material-${coverId}`)).toHaveCount(0);
});

test('attempts a failed cover-only preview once per dialog opening', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  await page.getByTestId('material-file-input').setInputFiles({
    name: 'cover-only.png',
    mimeType: 'image/png',
    buffer: Buffer.from('cover-only'),
  });
  await expect(page.getByText('cover-only.png', { exact: true })).toBeVisible();
  const context = Array.from(workspace.contexts.values())[0];
  const coverSource = context.manifest.sources.find(
    (source) => source.filename === 'cover-only.png'
  );
  expect(coverSource).toBeDefined();
  workspace.nextGeneratedDocument = draftDocument(
    'Cover preview failure',
    'The Draft remains usable without body media.'
  );
  workspace.failSourceContent = true;
  await page.getByTestId('generate-draft').click();

  const requestName = `GET /sources/${coverSource!.id}/content`;
  const requestCount = () =>
    workspace.requests.filter((request) => request === requestName).length;
  const requestsBeforeOpening = requestCount();
  await page.getByTestId('open-cover-picker').click();
  await expect.poll(requestCount).toBe(requestsBeforeOpening + 1);
  await page.waitForTimeout(300);
  expect(requestCount()).toBe(requestsBeforeOpening + 1);

  const dialog = page.getByTestId('cover-picker-dialog');
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await page.getByTestId('open-cover-picker').click();
  await expect.poll(requestCount).toBe(requestsBeforeOpening + 2);
  await page.waitForTimeout(300);
  expect(requestCount()).toBe(requestsBeforeOpening + 2);
});
