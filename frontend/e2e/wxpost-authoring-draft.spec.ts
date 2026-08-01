import { expect, test } from '@playwright/test';

import {
  draftDocument,
  openAuthoringPage,
  type DraftDocument,
} from './support/wxpostAuthoring';

const COMPLETE_DRAFT_MARKDOWN = `Opening paragraph for direct editing.

Second opening paragraph.

- First principle
- Second principle

> A visible quotation block.

:::section
kicker: The beginning
:::

## A section heading

First section paragraph.

Second section paragraph.

:::image
media: M01
caption: A standalone image caption
:::

:::gallery
items:
  - M02
caption: A gallery heading
:::

:::video
media: M03
caption: A video heading
:::

:::takeaway
title: A useful takeaway
text: Keep the lesson close.
:::

:::person
name: Jamie Lee
role: Toastmaster
media: M01
summary: Jamie welcomed every guest.
quote: Make room for every voice.
:::

:::info-grid
title: At a glance
items:
  - label: Guests
    value: Thirty
  - label: Theme
    value: Belonging
:::

:::timeline
title: The evening
items:
  - label: 7 PM
    title: Welcome
    description: Guests found their seats.
  - label: 8 PM
    title: Speeches
    description: Members shared prepared stories.
:::

:::pull-quote
text: Ordinary effort can still be remarkable.
attribution: Meeting 462
:::`;

function completeDraftDocument(): DraftDocument {
  return {
    ...draftDocument('A complete editable Draft', COMPLETE_DRAFT_MARKDOWN),
    media: [
      {
        id: 'M01',
        kind: 'image',
        sourceUrl: '',
        description: 'Portrait of Jamie at the lectern.',
        include: true,
        order: 1,
        descriptionSource: 'user',
        descriptionStatus: 'confirmed',
      },
      {
        id: 'M02',
        kind: 'image',
        sourceUrl: '',
        description: 'Members listening together.',
        include: true,
        order: 2,
        descriptionSource: 'ai',
        descriptionStatus: 'needs_confirmation',
      },
      {
        id: 'M03',
        kind: 'video',
        sourceUrl: '',
        description: 'Closing applause on video.',
        include: true,
        order: 3,
        descriptionSource: 'ai',
        descriptionStatus: 'needs_confirmation',
      },
    ],
  };
}

async function replaceEditableText(
  page: Parameters<typeof openAuthoringPage>[0],
  label: string,
  value: string,
  index = 0
) {
  const target = page.locator(`[data-wxpost-edit-label="${label}"]`).nth(index);
  await target.click();
  const editor = page.getByRole('textbox', {
    name: `Edit ${label}`,
  });
  await expect(editor).toBeFocused();
  await editor.fill(value);
}

async function createAndGenerateDraft(
  page: Parameters<typeof openAuthoringPage>[0]
) {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId('generate-draft')).toBeEnabled();
  await page.getByTestId('generate-draft').click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  return workspace;
}

