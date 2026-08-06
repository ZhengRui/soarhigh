import { expect, test, type Page } from '@playwright/test';

import {
  WXPOST_FIXTURES,
  WXPOST_FIXTURE_CONTEXT_LABELS,
  WXPOST_FIXTURE_IDS,
  type WxPostFixtureId,
} from '../src/components/wxpost/fixtures';
import {
  WXPOST_APPEARANCES,
  WXPOST_LAYOUTS,
  WXPOST_PALETTES,
  WXPOST_PREVIEW_SIZES,
  WXPOST_TYPEFACES,
} from '../src/components/wxpost/types';

async function mockWxPostApi(page: Page) {
  await page.route(/\/posts\/wxposts\/[^/?]+$/, async (route) => {
    if (route.request().resourceType() === 'document') {
      await route.continue();
      return;
    }

    const fixtureId = new URL(route.request().url()).pathname
      .split('/')
      .at(-1) as WxPostFixtureId;
    const fixture = WXPOST_FIXTURES[fixtureId];
    if (!fixture) {
      await route.fulfill({ status: 404, json: { detail: 'Not found' } });
      return;
    }

    await route.fulfill({
      status: 200,
      json: {
        id: `00000000-0000-4000-8000-${fixtureId.padEnd(12, '0').slice(0, 12)}`,
        slug: fixtureId,
        is_public: true,
        article_revision: 3,
        context_label: WXPOST_FIXTURE_CONTEXT_LABELS[fixtureId],
        created_at: '2026-07-18T12:00:00+00:00',
        updated_at: '2026-07-19T12:00:00+00:00',
        render_document: fixture,
      },
    });
  });
}

async function openFixture(
  page: Page,
  fixtureId: WxPostFixtureId = 'meeting-recap'
) {
  await page.goto(`/posts/wxposts/${fixtureId}`);
  await expect(
    page.getByRole('heading', {
      level: 1,
      name: WXPOST_FIXTURES[fixtureId].title,
    })
  ).toBeVisible();
}

function presentationOption(page: Page, group: string, option: string) {
  return page.locator(`[data-testid="wxpost-${group}-${option}"]:visible`);
}

test.beforeEach(async ({ page }) => {
  await mockWxPostApi(page);
});

test('renders the formal public page and every v1 directive', async ({
  page,
}) => {
  await openFixture(page);

  await expect(page.getByText('WxPost', { exact: true })).toBeVisible();
  await expect(page.getByText('Revision 3', { exact: true })).toBeVisible();
  await expect(page.getByText('Meeting 236', { exact: true })).toBeVisible();
  await expect(
    page.getByTestId('wxpost-article').getByText('Meeting 236', { exact: true })
  ).toHaveCount(0);
  await expect(page.getByText('meeting-236', { exact: true })).toHaveCount(0);
  await expect(page.getByText('WxPost Renderer Lab')).toHaveCount(0);
  await expect(page.getByTestId('delete-public-wxpost')).toHaveCount(0);
  await expect(page.getByTestId('publish-wechat-draft')).toHaveCount(0);

  for (const directive of [
    'section',
    'image',
    'info-grid',
    'timeline',
    'gallery',
    'pull-quote',
    'person',
    'video',
    'takeaway',
  ]) {
    await expect(
      page.getByTestId(`directive-${directive}`).first()
    ).toBeVisible();
  }

  const keyPoints = page.locator('.wxpost-key-point');
  await expect(keyPoints).toHaveCount(3);
  await expect(keyPoints.first()).toHaveCSS(
    'text-decoration-line',
    'underline'
  );
  await expect(page.locator('[data-wxpost-kind="markdown"]')).toHaveCount(6);
  await expect(page.getByTestId('markdown-segment')).toHaveCount(3);

  const video = page.getByTestId('wxpost-video');
  await expect(video).toBeVisible();
  await expect(video).toHaveAttribute('controls', '');
  await expect(video).toHaveAttribute('poster', /soarhigh\.oss-cn-shenzhen/);
  await expect(video.locator('source')).toHaveAttribute(
    'src',
    /interactive-examples\.mdn\.mozilla\.net/
  );
});

test('does not repeat the public article label in the Field Notes header', async ({
  page,
}) => {
  const article = structuredClone(WXPOST_FIXTURES['meeting-recap']);
  article.title = 'A Community Garden Begins with Attention';
  article.articleType = 'custom';
  article.customArticleType = 'Community Garden Field Guide';
  article.presentation.layout = 'field-notes';

  await page.route(/\/posts\/wxposts\/custom-field-note$/, async (route) => {
    if (route.request().resourceType() === 'document') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      json: {
        id: '00000000-0000-4000-8000-000000000002',
        slug: 'custom-field-note',
        is_public: true,
        article_revision: 1,
        context_label: 'Community Garden Field Guide',
        created_at: '2026-08-01T12:00:00+00:00',
        updated_at: '2026-08-01T12:00:00+00:00',
        render_document: article,
      },
    });
  });

  await page.goto('/posts/wxposts/custom-field-note');
  await expect(
    page.getByRole('heading', { level: 1, name: article.title })
  ).toBeVisible();

  await expect(
    page
      .getByTestId('wxpost-article')
      .getByText('Community Garden Field Guide', { exact: true })
  ).toHaveCount(1);
  await expect(
    page.getByTestId('wxpost-article').locator('[data-wxpost-hero-mark]')
  ).toHaveCount(0);
});

