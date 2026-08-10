import { expect, type Page } from '@playwright/test';

import {
  draftDocument,
  openAuthoringPage,
  type DraftDocument,
} from './wxpostAuthoring';

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

export function completeDraftDocument(): DraftDocument {
  return {
    ...draftDocument('A complete editable Draft', COMPLETE_DRAFT_MARKDOWN),
    media: [
      {
        id: 'M01',
        kind: 'image',
        sourceUrl: 'https://workspace.invalid/materials/M01',
        description: 'Portrait of Jamie at the lectern.',
        include: true,
        order: 1,
        descriptionSource: 'user',
        descriptionStatus: 'confirmed',
      },
      {
        id: 'M02',
        kind: 'image',
        sourceUrl: 'https://workspace.invalid/materials/M02',
        description: 'Members listening together.',
        include: true,
        order: 2,
        descriptionSource: 'ai',
        descriptionStatus: 'needs_confirmation',
      },
      {
        id: 'M03',
        kind: 'video',
        sourceUrl: 'https://workspace.invalid/materials/M03',
        description: 'Closing applause on video.',
        include: true,
        order: 3,
        descriptionSource: 'ai',
        descriptionStatus: 'needs_confirmation',
      },
    ],
  };
}

export async function replaceEditableText(
  page: Page,
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

export async function createAndGenerateDraft(page: Page) {
  const workspace = await openAuthoringPage(page);
  await page.getByTestId('create-workspace').click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId('generate-draft')).toBeEnabled();
  await page.getByTestId('generate-draft').click();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  return workspace;
}