test('opens an existing Draft directly in Preview mode', async ({ page }) => {
  const workspace = await createAndGenerateDraft(page);
  const workspaceId = Array.from(workspace.contexts.keys())[0];
  const workspaceKey = workspaceId.replace(/^wxpost-/, '');

  await page.goto(`/posts/wxposts/edit/${workspaceKey}?view=preview`);

  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  await expect(page.getByTestId('draft-mode-preview')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(
    page.getByRole('heading', { name: 'Draft Assistant' })
  ).toBeHidden();
  await expect(page.getByTestId('wxpost-article')).toBeVisible();
});

test('keeps local Draft edits isolated until an explicit Save Draft', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);
  const context = Array.from(workspace.contexts.values())[0];

  await expect(page.getByText('Draft · v1')).toBeVisible();
  await expect(
    page.getByTestId('draft-workbench').locator(':scope > header')
  ).toContainText('Saved');
  await expect(page.getByTestId('save-draft')).toBeDisabled();

  const savedTitle = context.draft!.document.title as string;
  const article = page.getByTestId('wxpost-article');
  const titleHeading = article.getByRole('heading', { level: 1 });
  await titleHeading.hover();
  await expect
    .poll(() =>
      titleHeading.evaluate((element) => getComputedStyle(element).outline)
    )
    .toBe('rgb(147, 197, 253) solid 1px');
  await titleHeading.click();
  const titleInput = page.getByRole('textbox', { name: 'Edit draft title' });
  await expect
    .poll(() =>
      titleInput.evaluate((element) => getComputedStyle(element).outline)
    )
    .toBe('rgb(59, 130, 246) solid 2px');
  await titleInput.fill('A local title that is not saved yet');

  await expect(
    page.getByTestId('draft-workbench').locator(':scope > header')
  ).toContainText('Unsaved changes');
  await expect(page.getByTestId('save-draft')).toBeEnabled();
  await expect(page.getByTestId('regenerate-draft')).toBeDisabled();
  expect(context.draft!.document.title).toBe(savedTitle);

  await article.click({ position: { x: 5, y: 5 } });
  await expect(titleInput).toBeHidden();
  await expect(article.getByRole('heading', { level: 1 })).toHaveText(
    'A local title that is not saved yet'
  );

  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId('workspace-M01').click();
  await expect(
    page
      .getByTestId('material-M01')
      .getByRole('button', { name: 'Delete meeting-room.jpg from workspace' })
  ).toBeVisible();
  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await article.getByRole('heading', { level: 1 }).click();
  await expect(titleInput).toHaveText('A local title that is not saved yet');

  await page.getByTestId('draft-mode-preview').click();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'A local title that is not saved yet'
  );
  await expect(
    page.getByRole('heading', { name: 'Draft Assistant' })
  ).toBeHidden();
  await expect(page.getByTestId('draft-presentation-controls')).toBeVisible();
  expect(context.draft!.document.title).toBe(savedTitle);

  await page.getByTestId('draft-mode-edit').click();
  await page
    .getByTestId('wxpost-article')
    .getByRole('heading', { level: 1 })
    .click();
  await expect(
    page.getByRole('textbox', { name: 'Edit draft title' })
  ).toHaveText('A local title that is not saved yet');
  await page.getByTestId('save-draft').click();
  await expect(
    page.getByText('Draft saved successfully!', { exact: true })
  ).toBeVisible();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(
    page.getByTestId('draft-workbench').locator(':scope > header')
  ).toContainText('Saved');
  expect(context.draft!.draftVersion).toBe(2);
  expect(context.draft!.document.title).toBe(
    'A local title that is not saved yet'
  );

  const markdownSegment = page.getByTestId('markdown-segment');
  const sectionParagraph = markdownSegment.getByText(
    'Generated from saved Materials as version 1.'
  );
  const heightBeforeEditing = (await sectionParagraph.boundingBox())!.height;
  await sectionParagraph.hover();
  await expect
    .poll(() =>
      sectionParagraph.evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          outlineColor: style.outlineColor,
          outlineStyle: style.outlineStyle,
          outlineWidth: style.outlineWidth,
        };
      })
    )
    .toEqual({
      outlineColor: 'rgb(147, 197, 253)',
      outlineStyle: 'solid',
      outlineWidth: '1px',
    });
  await sectionParagraph.click();
  const bodyEditor = page.getByRole('textbox', {
    name: 'Edit paragraph',
  });
  await expect
    .poll(() =>
      sectionParagraph.evaluate((element) => {
        return {
          paragraphOutline: getComputedStyle(element).outline,
          segmentOutline: getComputedStyle(
            element.closest('[data-testid="markdown-segment"]')!
          ).outlineStyle,
        };
      })
    )
    .toEqual({
      paragraphOutline: 'rgb(59, 130, 246) solid 2px',
      segmentOutline: 'none',
    });
  await expect(bodyEditor).not.toContainText('##');
  const heightAfterEditing = (await sectionParagraph.boundingBox())!.height;
  expect(Math.abs(heightAfterEditing - heightBeforeEditing)).toBeLessThan(2);

  await expect(bodyEditor).toBeFocused();
  await page.keyboard.press('End');
  await page.keyboard.type(' revised');
  await expect(sectionParagraph).toHaveText(
    'Generated from saved Materials as version 1. revised'
  );
  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v3')).toBeVisible();
  expect(context.draft!.draftVersion).toBe(3);
  expect(context.draft!.document.bodyMarkdown).toBe(
    '## Generated section\n\nGenerated from saved Materials as version 1. revised'
  );
  expect(
    (context.draft!.document.bodyMarkdown as string).match(
      /Generated from saved Materials as version 1\. revised/g
    )
  ).toHaveLength(1);
});