test('lets a signed-in member delete the public revision and its media', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    window.localStorage.setItem('token', 'member-token');
  });
  await page.route(/\/whoami$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        uid: 'member-123',
        username: 'member',
        full_name: 'Test Member',
      },
    });
  });
  let deletion: { id: string; revision: number } | null = null;
  await page.route(
    /\/posts\/wxposts\/([^/?]+)\/publication$/,
    async (route) => {
      const match = /\/posts\/wxposts\/([^/?]+)\/publication$/.exec(
        new URL(route.request().url()).pathname
      );
      const body = route.request().postDataJSON() as {
        expectedPublicRevision: number;
      };
      deletion = {
        id: match?.[1] ?? '',
        revision: body.expectedPublicRevision,
      };
      await route.fulfill({
        status: 200,
        json: { deleted: true, workspaceId: 'wxpost-meeting-recap' },
      });
    }
  );

  await openFixture(page);
  const header = await page.getByTestId('public-wxpost-header').boundingBox();
  const metadata = await page
    .getByTestId('public-wxpost-metadata')
    .boundingBox();
  const deleteButton = await page
    .getByTestId('delete-public-wxpost')
    .boundingBox();
  const contextLabel = await page
    .getByTestId('public-wxpost-context')
    .boundingBox();
  const title = await page.getByTestId('public-wxpost-title').boundingBox();
  expect(header).not.toBeNull();
  expect(metadata).not.toBeNull();
  expect(deleteButton).not.toBeNull();
  expect(contextLabel).not.toBeNull();
  expect(title).not.toBeNull();
  expect(deleteButton!.x + deleteButton!.width).toBeCloseTo(
    header!.x + header!.width,
    0
  );
  expect(deleteButton!.y).toBeCloseTo(header!.y, 0);
  expect(contextLabel!.x + contextLabel!.width).toBeLessThanOrEqual(
    deleteButton!.x
  );
  expect(title!.x + title!.width).toBeLessThanOrEqual(deleteButton!.x);
  expect(metadata!.y).toBeGreaterThan(deleteButton!.y);
  await page.getByTestId('delete-public-wxpost').click();
  const dialog = page.getByTestId('delete-public-wxpost-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(
    'This removes the public revision and its public media. The private workspace, Saved Draft, and any existing WeChat draft will remain.'
  );
  // The app's Supabase client may reconcile its empty test session after the
  // page has loaded. Restore the synthetic member token immediately before
  // exercising the authenticated request.
  await dialog
    .getByRole('button', { name: 'Delete public WxPost' })
    .evaluate((button) => {
      window.localStorage.setItem('token', 'member-token');
      (button as HTMLButtonElement).click();
    });

  await expect(page).toHaveURL(/\/posts$/);
  expect(deletion).toEqual({
    id: '00000000-0000-4000-8000-meeting-reca',
    revision: 3,
  });
});

