import { expect, test } from '@playwright/test';

import { createAndGenerateDraft } from './support/wxpostDraft';
import { openAuthoringPage } from './support/wxpostAuthoring';

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
  expect(
    Math.abs(
      390 - (mobileHermesButtonBox!.x + mobileHermesButtonBox!.width) - 20
    )
  ).toBeLessThanOrEqual(2);
  expect(
    Math.abs(
      844 - (mobileHermesButtonBox!.y + mobileHermesButtonBox!.height) - 20
    )
  ).toBeLessThanOrEqual(2);
  expect(mobileHermesButtonBox!.width).toBe(48);
  expect(mobileHermesButtonBox!.height).toBe(48);
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

  await expect(page.getByTestId('discard-draft-changes')).toBeVisible();
  await expect(page.getByTestId('save-draft')).toBeVisible();
  await expect(page.getByRole('button', { name: /Materials/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /^3 Draft$/ })).toBeVisible();

  await page.getByRole('button', { name: /Materials/ }).click();
  await expect(mobileHermesButton).toBeHidden();
  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await expect(mobileHermesButton).toBeVisible();
  await page.getByTestId('draft-mode-preview').click();
  await expect(mobileHermesButton).toBeHidden();
  await page.getByTestId('draft-mode-edit').click();
  await expect(mobileHermesButton).toBeVisible();

  await mobileHermesButton.click();
  const mobileHermesDialog = page.getByTestId('mobile-hermes-dialog');
  await expect(mobileHermesDialog).toBeVisible();
  const dialogBox = await mobileHermesDialog.boundingBox();
  const sheetBox = await page.getByTestId('mobile-hermes-sheet').boundingBox();
  expect(dialogBox).toEqual({ x: 0, y: 0, width: 390, height: 844 });
  expect(sheetBox).not.toBeNull();
  expect(sheetBox!.x).toBeGreaterThanOrEqual(0);
  expect(sheetBox!.y).toBeGreaterThanOrEqual(0);
  expect(sheetBox!.x + sheetBox!.width).toBeLessThanOrEqual(390);
  expect(sheetBox!.y + sheetBox!.height).toBeLessThanOrEqual(844);
  await expect(
    mobileHermesDialog.getByRole('heading', { name: 'Draft Assistant' })
  ).toBeVisible();
  await mobileHermesDialog
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

  for (const width of [274, 308, 390, 430, 480, 520, 700, 768, 900, 1023]) {
    await page.setViewportSize({ width, height: 844 });

    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth
      )
    ).toBe(true);

    const modeBox = await page
      .locator('[aria-label="Draft mode"]')
      .boundingBox();
    const toolbarBox = await page
      .locator('[aria-label="Draft mode"]')
      .locator('..')
      .boundingBox();
    const editBox = await page.getByTestId('draft-mode-edit').boundingBox();
    const previewBox = await page
      .getByTestId('draft-mode-preview')
      .boundingBox();
    const floatingAssistantBox = await page
      .getByTestId('open-mobile-hermes')
      .boundingBox();
    const discardBox = await page
      .getByTestId('discard-draft-changes')
      .boundingBox();
    const coverBox = await page.getByTestId('open-cover-picker').boundingBox();
    const saveBox = await page.getByTestId('save-draft').boundingBox();
    const publicButton = page.getByTestId('sync-public-wxpost');
    const publicButtonBox = await publicButton.boundingBox();
    const publicationControlsBox = await page
      .getByTestId('draft-publication-controls')
      .boundingBox();
    const publicationStatusBox = await page
      .getByTestId('publication-status')
      .locator('..')
      .boundingBox();
    const publicationActionsBox = await page
      .getByTestId('publication-actions')
      .boundingBox();
    expect(modeBox).not.toBeNull();
    expect(toolbarBox).not.toBeNull();
    expect(editBox).not.toBeNull();
    expect(previewBox).not.toBeNull();
    expect(floatingAssistantBox).not.toBeNull();
    expect(discardBox).not.toBeNull();
    expect(coverBox).not.toBeNull();
    expect(saveBox).not.toBeNull();
    expect(publicButtonBox).not.toBeNull();
    expect(publicationControlsBox).not.toBeNull();
    expect(publicationStatusBox).not.toBeNull();
    expect(publicationActionsBox).not.toBeNull();
    expect(Math.abs(discardBox!.y - coverBox!.y)).toBeLessThanOrEqual(2);
    expect(Math.abs(discardBox!.y - saveBox!.y)).toBeLessThanOrEqual(2);
    expect(Math.abs(modeBox!.y - discardBox!.y)).toBeLessThanOrEqual(2);
    expect(floatingAssistantBox!.width).toBe(48);
    expect(floatingAssistantBox!.height).toBe(48);
    expect(
      Math.abs(
        width - (floatingAssistantBox!.x + floatingAssistantBox!.width) - 20
      )
    ).toBeLessThanOrEqual(2);
    expect(
      Math.abs(
        844 - (floatingAssistantBox!.y + floatingAssistantBox!.height) - 20
      )
    ).toBeLessThanOrEqual(2);
    if (width <= 900) {
      for (const box of [discardBox, coverBox, saveBox]) {
        expect(box!.width).toBe(40);
        expect(box!.height).toBe(40);
      }
      expect(publicButtonBox!.width).toBe(36);
      expect(publicButtonBox!.height).toBe(36);
      expect(
        Math.abs(
          toolbarBox!.x + toolbarBox!.width - (saveBox!.x + saveBox!.width)
        )
      ).toBeLessThanOrEqual(2);
    }
    expect(publicButtonBox!.x).toBeGreaterThanOrEqual(0);
    expect(publicButtonBox!.x + publicButtonBox!.width).toBeLessThanOrEqual(
      width
    );
    if (width <= 480) {
      expect(publicationActionsBox!.y).toBeGreaterThan(
        publicationStatusBox!.y + publicationStatusBox!.height - 2
      );
      expect(
        Math.abs(publicationActionsBox!.x - publicationControlsBox!.x)
      ).toBeLessThanOrEqual(2);
    } else if (width <= 900) {
      expect(
        Math.abs(
          publicationStatusBox!.y +
            publicationStatusBox!.height / 2 -
            (publicationActionsBox!.y + publicationActionsBox!.height / 2)
        )
      ).toBeLessThanOrEqual(2);
    }
    await expect(publicButton).toHaveText('Update Public WxPost');
    if (width <= 480) {
      expect(editBox!.width).toBeLessThanOrEqual(48);
      expect(previewBox!.width).toBeLessThanOrEqual(48);
    }

    const presentationControls = page.getByTestId(
      'draft-presentation-controls'
    );
    await expect(presentationControls).toHaveCSS(
      'display',
      width <= 760 ? 'grid' : 'flex'
    );
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
      await page.getByTestId('open-cover-picker').click();
      const coverDialog = page.getByTestId('cover-picker-dialog');
      const coverDialogBox = await coverDialog.boundingBox();
      expect(coverDialogBox).not.toBeNull();
      expect(coverDialogBox!.width).toBe(width);
      expect(
        await coverDialog.evaluate(
          (element) => element.scrollWidth <= window.innerWidth
        )
      ).toBe(true);
      await coverDialog.getByRole('button', { name: 'Cancel' }).click();

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

  for (const width of [1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth
      )
    ).toBe(true);
    await expect(page.getByTestId('discard-draft-changes')).toBeVisible();
    await expect(page.getByTestId('sync-public-wxpost')).toBeVisible();
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
  const textarea = page.getByPlaceholder('Ask about or revise the Draft…');
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
  await expect
    .poll(() =>
      history.evaluate((element) =>
        Math.abs(
          element.scrollHeight - element.scrollTop - element.clientHeight
        )
      )
    )
    .toBeLessThanOrEqual(1);
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

  await history.evaluate((element) => {
    element.scrollTop = 0;
    element.dispatchEvent(new Event('scroll'));
  });
  workspace.answerNextDraftChat = true;
  await textarea.fill('How many sections are there?');
  await textarea.press('Enter');
  await expect
    .poll(() => history.evaluate((element) => element.scrollTop))
    .toBe(0);
  await expect(history).toContainText(
    'The saved Draft has four main sections.'
  );
  expect(await history.evaluate((element) => element.scrollTop)).toBe(0);

  await history.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    element.dispatchEvent(new Event('scroll'));
  });
  workspace.answerNextDraftChat = true;
  await textarea.fill('Confirm that section count again.');
  await textarea.press('Enter');
  await expect(history).toContainText(
    'The saved Draft has four main sections.'
  );
  await expect
    .poll(() =>
      history.evaluate(
        (element) =>
          Math.abs(
            element.scrollHeight - element.scrollTop - element.clientHeight
          ) <= 1
      )
    )
    .toBe(true);
});