test('edits every Draft text source precisely and persists it without changing Materials', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  context.manifest.sources.forEach((source, index) => {
    source.workspaceReady = true;
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

test('preserves the saved Draft across generation, chat, and conflict failures', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];

  workspace.failNextDraftGeneration = true;
  await page.getByTestId('generate-draft').click();
  await expect
    .poll(() =>
      page
        .getByRole('status')
        .filter({ hasText: 'Hermes is temporarily unavailable' })
        .count()
    )
    .toBeGreaterThan(0);
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  expect(context.draft).toBeNull();

  workspace.draftSessionUnavailable = true;
  await page.getByTestId('generate-draft').click();
  await expect(page.getByText('Draft · v1')).toBeVisible();
  await expect(page.getByText('Unavailable', { exact: true })).toBeVisible();
  workspace.draftSessionUnavailable = false;
  const generatedTitle = context.draft!.document.title;

  workspace.failNextDraftGeneration = true;
  await page.getByTestId('regenerate-draft').click();
  await expect
    .poll(() =>
      page
        .getByRole('status')
        .filter({ hasText: 'Hermes is temporarily unavailable' })
        .count()
    )
    .toBeGreaterThan(0);
  await expect(page.getByText('Draft · v1')).toBeVisible();
  expect(context.draft!.draftVersion).toBe(1);
  expect(context.draft!.document.title).toBe(generatedTitle);

  const chatInput = page.getByPlaceholder(
    'Ask the assistant to revise the Draft…'
  );
  await chatInput.fill('Make the opening warmer.');
  workspace.failNextDraftChat = true;
  await page.getByTestId('send-draft-chat').click();
  await expect(
    page.getByTestId('draft-workbench').getByRole('alert')
  ).toBeVisible();
  await expect(page.getByTestId('draft-workbench')).toContainText(
    'Hermes could not revise the draft'
  );
  expect(context.draft!.draftVersion).toBe(1);
  expect(context.draft!.document.title).toBe(generatedTitle);
  await expect(chatInput).toHaveValue('Make the opening warmer.');
  await expect(
    page
      .getByTestId('draft-chat-history')
      .getByText('Make the opening warmer.', { exact: true })
  ).toHaveCount(0);

  await page.getByTestId('send-draft-chat').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(page.getByText('Online', { exact: true })).toBeVisible();
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'Make the opening warmer.'
  );
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'I revised the saved draft'
  );
  expect(context.draft!.draftVersion).toBe(2);
  expect(context.draft!.document.title).toBe('Hermes revision v2');

  await page
    .getByTestId('wxpost-article')
    .getByRole('heading', { level: 1 })
    .click();
  const titleInput = page.getByRole('textbox', { name: 'Edit draft title' });
  await titleInput.fill('Keep this local title after the conflict');
  await expect(titleInput).toHaveText(
    'Keep this local title after the conflict'
  );
  await chatInput.fill('This request cannot run against unsaved edits.');
  await expect(page.getByTestId('send-draft-chat')).toBeDisabled();

  context.draft = {
    draftVersion: 3,
    document: draftDocument(
      'Saved in another tab',
      '## External update\n\nThis is the authoritative saved version.'
    ),
  };
  context.manifest.draft = {
    version: 3,
    sourceManifestVersion: context.manifest.manifestVersion,
    sha256: 'draft-3',
  };
  await page.getByTestId('save-draft').click();
  const conflictDialog = page.getByTestId('draft-conflict-dialog');
  await expect(conflictDialog).toBeVisible();
  await expect(conflictDialog).toContainText(
    'Loading the latest version will discard your unsaved Draft changes.'
  );
  await expect(
    page.getByText(
      'This workspace or draft changed elsewhere. Your local edits were kept; reload the workspace before saving again.'
    )
  ).toHaveCount(0);
  await expect(titleInput).toBeHidden();
  await expect(
    page.getByTestId('wxpost-article').getByRole('heading', { level: 1 })
  ).toHaveText('Keep this local title after the conflict');
  await expect(page.getByText('Draft · v2')).toBeVisible();

  await conflictDialog
    .getByRole('button', { name: 'Keep current edits' })
    .click();
  await expect(conflictDialog).toHaveCount(0);
  await expect(
    page.getByTestId('wxpost-article').getByRole('heading', { level: 1 })
  ).toHaveText('Keep this local title after the conflict');

  await page.getByTestId('save-draft').click();
  await expect(conflictDialog).toBeVisible();
  await conflictDialog.getByRole('button', { name: 'Load latest' }).click();
  await expect(conflictDialog).toHaveCount(0);
  await expect(page.getByText('Draft · v3')).toBeVisible();
  await expect(
    page.getByTestId('wxpost-article').getByRole('heading', { level: 1 })
  ).toHaveText('Saved in another tab');
});