test('publishes the selected Public Revision presentation to one WeChat draft', async ({
  page,
}) => {
  const publishable = structuredClone(WXPOST_FIXTURES['meeting-recap']);
  publishable.body = publishable.body.filter(
    (node) => node.kind !== 'directive' || node.name !== 'video'
  );
  publishable.media = publishable.media.filter(
    (media) => media.kind !== 'video'
  );
  await page.route(/\/posts\/wxposts\/meeting-recap$/, async (route) => {
    if (route.request().resourceType() === 'document') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      json: {
        id: '00000000-0000-4000-8000-meeting-reca',
        slug: 'meeting-recap',
        is_public: true,
        article_revision: 3,
        context_label: WXPOST_FIXTURE_CONTEXT_LABELS['meeting-recap'],
        created_at: '2026-07-18T12:00:00+00:00',
        updated_at: '2026-07-19T12:00:00+00:00',
        render_document: publishable,
      },
    });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem('token', 'member-token');
  });
  await page.route(/\/whoami$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: { uid: 'member-123', username: 'member', full_name: 'Test Member' },
    });
  });
  let requestBody: Record<string, unknown> | null = null;
  let publishRequests = 0;
  let statusRequests = 0;
  let remoteDraftExists = false;
  let previewRequestFails = false;
  await page.route(
    /\/posts\/wxposts\/([^/?]+)\/wechat-draft$/,
    async (route) => {
      if (route.request().method() === 'GET') {
        statusRequests += 1;
        await route.fulfill({
          status: 200,
          json: remoteDraftExists
            ? {
                state: 'ready',
                sourcePublicRevision: 3,
                presentation: requestBody!.presentation,
                readbackChanged: true,
                needsUpdate: false,
                message: null,
              }
            : {
                state: 'not-created',
                sourcePublicRevision: null,
                presentation: null,
                readbackChanged: null,
                needsUpdate: false,
                message: null,
              },
        });
        return;
      }
      publishRequests += 1;
      requestBody = route.request().postDataJSON() as Record<string, unknown>;
      remoteDraftExists = true;
      await route.fulfill({
        status: 200,
        json: {
          state: 'ready',
          action: 'created',
          sourcePublicRevision: 3,
          presentation: requestBody.presentation,
          readbackChanged: true,
          needsUpdate: false,
          message: null,
          previewUrl: 'https://mp.weixin.qq.com/s/test-preview',
        },
      });
    }
  );
  await page.route(
    /\/posts\/wxposts\/([^/?]+)\/wechat-draft\/preview$/,
    async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 100));
      if (previewRequestFails) {
        await route.fulfill({
          status: 502,
          json: { detail: 'WeChat preview service unavailable.' },
        });
        return;
      }
      if (!remoteDraftExists) {
        await route.fulfill({
          status: 409,
          json: { detail: 'The linked WeChat draft no longer exists.' },
        });
        return;
      }
      await route.fulfill({
        status: 200,
        json: { previewUrl: 'https://mp.weixin.qq.com/s/test-preview' },
      });
    }
  );

  await openFixture(page);
  const wechatButton = page.getByTestId('publish-wechat-draft');
  const previewButton = page.getByTestId('preview-wechat-draft');
  const deleteButton = page.getByTestId('delete-public-wxpost');
  await expect(wechatButton).toBeVisible();
  await expect(previewButton).toBeVisible();
  await expect(previewButton).toBeEnabled();
  await page.waitForTimeout(100);
  const statusRequestsBeforeOpen = statusRequests;
  const wechatStyle = await wechatButton.evaluate((button) => {
    const style = window.getComputedStyle(button);
    const icon = button.querySelector('svg');
    return {
      backgroundColor: style.backgroundColor,
      color: style.color,
      fill: icon?.getAttribute('fill'),
      stroke: icon?.getAttribute('stroke'),
    };
  });
  const deleteBackground = await deleteButton.evaluate(
    (button) => window.getComputedStyle(button).backgroundColor
  );
  expect(wechatStyle.backgroundColor).toBe(deleteBackground);
  expect(wechatStyle.color).not.toBe(
    await deleteButton.evaluate(
      (button) => window.getComputedStyle(button).color
    )
  );
  expect(wechatStyle.fill).toBe('none');
  expect(wechatStyle.stroke).toBe('currentColor');
  const wechatBox = await wechatButton.boundingBox();
  const deleteBox = await deleteButton.boundingBox();
  expect(wechatBox).not.toBeNull();
  expect(deleteBox).not.toBeNull();
  const initialPreviewBox = await previewButton.boundingBox();
  expect(initialPreviewBox).not.toBeNull();
  expect(initialPreviewBox!.x + initialPreviewBox!.width).toBeLessThan(
    wechatBox!.x
  );
  expect(wechatBox!.x + wechatBox!.width).toBeLessThan(deleteBox!.x);

  await presentationOption(page, 'appearance', 'dark').click();
  await wechatButton.click();
  const dialog = page.getByTestId('publish-wechat-draft-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Revision 3');
  await expect(dialog).toContainText('dark');
  await expect(dialog).toContainText('does not publish or send the article');
  await expect(dialog).not.toContainText(
    'Dark appearance and horizontal Gallery behavior'
  );
  expect(statusRequests).toBe(statusRequestsBeforeOpen);
  expect(publishRequests).toBe(0);
  expect(requestBody).toBeNull();
  await dialog.click({ position: { x: 2, y: 2 } });
  await expect(dialog).toHaveCount(0);
  await wechatButton.click();
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole('button', { name: 'Publish to WeChat Drafts' })
    .evaluate((button) => {
      window.localStorage.setItem('token', 'member-token');
      (button as HTMLButtonElement).click();
    });
  await expect(dialog).toHaveCount(0);
  expect(publishRequests).toBe(1);
  await expect(previewButton).toBeEnabled();
  const publishedWechatBox = await wechatButton.boundingBox();
  const previewBox = await previewButton.boundingBox();
  const publishedDeleteBox = await deleteButton.boundingBox();
  expect(publishedWechatBox).not.toBeNull();
  expect(previewBox).not.toBeNull();
  expect(publishedDeleteBox).not.toBeNull();
  expect(previewBox!.x + previewBox!.width).toBeLessThan(publishedWechatBox!.x);
  expect(publishedWechatBox!.x + publishedWechatBox!.width).toBeLessThan(
    publishedDeleteBox!.x
  );

  expect(requestBody).toEqual({
    expectedPublicRevision: 3,
    presentation: {
      layout: 'brand-default',
      palette: 'paper-neutral',
      appearance: 'dark',
      typeface: 'editorial-serif',
    },
    confirmed: true,
  });

  await wechatButton.click();
  await expect(dialog).toContainText('Publish to WeChat Drafts?');
  expect(statusRequests).toBe(statusRequestsBeforeOpen);
  await expect(dialog).not.toContainText('WeChat adjusted the submitted HTML');
  await expect(dialog).not.toContainText('No HTML changes were detected');
  await expect(
    dialog.getByRole('button', { name: 'Publish to WeChat Drafts' })
  ).toBeVisible();
  await dialog.getByRole('button', { name: 'Cancel' }).click();

  const popupPromise = page.waitForEvent('popup');
  const previewClick = previewButton.click();
  await expect(previewButton.locator('.animate-spin')).toBeVisible();
  await previewClick;
  const popup = await popupPromise;
  await expect(popup).toHaveURL('https://mp.weixin.qq.com/s/test-preview');

  remoteDraftExists = false;
  await previewButton.click();
  await expect(
    page.getByText('The linked WeChat draft no longer exists.')
  ).toBeVisible();
  await expect(previewButton).toBeEnabled();
  expect(statusRequests).toBe(statusRequestsBeforeOpen);

  remoteDraftExists = true;
  previewRequestFails = true;
  await previewButton.click();
  await expect(
    page.getByText('WeChat preview service unavailable.')
  ).toBeVisible();
  await expect(previewButton).toBeEnabled();
  expect(statusRequests).toBe(statusRequestsBeforeOpen);
});

