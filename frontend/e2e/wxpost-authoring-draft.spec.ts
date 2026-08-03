import { expect, test } from '@playwright/test';

import {
  completeDraftDocument,
  createAndGenerateDraft,
} from './support/wxpostDraft';
import { draftDocument, openAuthoringPage } from './support/wxpostAuthoring';

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

test('keeps loaded Draft media stable when the assistant saves a revision', async ({
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
  await page.getByTestId('generate-draft').click();

  const firstImage = page.getByTestId('wxpost-article').locator('img').first();
  await expect(firstImage).toBeVisible();
  const sourceBeforeRevision = await firstImage.getAttribute('src');
  expect(sourceBeforeRevision).toMatch(/^blob:/);

  const chatInput = page.getByPlaceholder('Ask about or revise the Draft…');
  await chatInput.fill('Make the title more concise.');
  await chatInput.press('Enter');

  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(firstImage).toHaveAttribute('src', sourceBeforeRevision!);
  await expect(
    page.getByText('Preparing Draft preview and media…')
  ).toHaveCount(0);
  const completedSteps = page.getByText('4 steps completed', { exact: true });
  await completedSteps.click();
  const history = page.getByTestId('draft-chat-history');
  await expect(history).toContainText('Updating the Draft title');
  await expect(
    history.getByText('replaceMetadata', { exact: true })
  ).toBeVisible();
  await expect(
    history.getByText('wxpost_edit_draft', { exact: true })
  ).toBeVisible();
});

test('shows only milestones delivered by the live Draft chat stream', async ({
  page,
}) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);
    let draftChatRequests = 0;
    window.fetch = async (input, init) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (!url.endsWith('/draft/chat')) return originalFetch(input, init);
      draftChatRequests += 1;
      const encoder = new TextEncoder();
      const event = (name: string, data: Record<string, unknown>) =>
        encoder.encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`);
      const events =
        draftChatRequests === 1
          ? ([
              ['progress', { stage: 'request_started' }],
              [
                'progress',
                {
                  stage: 'activity_started',
                  activityId: 'search-1',
                  label: 'Searching the web for current club news',
                },
              ],
              [
                'progress',
                {
                  stage: 'activity_completed',
                  activityId: 'search-1',
                  label: 'Searching the web for current club news',
                },
              ],
              [
                'progress',
                {
                  stage: 'activity_started',
                  activityId: 'read-1',
                  label: 'Reading https://example.com/article',
                },
              ],
              [
                'progress',
                {
                  stage: 'activity_completed',
                  activityId: 'read-1',
                  label: 'Reading https://example.com/article',
                },
              ],
              [
                'complete',
                {
                  workspaceId: 'wxpost-stream-test',
                  sessionId: 'session-stream-test',
                  reply: 'I found the current club news.',
                  context: {},
                  draftChanged: false,
                },
              ],
            ] as const)
          : draftChatRequests === 2
            ? ([
                ['progress', { stage: 'request_started' }],
                [
                  'complete',
                  {
                    workspaceId: 'wxpost-stream-test',
                    sessionId: 'session-stream-test',
                    reply: 'I am the SoarHigh Club AI Assistant.',
                    context: {},
                    draftChanged: false,
                  },
                ],
              ] as const)
            : ([
                ['progress', { stage: 'request_started' }],
                [
                  'progress',
                  {
                    stage: 'activity_started',
                    activityId: 'context-1',
                    label: 'Reading the saved Draft and media',
                  },
                ],
                [
                  'progress',
                  {
                    stage: 'activity_failed',
                    activityId: 'context-1',
                    label: 'Reading the saved Draft and media',
                  },
                ],
                [
                  'error',
                  {
                    code: 'hermes_turn_failed',
                    message: 'Hermes could not revise the draft',
                  },
                ],
              ] as const);
      return new Response(
        new ReadableStream({
          start(controller) {
            events.forEach(([name, data], index) => {
              window.setTimeout(() => {
                controller.enqueue(event(name, data));
                if (index === events.length - 1) controller.close();
              }, index * 250);
            });
          },
        }),
        {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }
      );
    };
  });
  await createAndGenerateDraft(page);

  const chatInput = page.getByPlaceholder('Ask about or revise the Draft…');
  await chatInput.fill('Search for current club news.');
  await chatInput.press('Enter');

  const progress = page.getByTestId('draft-assistant-progress');
  await expect(progress).toContainText(
    'Searching the web for current club news'
  );
  await expect(progress).toContainText('Reading https://example.com/article');
  await expect(progress).toHaveCount(0);
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'I found the current club news.'
  );
  const completedSteps = page.getByText('2 steps completed', { exact: true });
  await expect(completedSteps).toBeVisible();
  await expect(
    page
      .getByTestId('draft-chat-history')
      .locator('details + p')
      .filter({ hasText: 'I found the current club news.' })
  ).toBeVisible();
  await completedSteps.click();
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'Searching the web for current club news'
  );

  await chatInput.fill('Who are you?');
  await chatInput.press('Enter');
  await expect(progress).toContainText('Thinking…');
  await expect(progress).toHaveCount(0);
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'I am the SoarHigh Club AI Assistant.'
  );
  await expect(page.getByText(/steps completed/)).toHaveCount(1);

  await chatInput.fill('Make the opening warmer.');
  await chatInput.press('Enter');
  await expect(progress).toContainText('Reading the saved Draft and media');
  await expect(progress.getByLabel('Failed')).toBeVisible();
  await expect(progress).toHaveCount(0);
  await expect(
    page.getByTestId('draft-workbench').getByRole('alert')
  ).toContainText('Hermes could not revise the draft');
  await expect(chatInput).toHaveValue('Make the opening warmer.');
  await expect(
    page
      .getByTestId('draft-chat-history')
      .getByText('Make the opening warmer.', { exact: true })
  ).toHaveCount(0);
});

test('starts a confirmed new Draft Assistant conversation without changing the Draft', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);
  const context = Array.from(workspace.contexts.values())[0];
  const chatInput = page.getByPlaceholder('Ask about or revise the Draft…');
  workspace.answerNextDraftChat = true;
  await chatInput.fill('How many sections are there?');
  await chatInput.press('Enter');
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'The saved Draft has four main sections.'
  );
  const workspaceId = Array.from(workspace.contexts.keys())[0];
  const oldSessionId = workspace.draftSessionIds.get(workspaceId);
  const draftVersion = context.draft?.draftVersion;
  const manifestVersion = context.manifest.manifestVersion;

  await chatInput.fill('/new');
  await chatInput.press('Enter');
  const dialog = page.getByTestId('draft-session-reset-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(
    'Your workspace, Materials, and saved Draft will not change.'
  );
  expect(
    workspace.requests.filter((item) => item === 'POST /draft/chat')
  ).toHaveLength(1);

  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(chatInput).toHaveValue('/new');
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'The saved Draft has four main sections.'
  );

  await chatInput.press('Enter');
  const confirmation = page.getByTestId('draft-session-reset-dialog');
  const geometry = await confirmation.evaluate((overlay) => {
    const dialogElement = overlay.firstElementChild;
    if (!(dialogElement instanceof HTMLElement)) return null;
    const box = dialogElement.getBoundingClientRect();
    return {
      dialogCenterX: box.left + box.width / 2,
      dialogCenterY: box.top + box.height / 2,
      viewportCenterX: window.innerWidth / 2,
      viewportCenterY: window.innerHeight / 2,
    };
  });
  expect(geometry).not.toBeNull();
  expect(
    Math.abs(geometry!.dialogCenterX - geometry!.viewportCenterX)
  ).toBeLessThan(2);
  expect(
    Math.abs(geometry!.dialogCenterY - geometry!.viewportCenterY)
  ).toBeLessThan(2);
  await confirmation
    .getByRole('button', { name: 'Start new conversation' })
    .click();

  await expect(confirmation).toHaveCount(0);
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'Ask about the article or request a Draft edit.'
  );
  await expect(chatInput).toHaveValue('');
  expect(workspace.requests).toContain('DELETE /draft/session');
  expect(context.draft?.draftVersion).toBe(draftVersion);
  expect(context.manifest.manifestVersion).toBe(manifestVersion);
  expect(workspace.draftSessionIds.get(workspaceId)).toBeNull();

  await page.reload();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'Ask about the article or request a Draft edit.'
  );
  await expect(page.getByTestId('draft-chat-history')).not.toContainText(
    'The saved Draft has four main sections.'
  );

  const refreshedInput = page.getByPlaceholder(
    'Ask about or revise the Draft…'
  );
  workspace.answerNextDraftChat = true;
  await refreshedInput.fill('What is in the new conversation?');
  await refreshedInput.press('Enter');
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'The saved Draft has four main sections.'
  );
  const newSessionId = workspace.draftSessionIds.get(workspaceId);
  expect(newSessionId).not.toBeNull();
  expect(newSessionId).not.toBe(oldSessionId);

  await page.reload();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'What is in the new conversation?'
  );
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'The saved Draft has four main sections.'
  );
});

test('keeps the new-conversation confirmation usable on a narrow mobile viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await createAndGenerateDraft(page);
  await page.getByTestId('open-mobile-hermes').click();
  const chatInput = page
    .getByTestId('mobile-draft-chat-composer')
    .getByPlaceholder('Ask about or revise the Draft…');
  await chatInput.fill('/new');
  await chatInput.press('Enter');

  const overlay = page.getByTestId('draft-session-reset-dialog');
  await expect(overlay).toBeInViewport();
  await expect(overlay.getByRole('button', { name: 'Cancel' })).toBeVisible();
  await expect(
    overlay.getByRole('button', { name: 'Start new conversation' })
  ).toBeVisible();
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
  await expect(page.getByTestId('discard-draft-changes')).toBeEnabled();
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
  await expect(page.getByTestId('save-draft')).toBeDisabled();
  await expect(
    page.getByRole('heading', { name: 'Draft Assistant' })
  ).toBeHidden();
  await expect(page.getByTestId('draft-presentation-controls')).toBeVisible();
  expect(context.draft!.document.title).toBe(savedTitle);

  await page.getByTestId('draft-mode-edit').click();
  await expect(page.getByTestId('save-draft')).toBeEnabled();
  await page
    .getByTestId('wxpost-article')
    .getByRole('heading', { level: 1 })
    .click();
  await expect(
    page.getByRole('textbox', { name: 'Edit draft title' })
  ).toHaveText('A local title that is not saved yet');
  workspace.draftSaveDelayMs = 500;
  await page.getByTestId('save-draft').click();
  await expect(
    page.getByTestId('save-draft').locator('svg.animate-spin')
  ).toBeVisible();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toBeVisible();
  await expect(page.getByText('Draft · v1')).toBeVisible();
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
  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId('generate-draft').click();
  await expect
    .poll(() =>
      page
        .getByRole('status')
        .filter({ hasText: 'Hermes is temporarily unavailable' })
        .count()
    )
    .toBeGreaterThan(0);
  await page.getByRole('button', { name: /^3 Draft$/ }).click();
  await expect(page.getByText('Draft · v1')).toBeVisible();
  expect(context.draft!.draftVersion).toBe(1);
  expect(context.draft!.document.title).toBe(generatedTitle);

  const chatInput = page.getByPlaceholder('Ask about or revise the Draft…');
  workspace.answerNextDraftChat = true;
  await chatInput.fill('How many sections does this article have?');
  await chatInput.press('Enter');
  await expect(page.getByText('Draft · v1')).toBeVisible();
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'The saved Draft has four main sections.'
  );
  expect(context.draft!.draftVersion).toBe(1);

  await chatInput.fill('Make the opening warmer.');
  await chatInput.press('Shift+Enter');
  await chatInput.pressSequentially('Keep it concise.');
  await expect(chatInput).toHaveValue(
    'Make the opening warmer.\nKeep it concise.'
  );
  workspace.failNextDraftChat = true;
  await chatInput.press('Enter');
  await expect(
    page.getByTestId('draft-workbench').getByRole('alert')
  ).toBeVisible();
  await expect(page.getByText('Online', { exact: true })).toBeVisible();
  await expect(page.getByTestId('draft-workbench')).toContainText(
    'Hermes could not revise the draft'
  );
  expect(context.draft!.draftVersion).toBe(1);
  expect(context.draft!.document.title).toBe(generatedTitle);
  await expect(chatInput).toHaveValue(
    'Make the opening warmer.\nKeep it concise.'
  );
  await expect(
    page
      .getByTestId('draft-chat-history')
      .getByText('Make the opening warmer.', { exact: true })
  ).toHaveCount(0);

  workspace.draftChatDelayMs = 500;
  await chatInput.press('Enter');
  await expect(
    page.getByTestId('draft-assistant-progress').getByText('Thinking…')
  ).toBeVisible();
  await expect(page.getByTestId('draft-workbench')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    generatedTitle
  );
  await expect(
    page.getByText('Preparing Draft preview and media…')
  ).toHaveCount(0);
  await expect(page.getByText('Draft · v2')).toBeVisible();
  workspace.draftChatDelayMs = 0;
  await expect(page.getByText('Online', { exact: true })).toBeVisible();
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'Make the opening warmer.'
  );
  await expect(page.getByTestId('draft-chat-history')).toContainText(
    'Keep it concise.'
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

test('regenerates only from Materials and discards local Draft changes separately', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);

  workspace.nextGeneratedDocument = draftDocument(
    'Regenerated without a reload',
    '## Updated section\n\nThis version should appear immediately.'
  );
  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId('generate-draft').click();
  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Regenerated without a reload'
  );
  const validationCount = workspace.draftValidationRequests;

  await page
    .getByTestId('wxpost-article')
    .getByRole('heading', { level: 1 })
    .click();
  await page
    .getByRole('textbox', { name: 'Edit draft title' })
    .fill('Unsaved local title');
  await page.getByTestId('discard-draft-changes').click();
  const discardDialog = page.getByTestId('discard-draft-dialog');
  await expect(discardDialog).toContainText('Discard unsaved changes?');
  await discardDialog.getByRole('button', { name: 'Keep editing' }).click();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Unsaved local title'
  );

  await page.getByTestId('discard-draft-changes').click();
  await discardDialog.getByRole('button', { name: 'Discard changes' }).click();
  await expect(discardDialog).toHaveCount(0);
  await expect(page.getByText('Draft · v2')).toBeVisible();
  await expect(page.getByTestId('wxpost-article')).toContainText(
    'Regenerated without a reload'
  );
  await expect(page.getByTestId('draft-workbench')).toContainText('Saved');
  await expect(page.getByTestId('discard-draft-changes')).toBeDisabled();
  expect(workspace.draftValidationRequests).toBe(validationCount);
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
  await expect(page.getByTestId('save-draft')).toBeDisabled();
  expect(context.draft!.document.title).toBe('Generated draft v1');
  expect(context.draft!.document.presentation).toEqual({
    layout: 'brand-default',
    palette: 'paper-neutral',
    appearance: 'light',
    typeface: 'editorial-serif',
  });

  await page.getByTestId('draft-mode-edit').click();
  await expect(page.getByTestId('save-draft')).toBeEnabled();
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

test('never exposes an older Draft as a newer version after validation fails', async ({
  page,
}) => {
  const workspace = await createAndGenerateDraft(page);
  const context = Array.from(workspace.contexts.values())[0];
  const versionOneTitle = context.draft!.document.title;

  workspace.failDraftValidation = true;
  await page.getByRole('button', { name: /Materials/ }).click();
  await page.getByTestId('generate-draft').click();

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