test('shows a regenerated Draft immediately and reloads the latest Draft after a conflict', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);
  const context = Array.from(workspace.contexts.values())[0];

  workspace.nextGeneratedDocument = draftDocument(
    'Regenerated without a reload',
    '## Updated section\n\nThis version should appear immediately.'
  );
  await page.getByTestId('regenerate-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Regenerated without a reload'
  );

  context.draft = {
    draftVersion: 3,
    document: draftDocument(
      'Saved in another tab',
      '## External update\n\nThis is the authoritative saved version.'
    ),
  };
  context.manifest.draft = {
    version: 3,
    sourceManifestVersion: context.manifest.manifestVersion,
    sha256: 'draft-3',
  };

  await page.getByTestId('regenerate-draft').click();
  const conflictDialog = page.getByTestId('draft-conflict-dialog');
  await expect(conflictDialog).toBeVisible();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Regenerated without a reload'
  );
  await conflictDialog.getByRole('button', { name: 'Load latest' }).click();
  await expect(conflictDialog).toHaveCount(0);
  await expect(page.getByText('Draft · v3')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Saved in another tab'
  );
  await expect(page.getByTestId('draft-workbench')).toContainText('Saved');
});

test('generates only saved Materials and previews the same local Draft working copy', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];

  await page
    .getByTestId('description-M01')
    .fill('This description is still local.');
  await expect(page.getByTestId('generate-draft')).toBeDisabled();
  await expect(page.getByTestId('save-materials')).toBeEnabled();
  expect(context.manifest.sources[0].description).toBe('');

  await page.getByTestId('save-materials').click();
  await expect(page.getByTestId('generate-draft')).toBeEnabled();
  expect(context.manifest.sources[0].description).toBe(
    'This description is still local.'
  );

  await page.getByTestId('generate-draft').click();
  await expect(page.getByText('Draft · v1')).toBeVisible();
  await page
    .getByTestId('wxpost-article')
    .getByRole('heading', { level: 1 })
    .click();
  await page
    .getByRole('textbox', { name: 'Edit draft title' })
    .fill('Unsaved Draft title');
  await page.getByTestId('draft-palette-select').click();
  await page.getByTestId('draft-palette-option-paper-neutral').click();
  await page.getByTestId('draft-mode-preview').click();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Unsaved Draft title'
  );
  await expect(page.getByTestId('wxpost-article')).toHaveAttribute(
    'data-palette',
    'paper-neutral'
  );
  await expect(page.getByTestId('save-draft')).toBeEnabled();
  expect(context.draft!.document.title).toBe('Generated draft v1');
  expect(context.draft!.document.presentation).toEqual({
    layout: 'brand-default',
    palette: 'paper-neutral',
    appearance: 'light',
    typeface: 'editorial-serif',
  });

  await page.getByTestId('save-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  expect(context.draft!.document.presentation).toEqual({
    layout: 'brand-default',
    palette: 'paper-neutral',
    appearance: 'light',
    typeface: 'editorial-serif',
  });

  await page.getByTestId('draft-canvas-mobile').click();
  await expect(page.getByTestId('wxpost-stage')).toHaveAttribute(
    'data-preview-size',
    'mobile-390'
  );
  await expect(page.getByTestId('save-draft')).toBeDisabled();
});