test('retries and explicitly resets an uncertain WeChat creation', async ({
  page,
}) => {
  const publishable = structuredClone(WXPOST_FIXTURES['meeting-recap']);
  publishable.body = publishable.body.filter(
    (node) => node.kind !== 'directive' || node.name !== 'video'
  );
  publishable.media = publishable.media.filter(
    (media) => media.kind !== 'video'
  );
  await page.route(/\/posts\/wxposts\/meeting-recap$/, async (route) => {
    if (route.request().resourceType() === 'document') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      json: {
        id: '00000000-0000-4000-8000-meeting-reca',
        slug: 'meeting-recap',
        is_public: true,
        article_revision: 3,
        context_label: WXPOST_FIXTURE_CONTEXT_LABELS['meeting-recap'],
        created_at: '2026-07-18T12:00:00+00:00',
        updated_at: '2026-07-19T12:00:00+00:00',
        render_document: publishable,
      },
    });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem('token', 'member-token');
    const removeItem = Storage.prototype.removeItem;
    Storage.prototype.removeItem = function (key: string) {
      if (this === window.localStorage && key === 'token') return;
      removeItem.call(this, key);
    };
  });
  await page.route(/\/whoami$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: { uid: 'member-123', username: 'member', full_name: 'Test Member' },
    });
  });

  let recoveryRequests = 0;
  let recoveryBody: Record<string, unknown> | null = null;
  let resetBody: Record<string, unknown> | null = null;
  let statusRequests = 0;
  await page.route(
    /\/posts\/wxposts\/([^/?]+)\/wechat-draft\/reset-uncertain$/,
    async (route) => {
      resetBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        json: {
          state: 'not-created',
          sourcePublicRevision: null,
          presentation: null,
          readbackChanged: null,
          needsUpdate: false,
          message: null,
        },
      });
    }
  );
  await page.route(
    /\/posts\/wxposts\/([^/?]+)\/wechat-draft$/,
    async (route) => {
      if (route.request().method() === 'GET') {
        statusRequests += 1;
        await route.fulfill({
          status: 200,
          json: {
            state: 'uncertain',
            sourcePublicRevision: 3,
            presentation: {
              layout: 'brand-default',
              palette: 'brand-blue',
              appearance: 'dark',
              typeface: 'modern-sans',
            },
            readbackChanged: null,
            needsUpdate: false,
            message: 'The previous creation result is uncertain.',
          },
        });
        return;
      }
      recoveryRequests += 1;
      recoveryBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 409,
        json: {
          detail:
            'The previous WeChat draft creation result is uncertain and could not be uniquely recovered.',
        },
      });
    }
  );

  await openFixture(page);
  await expect(page.getByTestId('publish-wechat-draft')).toBeVisible();
  await expect.poll(() => statusRequests).toBeGreaterThan(0);
  await page.waitForTimeout(50);
  await page.getByTestId('publish-wechat-draft').click();
  const recoveryDialog = page.getByTestId('publish-wechat-draft-dialog');
  await expect(recoveryDialog).toContainText('Recover WeChat Draft?');
  await recoveryDialog.getByRole('button', { name: 'Retry Recovery' }).click();
  await expect(recoveryDialog.getByRole('alert')).toContainText(
    'could not be uniquely recovered'
  );
  expect(recoveryRequests).toBe(1);
  expect(recoveryBody).toEqual({
    expectedPublicRevision: 3,
    presentation: {
      layout: 'brand-default',
      palette: 'brand-blue',
      appearance: 'dark',
      typeface: 'modern-sans',
    },
    confirmed: true,
  });

  await recoveryDialog
    .getByRole('button', { name: 'I checked; no matching draft exists' })
    .click();
  const resetDialog = page.getByTestId('reset-uncertain-wechat-draft-dialog');
  await expect(resetDialog).toContainText(
    'confirming that no matching draft exists'
  );
  await resetDialog.getByRole('button', { name: 'Reset WeChat State' }).click();
  await expect(resetDialog).toHaveCount(0);
  expect(resetBody).toEqual({
    expectedPublicRevision: 3,
    confirmedNoDraft: true,
  });

  await page.getByTestId('publish-wechat-draft').click();
  await expect(page.getByTestId('publish-wechat-draft-dialog')).toContainText(
    'Publish to WeChat Drafts?'
  );
});