test('keeps the balanced workbench usable without horizontal overflow on mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await createAndGenerateDraft(page);

  const workbench = page.getByTestId('draft-workbench');
  const article = workbench.getByTestId('wxpost-stage');
  const articleBox = await article.boundingBox();
  expect(articleBox).not.toBeNull();
  await expect(
    workbench.getByRole('heading', { name: 'Draft Assistant' })
  ).toBeHidden();
  const mobileHermesButton = page.getByTestId('open-mobile-hermes');
  await expect(mobileHermesButton).toBeVisible();
  const mobileHermesButtonBox = await mobileHermesButton.boundingBox();
  expect(mobileHermesButtonBox).not.toBeNull();
  expect(mobileHermesButtonBox!.y + mobileHermesButtonBox!.height).toBeLessThan(
    articleBox!.y
  );
  const presentationControls = page.getByTestId('draft-presentation-controls');
  await expect(presentationControls.getByText('Appearance')).toBeVisible();
  await expect(presentationControls.getByText('Typeface')).toBeVisible();
  await expect(presentationControls.getByText('Canvas')).toBeVisible();
  await expect(page.getByTestId('draft-canvas-mobile')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth
    )
  ).toBe(true);

  await expect(page.getByTestId('regenerate-draft')).toBeVisible();
  await expect(page.getByTestId('save-draft')).toBeVisible();
  await expect(page.getByRole('button', { name: /Materials/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /^3 Draft$/ })).toBeVisible();

  await mobileHermesButton.click();
  await expect(page.getByTestId('mobile-hermes-dialog')).toBeVisible();
  await expect(
    page
      .getByTestId('mobile-hermes-dialog')
      .getByRole('heading', { name: 'Draft Assistant' })
  ).toBeVisible();
  await page
    .getByTestId('mobile-hermes-dialog')
    .getByRole('button', { name: 'Close Draft Assistant' })
    .click();
  await expect(page.getByTestId('mobile-hermes-dialog')).toBeHidden();
});

test('keeps Draft controls compact at intermediate viewport widths', async ({
  page,
}) => {
  await createAndGenerateDraft(page);

  for (const testId of [
    'draft-layout-select',
    'draft-palette-select',
    'draft-appearance-select',
    'draft-typeface-select',
  ]) {
    const select = page.getByTestId(testId);
    await expect(select).toHaveCSS('height', '36px');
    await expect(select).toHaveCSS('border-radius', '6px');
    await expect(select).toHaveCSS('border-color', 'rgb(209, 213, 219)');
    await expect(select).toHaveCSS('font-size', '14px');
    await expect(select).toHaveCSS('font-weight', '400');
  }

  await page.getByTestId('draft-layout-select').click();
  const layoutOptions = page.getByRole('listbox', { name: 'Layout' });
  await expect(layoutOptions).toBeVisible();
  await expect(layoutOptions.locator('..')).toHaveCSS(
    'background-color',
    'rgb(255, 255, 255)'
  );
  await expect(page.getByTestId('draft-layout-option-brand-default')).toHaveCSS(
    'background-color',
    'rgb(232, 239, 255)'
  );
  await page.keyboard.press('Escape');
  await expect(layoutOptions).toBeHidden();

  for (const width of [308, 520, 700]) {
    await page.setViewportSize({ width, height: 844 });

    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth
      )
    ).toBe(true);

    const modeBox = await page
      .locator('[aria-label="Draft mode"]')
      .boundingBox();
    const editBox = await page.getByTestId('draft-mode-edit').boundingBox();
    const previewBox = await page
      .getByTestId('draft-mode-preview')
      .boundingBox();
    const hermesBox = await page
      .getByTestId('open-mobile-hermes')
      .boundingBox();
    const regenerateBox = await page
      .getByTestId('regenerate-draft')
      .boundingBox();
    const saveBox = await page.getByTestId('save-draft').boundingBox();
    expect(modeBox).not.toBeNull();
    expect(editBox).not.toBeNull();
    expect(previewBox).not.toBeNull();
    expect(hermesBox).not.toBeNull();
    expect(regenerateBox).not.toBeNull();
    expect(saveBox).not.toBeNull();
    expect(Math.abs(modeBox!.y - hermesBox!.y)).toBeLessThan(2);
    expect(Math.abs(modeBox!.y - regenerateBox!.y)).toBeLessThan(2);
    expect(Math.abs(modeBox!.y - saveBox!.y)).toBeLessThan(2);
    expect(regenerateBox!.width).toBeLessThanOrEqual(48);
    expect(saveBox!.width).toBeLessThanOrEqual(48);
    if (width <= 360) {
      expect(editBox!.width).toBeLessThanOrEqual(48);
      expect(previewBox!.width).toBeLessThanOrEqual(48);
    }

    const presentationControls = page.getByTestId(
      'draft-presentation-controls'
    );
    await expect(presentationControls).toHaveCSS('display', 'grid');
    const layoutBox = await page
      .getByTestId('draft-layout-select')
      .boundingBox();
    const paletteBox = await page
      .getByTestId('draft-palette-select')
      .boundingBox();
    const appearanceBox = await page
      .getByTestId('draft-appearance-select')
      .boundingBox();
    const typefaceBox = await page
      .getByTestId('draft-typeface-select')
      .boundingBox();
    expect(layoutBox).not.toBeNull();
    expect(paletteBox).not.toBeNull();
    expect(appearanceBox).not.toBeNull();
    expect(typefaceBox).not.toBeNull();
    expect(Math.abs(layoutBox!.y - paletteBox!.y)).toBeLessThan(2);
    expect(Math.abs(appearanceBox!.y - typefaceBox!.y)).toBeLessThan(2);

    if (width === 308) {
      for (const control of [
        { name: 'layout', option: 'editorial-feature' },
        { name: 'palette', option: 'warm-terracotta' },
        { name: 'typeface', option: 'editorial-serif' },
      ]) {
        await page.getByTestId(`draft-${control.name}-select`).click();
        const option = page.getByTestId(
          `draft-${control.name}-option-${control.option}`
        );
        const menuBox = await option.locator('../..').boundingBox();
        expect(menuBox).not.toBeNull();
        expect(menuBox!.width).toBeGreaterThanOrEqual(180);
        expect(menuBox!.x).toBeGreaterThanOrEqual(0);
        expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(width);
        expect(await option.evaluate((element) => element.scrollWidth)).toBe(
          await option.evaluate((element) => element.clientWidth)
        );
        expect((await option.boundingBox())!.height).toBeLessThanOrEqual(40);
        await page.keyboard.press('Escape');
      }
    }
  }
});

test('keeps the desktop Hermes composer visible while long history scrolls', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 844 });
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const workspaceId = Array.from(workspace.contexts.keys())[0];
  workspace.draftMessages.set(
    workspaceId,
    Array.from({ length: 24 }, (_, index) => ({
      role: index % 2 === 0 ? ('user' as const) : ('assistant' as const),
      text: `Hermes conversation turn ${index + 1} with enough text to exercise the scrolling history.`,
    }))
  );

  await page.getByTestId('generate-draft').click();
  const panel = page.getByTestId('desktop-hermes-panel');
  await expect(panel).toBeVisible();
  await panel.evaluate((element) =>
    element.scrollIntoView({ block: 'start', behavior: 'auto' })
  );

  const panelBox = await panel.boundingBox();
  const history = page.getByTestId('draft-chat-history');
  const historyBox = await history.boundingBox();
  const composer = page.getByTestId('draft-chat-composer');
  const composerBox = await composer.boundingBox();
  expect(panelBox).not.toBeNull();
  expect(historyBox).not.toBeNull();
  expect(composerBox).not.toBeNull();
  expect(panelBox!.width).toBeGreaterThanOrEqual(360);
  expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(844);
  expect(composerBox!.y).toBeGreaterThanOrEqual(
    historyBox!.y + historyBox!.height - 1
  );
  expect(
    Math.abs(
      composerBox!.y + composerBox!.height - (panelBox!.y + panelBox!.height)
    )
  ).toBeLessThanOrEqual(1);
  const textarea = page.getByPlaceholder(
    'Ask the assistant to revise the Draft…'
  );
  await expect(textarea).toBeInViewport();
  await expect(textarea).toHaveCSS('resize', 'none');
  const initialTextareaHeight = (await textarea.boundingBox())!.height;
  await textarea.fill('Line one\nLine two\nLine three\nLine four\nLine five');
  expect((await textarea.boundingBox())!.height).toBeGreaterThan(
    initialTextareaHeight
  );
  await textarea.fill(
    Array.from({ length: 20 }, (_, index) => `Line ${index + 1}`).join('\n')
  );
  expect((await textarea.boundingBox())!.height).toBeLessThanOrEqual(160);
  expect(
    await textarea.evaluate(
      (element) => element.scrollHeight > element.clientHeight
    )
  ).toBe(true);
  await textarea.fill('Short again');
  expect((await textarea.boundingBox())!.height).toBe(initialTextareaHeight);
  expect(
    await history.evaluate(
      (element) => element.scrollHeight > element.clientHeight
    )
  ).toBe(true);
  expect(
    await history.evaluate(
      (element) =>
        Math.abs(
          element.scrollHeight - element.scrollTop - element.clientHeight
        ) <= 1
    )
  ).toBe(true);
});