test('renders a controlled placeholder for missing media', async ({ page }) => {
  const article = structuredClone(WXPOST_FIXTURES['meeting-recap']);
  article.media[0].sourceUrl = '';
  await page.route(/\/posts\/wxposts\/meeting-recap$/, async (route) => {
    if (route.request().resourceType() === 'document') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      json: {
        id: '00000000-0000-4000-8000-000000000001',
        slug: 'meeting-recap',
        is_public: true,
        article_revision: 3,
        context_label: 'Meeting 236',
        created_at: '2026-07-18T12:00:00+00:00',
        updated_at: '2026-07-19T12:00:00+00:00',
        render_document: article,
      },
    });
  });

  await openFixture(page);

  await expect(page.getByText('Missing image M01')).toBeVisible();
  await expect(page.locator('img[src=""]')).toHaveCount(0);
});

test('starts with stored defaults and changes presentation only locally', async ({
  page,
}) => {
  const mutationRequests: string[] = [];
  page.on('request', (request) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      mutationRequests.push(`${request.method()} ${request.url()}`);
    }
  });

  await openFixture(page);

  const stage = page.getByTestId('wxpost-stage');
  const article = page.getByTestId('wxpost-article');

  await expect(
    presentationOption(page, 'layout', 'brand-default')
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(
    presentationOption(page, 'palette', 'paper-neutral')
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(presentationOption(page, 'appearance', 'light')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(
    presentationOption(page, 'typeface', 'editorial-serif')
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(
    presentationOption(page, 'preview-size', 'mobile-390')
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(stage).toHaveAttribute('data-preview-size', 'mobile-390');

  const mobileWidth = await stage.evaluate(
    (element) => element.getBoundingClientRect().width
  );
  expect(mobileWidth).toBeLessThanOrEqual(390);
  const defaultTypography = await article.evaluate((element) => {
    const style = (selector: string) =>
      getComputedStyle(element.querySelector(selector)!);
    const articleStyle = getComputedStyle(element);
    const metaStyle = style('header > div');
    return {
      background: articleStyle.backgroundColor,
      bodyFontSize: articleStyle.fontSize,
      bodyLineHeight: articleStyle.lineHeight,
      paddingTop: articleStyle.paddingTop,
      titleFontSize: style('h1').fontSize,
      titleLineHeight: style('h1').lineHeight,
      headingFontSize: style('h2').fontSize,
      headingLineHeight: style('h2').lineHeight,
      metaFontSize: metaStyle.fontSize,
      captionFontSize: style('figure p').fontSize,
    };
  });
  expect(defaultTypography).toEqual({
    background: 'rgb(248, 246, 240)',
    bodyFontSize: '16px',
    bodyLineHeight: '29.6px',
    paddingTop: '29.44px',
    titleFontSize: '24px',
    titleLineHeight: '32.4px',
    headingFontSize: '20px',
    headingLineHeight: '27px',
    metaFontSize: '16px',
    captionFontSize: '14px',
  });

  await presentationOption(page, 'layout', 'editorial-feature').click();
  await presentationOption(page, 'palette', 'brand-blue').click();
  await presentationOption(page, 'appearance', 'dark').click();
  await presentationOption(page, 'typeface', 'humanist-mix').click();
  await presentationOption(page, 'preview-size', 'desktop-760').click();

  await expect(article).toHaveAttribute('data-layout', 'editorial-feature');
  await expect(article).toHaveAttribute('data-palette', 'brand-blue');
  await expect(article).toHaveAttribute('data-appearance', 'dark');
  await expect(article).toHaveAttribute('data-typeface', 'humanist-mix');
  await expect(stage).toHaveAttribute('data-preview-size', 'desktop-760');
  await expect(page.getByTestId('current-style')).toContainText(
    'Editorial Feature · SoarHigh Blue · Dark · Humanist Mix · Desktop 760px'
  );

  const desktopWidth = await stage.evaluate(
    (element) => element.getBoundingClientRect().width
  );
  expect(desktopWidth).toBeGreaterThan(700);
  expect(desktopWidth).toBeLessThanOrEqual(760);

  await page.getByRole('button', { name: 'Reset' }).click();
  await expect(article).toHaveAttribute('data-layout', 'brand-default');
  await expect(article).toHaveAttribute('data-palette', 'paper-neutral');
  await expect(article).toHaveAttribute('data-appearance', 'light');
  await expect(article).toHaveAttribute('data-typeface', 'editorial-serif');
  await expect(stage).toHaveAttribute('data-preview-size', 'mobile-390');
  expect(mutationRequests).toEqual([]);
});

test('renders every layout, palette, appearance, and typeface combination', async ({
  page,
}) => {
  test.setTimeout(60_000);
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await openFixture(page);
  await presentationOption(page, 'preview-size', 'desktop-760').click();

  const article = page.getByTestId('wxpost-article');
  const expectedBackgrounds = {
    'brand-blue': {
      light: 'rgb(255, 255, 255)',
      dark: 'rgb(16, 19, 26)',
    },
    'paper-neutral': {
      light: 'rgb(248, 246, 240)',
      dark: 'rgb(27, 26, 23)',
    },
    'fresh-sage': {
      light: 'rgb(248, 250, 245)',
      dark: 'rgb(18, 25, 21)',
    },
    'warm-terracotta': {
      light: 'rgb(255, 250, 242)',
      dark: 'rgb(33, 22, 18)',
    },
    'minimal-mono': {
      light: 'rgb(255, 255, 255)',
      dark: 'rgb(17, 17, 17)',
    },
  } as const;
  const expectedTitleFonts = {
    'modern-sans': 'Avenir Next',
    'editorial-serif': 'Baskerville',
    'humanist-mix': 'Charter',
  } as const;

  for (const layout of WXPOST_LAYOUTS) {
    await presentationOption(page, 'layout', layout).click();
    await expect(article).toHaveAttribute('data-layout', layout);
    const layoutStyles = await article.evaluate((element) => ({
      articleMaxWidth: getComputedStyle(element).maxWidth,
      headerDisplay: getComputedStyle(element.querySelector('header')!).display,
    }));
    expect(layoutStyles.articleMaxWidth).toBe(
      {
        'brand-default': '736px',
        'field-notes': '768px',
        'editorial-feature': '816px',
      }[layout]
    );
    expect(layoutStyles.headerDisplay).toBe(
      layout === 'brand-default' ? 'block' : 'flex'
    );

    for (const palette of WXPOST_PALETTES) {
      await presentationOption(page, 'palette', palette).click();
      await expect(article).toHaveAttribute('data-palette', palette);
      const borderImageSource = await article
        .locator('header')
        .evaluate((header) => getComputedStyle(header).borderImageSource);
      if (palette === 'brand-blue') {
        expect(borderImageSource).toContain('linear-gradient');
      } else {
        expect(borderImageSource).toBe('none');
      }

      for (const appearance of WXPOST_APPEARANCES) {
        await presentationOption(page, 'appearance', appearance).click();
        await expect(article).toHaveAttribute('data-appearance', appearance);
        await expect(article).toHaveCSS(
          'background-color',
          expectedBackgrounds[palette][appearance]
        );

        for (const typeface of WXPOST_TYPEFACES) {
          await presentationOption(page, 'typeface', typeface).click();
          await expect(article).toHaveAttribute('data-typeface', typeface);
          const titleFont = await article
            .locator('h1')
            .evaluate((title) => getComputedStyle(title).fontFamily);
          expect(titleFont).toContain(expectedTitleFonts[typeface]);
        }
      }
    }
  }

  expect(pageErrors).toEqual([]);
});

test('keeps three article shapes readable in every layout and preview size', async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });

  for (const fixtureId of WXPOST_FIXTURE_IDS) {
    await openFixture(page, fixtureId);
    const article = page.getByTestId('wxpost-article');
    const stage = page.getByTestId('wxpost-stage');

    for (const layout of WXPOST_LAYOUTS) {
      await presentationOption(page, 'layout', layout).click();
      await expect(article).toHaveAttribute('data-layout', layout);

      for (const previewSize of WXPOST_PREVIEW_SIZES) {
        await presentationOption(page, 'preview-size', previewSize).click();
        await expect(stage).toHaveAttribute('data-preview-size', previewSize);

        const geometry = await article.evaluate((element) => {
          const articleRect = element.getBoundingClientRect();
          const title = element.querySelector('h1');
          const titleRect = title?.getBoundingClientRect();
          const body = element.querySelector('[data-wxpost-body="true"]');
          const bodyRect = body?.getBoundingClientRect();
          const bodyChildren = body
            ? Array.from(body.children)
                .filter(
                  (child) =>
                    child.getAttribute('data-testid') !== 'directive-pull-quote'
                )
                .map((child) => child.getBoundingClientRect())
            : [];
          const segments = Array.from(
            element.querySelectorAll<HTMLElement>(
              '[data-testid="markdown-segment"]'
            )
          ).map((segment) => {
            return {
              paddingLeft: Number.parseFloat(
                getComputedStyle(segment).paddingLeft
              ),
              borderLeftWidth: Number.parseFloat(
                getComputedStyle(segment).borderLeftWidth
              ),
              borderTopWidth: Number.parseFloat(
                getComputedStyle(segment).borderTopWidth
              ),
            };
          });
          const sectionHeading = element.querySelector<HTMLElement>(
            '[data-wxpost-section-heading="true"]'
          );
          const sectionRoot = element.querySelector<HTMLElement>(
            '[data-testid="directive-section"] > [data-wxpost-kind="markdown"]'
          );
          const sectionHeadingStyle = sectionHeading
            ? getComputedStyle(sectionHeading)
            : null;
          const sectionRootStyle = sectionRoot
            ? getComputedStyle(sectionRoot)
            : null;
          const mediaWidths = Array.from(
            element.querySelectorAll<HTMLElement>(
              '[data-wxpost-directive="image"], [data-wxpost-directive="gallery"], [data-wxpost-directive="video"]'
            )
          ).map((media) => media.getBoundingClientRect().width);

          return {
            horizontalOverflow: element.scrollWidth - element.clientWidth,
            paddingInline: Number.parseFloat(
              getComputedStyle(element).paddingLeft
            ),
            titleInside:
              Boolean(titleRect) &&
              titleRect!.left >= articleRect.left - 1 &&
              titleRect!.right <= articleRect.right + 1,
            narrowestBodyChildRatio:
              bodyRect && bodyChildren.length
                ? Math.min(
                    ...bodyChildren.map((rect) => rect.width / bodyRect.width)
                  )
                : 1,
            segments,
            sectionHeading: sectionHeadingStyle
              ? {
                  borderTopWidth: Number.parseFloat(
                    sectionHeadingStyle.borderTopWidth
                  ),
                  borderBottomWidth: Number.parseFloat(
                    sectionHeadingStyle.borderBottomWidth
                  ),
                  borderLeftWidth: Number.parseFloat(
                    sectionHeadingStyle.borderLeftWidth
                  ),
                  backgroundColor: sectionHeadingStyle.backgroundColor,
                }
              : null,
            sectionRoot: sectionRootStyle
              ? {
                  borderTopWidth: Number.parseFloat(
                    sectionRootStyle.borderTopWidth
                  ),
                }
              : null,
            bodyWidth: bodyRect?.width ?? 0,
            mediaWidths,
          };
        });

        expect(geometry.horizontalOverflow).toBeLessThanOrEqual(1);
        expect(geometry.titleInside).toBe(true);
        expect(geometry.narrowestBodyChildRatio).toBeGreaterThan(0.94);
        expect(
          geometry.mediaWidths.every(
            (width) => Math.abs(width - geometry.bodyWidth) <= 1
          )
        ).toBe(true);

        const stageWidth = await stage.evaluate(
          (element) => element.getBoundingClientRect().width
        );
        if (previewSize === 'mobile-390') {
          expect(stageWidth).toBeLessThanOrEqual(390);
          expect(geometry.paddingInline).toBeCloseTo(12, 1);
        } else {
          expect(stageWidth).toBeGreaterThan(700);
          expect(stageWidth).toBeLessThanOrEqual(760);
          expect(geometry.paddingInline).toBeCloseTo(29.44, 1);
        }

        expect(
          geometry.segments.every(
            (segment) =>
              segment.paddingLeft <= 1 &&
              segment.borderLeftWidth <= 0.1 &&
              segment.borderTopWidth <= 0.1
          )
        ).toBe(true);
        await expect(
          article.getByText('Field notes', { exact: true })
        ).toHaveCount(0);

        if (layout === 'field-notes') {
          await expect(
            article.locator('[data-wxpost-hero-mark="true"]')
          ).toHaveCount(0);
          if (geometry.sectionRoot) {
            expect(geometry.sectionRoot.borderTopWidth).toBeGreaterThanOrEqual(
              1
            );
          }
        } else {
          await expect(
            article.locator('[data-wxpost-hero-mark="true"]')
          ).toHaveCount(0);
        }

        if (layout === 'editorial-feature' && geometry.sectionHeading) {
          expect(geometry.sectionHeading.borderTopWidth).toBeGreaterThanOrEqual(
            3
          );
        }
        if (layout === 'brand-default' && geometry.sectionHeading) {
          expect(
            geometry.sectionHeading.borderLeftWidth
          ).toBeGreaterThanOrEqual(4);
          expect(geometry.sectionHeading.backgroundColor).not.toBe(
            'rgba(0, 0, 0, 0)'
          );
        }
      }
    }
  }
});