test('never exposes an older Draft as a newer version after validation fails', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);
  const context = Array.from(workspace.contexts.values())[0];
  const versionOneTitle = context.draft!.document.title;

  workspace.failDraftValidation = true;
  await page.getByTestId('regenerate-draft').click();

  expect(context.draft!.draftVersion).toBe(2);
  expect(context.draft!.document.title).not.toBe(versionOneTitle);
  await expect(
    page.getByText('Canonical renderer is unavailable', { exact: true })
  ).toBeVisible();
  await expect(page.getByTestId('draft-workbench')).toBeHidden();
  await expect(page.getByTestId('save-draft')).toBeHidden();
  await expect(page.getByText('Draft · v2')).toBeHidden();

  workspace.failDraftValidation = false;
  await page.reload();
  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    context.draft!.document.title
  );
});

test('does not revalidate an unchanged Draft after a Materials-only save', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  context.manifest.sources[0].workspaceReady = true;
  context.manifest.sources[0].included = true;
  const mediaDraft = draftDocument(
    'One material Draft',
    ':::image\nmedia: M01\n:::'
  );
  mediaDraft.media = [
    {
      id: 'M01',
      kind: 'image',
      sourceUrl: '',
      description: 'A generated article caption.',
      include: true,
      order: 0,
      descriptionSource: 'ai',
      descriptionStatus: 'needs_confirmation',
    },
  ];
  workspace.nextGeneratedDocument = mediaDraft;

  await page.getByTestId('generate-draft').click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  const validationCount = workspace.draftValidationRequests;

  await page.getByRole('button', { name: /Materials/ }).click();
  await page
    .getByTestId('description-M01')
    .fill('A revised Materials-only description.');
  await page.getByTestId('include-M01').click();
  await page.getByTestId('save-materials').click();
  await expect(page.getByTestId('save-materials')).toBeDisabled();
  expect(context.manifest.sources[0].included).toBe(false);
  expect(workspace.draftValidationRequests).toBe(validationCount);

  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  await expect(page.getByTestId('wxpost-article').locator('img')).toBeVisible();
  await expect(page.getByText('Missing image M01')).toHaveCount(0);
  expect(workspace.draftValidationRequests).toBe(validationCount);
});

test('reports a media download failure instead of rendering a missing-material placeholder', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  const context = Array.from(workspace.contexts.values())[0];
  context.manifest.sources.forEach((source) => {
    source.workspaceReady = true;
    source.included = true;
  });
  workspace.nextGeneratedDocument = completeDraftDocument();
  workspace.failSourceContent = true;

  await page.getByTestId('generate-draft').click();

  await expect(
    page.getByText('Draft media is temporarily unavailable', { exact: true })
  ).toBeVisible();
  await expect(page.getByText(/Missing (?:image|video) M0[1-3]/)).toHaveCount(
    0
  );
  await expect(page.getByTestId('draft-workbench')).toBeHidden();

  workspace.failSourceContent = false;
  await page.reload();
  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  await expect(page.getByText(/Missing (?:image|video) M0[1-3]/)).toHaveCount(
    0
  );
});

test('shows a renderer failure instead of leaving Draft loading forever', async ({
  page,
}) => {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  workspace.failDraftValidation = true;
  await page.getByTestId('generate-draft').click();

  await expect(
    page.getByText('Canonical renderer is unavailable', { exact: true })
  ).toBeVisible();
  await expect(
    page.getByText('Preparing Draft preview and media…')
  ).toBeHidden();
});