test('uses full-width images in a native horizontally scrolling gallery', async ({
  page,
}) => {
  await openFixture(page);

  const track = page.getByTestId('gallery-track');
  const initial = await track.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    scrollLeft: element.scrollLeft,
    overflowX: getComputedStyle(element).overflowX,
    scrollSnapType: getComputedStyle(element).scrollSnapType,
    figureWidths: Array.from(element.querySelectorAll('figure')).map(
      (figure) => figure.getBoundingClientRect().width
    ),
    imageWidths: Array.from(element.querySelectorAll('img')).map(
      (image) => image.getBoundingClientRect().width
    ),
  }));

  expect(initial.scrollWidth).toBeGreaterThan(initial.clientWidth);
  expect(initial.scrollLeft).toBe(0);
  expect(initial.overflowX).toBe('auto');
  expect(initial.scrollSnapType).toContain('x');
  expect(initial.figureWidths.length).toBeGreaterThan(1);
  expect(
    initial.figureWidths.every(
      (width) => Math.abs(width - initial.clientWidth) <= 1
    )
  ).toBe(true);
  expect(
    initial.imageWidths.every(
      (width) => Math.abs(width - initial.clientWidth) <= 2
    )
  ).toBe(true);
  await expect(
    page.getByRole('button', { name: /gallery image/i })
  ).toHaveCount(0);

  await presentationOption(page, 'preview-size', 'desktop-760').click();
  const desktop = await track.evaluate((element) => ({
    clientWidth: element.clientWidth,
    figureWidths: Array.from(element.querySelectorAll('figure')).map(
      (figure) => figure.getBoundingClientRect().width
    ),
    imageWidths: Array.from(element.querySelectorAll('img')).map(
      (image) => image.getBoundingClientRect().width
    ),
  }));
  expect(
    desktop.figureWidths.every(
      (width) => Math.abs(width - desktop.clientWidth) <= 1
    )
  ).toBe(true);
  expect(
    desktop.imageWidths.every(
      (width) => Math.abs(width - desktop.clientWidth) <= 2
    )
  ).toBe(true);

  await track.evaluate((element) => {
    element.scrollTo({ left: element.clientWidth });
  });
  await expect
    .poll(() => track.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
});

test('customizes the mobile preview in a bottom drawer', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openFixture(page);

  const article = page.getByTestId('wxpost-article');
  const trigger = page.getByRole('button', {
    name: /Customize article appearance/,
  });

  await expect(trigger).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Article presentation' })
  ).toBeHidden();

  await page.evaluate(() => window.scrollTo(0, 700));
  const scrollPosition = await page.evaluate(() => window.scrollY);

  await trigger.click();
  const dialog = page.getByRole('dialog', {
    name: 'Customize appearance',
  });
  await expect(dialog).toBeVisible();
  await expect(page.locator('body')).toHaveCSS('overflow', 'hidden');

  const closeButton = page.getByRole('button', {
    name: 'Close appearance settings',
  });
  const doneButton = page.getByRole('button', { name: 'Done' });
  await expect(closeButton).toBeFocused();
  await doneButton.focus();
  await page.keyboard.press('Tab');
  await expect(closeButton).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(doneButton).toBeFocused();

  await presentationOption(page, 'palette', 'brand-blue').click();
  await expect(article).toHaveAttribute('data-palette', 'brand-blue');
  await presentationOption(page, 'typeface', 'humanist-mix').click();
  await expect(article).toHaveAttribute('data-typeface', 'humanist-mix');

  await doneButton.click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId('mobile-style-summary')).toContainText(
    'SoarHigh Blue'
  );
  await expect(page.locator('body')).not.toHaveCSS('overflow', 'hidden');
  expect(await page.evaluate(() => window.scrollY)).toBe(scrollPosition);
});

test('closes the mobile drawer when the viewport crosses the desktop breakpoint', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openFixture(page);

  await page
    .getByRole('button', { name: /Customize article appearance/ })
    .click();
  await expect(
    page.getByRole('dialog', { name: 'Customize appearance' })
  ).toBeVisible();
  await expect(page.locator('body')).toHaveCSS('overflow', 'hidden');

  await page.setViewportSize({ width: 760, height: 844 });

  await expect(
    page.getByRole('dialog', { name: 'Customize appearance' })
  ).toHaveCount(0);
  await expect(page.locator('body')).not.toHaveCSS('overflow', 'hidden');
  await expect(
    page.getByRole('region', { name: 'Article presentation' })
  ).toBeVisible();
});

test('collapses the formal page cleanly in a real narrow viewport', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 390, height: 844 });

  for (const fixtureId of WXPOST_FIXTURE_IDS) {
    await openFixture(page, fixtureId);
    const article = page.getByTestId('wxpost-article');
    await page
      .getByRole('button', { name: /Customize article appearance/ })
      .click();
    await expect(
      page.getByRole('dialog', { name: 'Customize appearance' })
    ).toBeVisible();

    for (const layout of WXPOST_LAYOUTS) {
      await presentationOption(page, 'layout', layout).click();
      await expect(article).toHaveAttribute('data-layout', layout);
      await expect(article).toBeVisible();

      const box = await article.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(390);

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth
      );
      expect(overflow).toBeLessThanOrEqual(1);
    }

    await page.getByRole('button', { name: 'Done' }).click();
  }
});
