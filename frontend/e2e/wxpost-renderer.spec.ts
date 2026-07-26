import { expect, test } from '@playwright/test';

import {
  WXPOST_FIXTURES,
  WXPOST_FIXTURE_IDS,
} from '../src/components/wxpost/fixtures';
import {
  WXPOST_APPEARANCES,
  WXPOST_LAYOUTS,
  WXPOST_PALETTES,
  WXPOST_PREVIEW_SIZES,
  WXPOST_TYPEFACES,
} from '../src/components/wxpost/types';

test('renders every v1 directive and key-point in the complete article', async ({
  page,
}) => {
  await page.goto('/posts/wxposts/renderer-preview');

  await expect(
    page.getByRole('heading', {
      level: 1,
      name: 'The Courage to Try the Next Sentence',
    })
  ).toBeVisible();
  await expect(page.getByText('Meeting 236', { exact: true })).toBeVisible();
  await expect(page.getByText('meeting-236', { exact: true })).toHaveCount(0);

  for (const directive of [
    'info-grid',
    'timeline',
    'gallery',
    'pull-quote',
    'person',
    'video',
    'takeaway',
  ]) {
    await expect(page.getByTestId(`directive-${directive}`)).toBeVisible();
  }

  const keyPoints = page.locator('.wxpost-key-point');
  await expect(keyPoints).toHaveCount(3);
  await expect(keyPoints.first()).toHaveCSS(
    'text-decoration-line',
    'underline'
  );
  await expect(page.getByTestId('markdown-segment')).toHaveCount(6);

  const video = page.getByTestId('wxpost-video');
  await expect(video).toBeVisible();
  await expect(video).toHaveAttribute('controls', '');
  await expect(video).toHaveAttribute('poster', /soarhigh\.oss-cn-shenzhen/);
  await expect(video.locator('source')).toHaveAttribute(
    'src',
    /interactive-examples\.mdn\.mozilla\.net/
  );
  await expect(
    page.getByText(
      'A short video placeholder representing Maya returning to the stage.',
      { exact: true }
    )
  ).toBeVisible();
});

test('starts with the agreed defaults and changes presentation locally', async ({
  page,
}) => {
  const mutationRequests: string[] = [];
  page.on('request', (request) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      mutationRequests.push(`${request.method()} ${request.url()}`);
    }
  });

  await page.goto('/posts/wxposts/renderer-preview');

  const stage = page.getByTestId('wxpost-stage');
  const article = page.getByTestId('wxpost-article');

  await expect(page.locator('#wxpost-layout')).toHaveValue('brand-default');
  await expect(page.locator('#wxpost-palette')).toHaveValue('paper-neutral');
  await expect(page.locator('#wxpost-appearance')).toHaveValue('light');
  await expect(page.locator('#wxpost-typeface')).toHaveValue('editorial-serif');
  await expect(page.locator('#wxpost-preview-size')).toHaveValue('mobile-390');
  await expect(stage).toHaveAttribute('data-preview-size', 'mobile-390');
  await expect(page.locator('#wxpost-layout')).toBeEnabled();

  const mobileWidth = await stage.evaluate(
    (element) => element.getBoundingClientRect().width
  );
  expect(mobileWidth).toBeLessThanOrEqual(390);

  await page.locator('#wxpost-layout').selectOption('editorial-feature');
  await page.locator('#wxpost-palette').selectOption('brand-blue');
  await page.locator('#wxpost-appearance').selectOption('dark');
  await page.locator('#wxpost-typeface').selectOption('humanist-mix');
  await page.locator('#wxpost-preview-size').selectOption('desktop-760');

  await expect(article).toHaveAttribute('data-layout', 'editorial-feature');
  await expect(article).toHaveAttribute('data-palette', 'brand-blue');
  await expect(article).toHaveAttribute('data-appearance', 'dark');
  await expect(article).toHaveAttribute('data-typeface', 'humanist-mix');
  await expect(stage).toHaveAttribute('data-preview-size', 'desktop-760');
  await expect(page.getByTestId('current-style')).toContainText(
    'Editorial Feature · Brand Blue · Dark · Humanist Mix · Desktop 760px'
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

  await page.goto('/posts/wxposts/renderer-preview');
  await expect(page.locator('#wxpost-layout')).toBeEnabled();
  await page.locator('#wxpost-preview-size').selectOption('desktop-760');

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
    'warm-terracotta': {
      light: 'rgb(255, 250, 242)',
      dark: 'rgb(33, 22, 18)',
    },
  } as const;
  const expectedTitleFonts = {
    'modern-sans': 'Avenir Next',
    'editorial-serif': 'Baskerville',
    'humanist-mix': 'Charter',
  } as const;

  for (const layout of WXPOST_LAYOUTS) {
    await page.locator('#wxpost-layout').selectOption(layout);
    await expect(article).toHaveAttribute('data-layout', layout);
    const heroColumnCount = await article
      .locator('header')
      .evaluate(
        (header) =>
          getComputedStyle(header).gridTemplateColumns.trim().split(/\s+/)
            .length
      );
    expect(heroColumnCount).toBe(layout === 'brand-default' ? 1 : 2);

    for (const palette of WXPOST_PALETTES) {
      await page.locator('#wxpost-palette').selectOption(palette);
      await expect(article).toHaveAttribute('data-palette', palette);

      for (const appearance of WXPOST_APPEARANCES) {
        await page.locator('#wxpost-appearance').selectOption(appearance);
        await expect(article).toHaveAttribute('data-appearance', appearance);
        await expect(article).toHaveCSS(
          'background-color',
          expectedBackgrounds[palette][appearance]
        );

        for (const typeface of WXPOST_TYPEFACES) {
          await page.locator('#wxpost-typeface').selectOption(typeface);
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
  await page.goto('/posts/wxposts/renderer-preview');
  await expect(page.locator('#wxpost-layout')).toBeEnabled();

  const article = page.getByTestId('wxpost-article');
  const stage = page.getByTestId('wxpost-stage');

  for (const fixtureId of WXPOST_FIXTURE_IDS) {
    await page.getByTestId(`fixture-option-${fixtureId}`).click();
    await expect(
      page.getByRole('heading', {
        level: 1,
        name: WXPOST_FIXTURES[fixtureId].title,
      })
    ).toBeVisible();

    for (const layout of WXPOST_LAYOUTS) {
      await page.locator('#wxpost-layout').selectOption(layout);
      await expect(article).toHaveAttribute('data-layout', layout);

      for (const previewSize of WXPOST_PREVIEW_SIZES) {
        await page.locator('#wxpost-preview-size').selectOption(previewSize);
        await expect(stage).toHaveAttribute('data-preview-size', previewSize);

        const geometry = await article.evaluate((element) => {
          const articleRect = element.getBoundingClientRect();
          const title = element.querySelector('h1');
          const titleRect = title?.getBoundingClientRect();
          const body = element.querySelector('[data-testid="wxpost-body"]');
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
            const markdown = segment.firstElementChild;
            const sectionCopy = segment.querySelector<HTMLElement>(
              '[data-wxpost-section-copy]'
            );
            const paragraphs = sectionCopy
              ? Array.from(sectionCopy.querySelectorAll('p')).map((paragraph) =>
                  paragraph.getBoundingClientRect()
                )
              : [];
            const paragraphGaps = paragraphs
              .slice(1)
              .map((paragraph, index) => {
                const previousParagraph = paragraphs[index];
                return paragraph.top - previousParagraph.bottom;
              });

            return {
              leadingHeading: segment.dataset.leadingHeading === 'true',
              paddingLeft: Number.parseFloat(
                getComputedStyle(segment).paddingLeft
              ),
              borderTopWidth: Number.parseFloat(
                getComputedStyle(segment).borderTopWidth
              ),
              markdownDisplay: markdown
                ? getComputedStyle(markdown).display
                : '',
              maxParagraphGap:
                paragraphGaps.length > 0 ? Math.max(...paragraphGaps) : 0,
            };
          });

          return {
            horizontalOverflow: element.scrollWidth - element.clientWidth,
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
          };
        });

        expect(geometry.horizontalOverflow).toBeLessThanOrEqual(1);
        expect(geometry.titleInside).toBe(true);
        expect(geometry.narrowestBodyChildRatio).toBeGreaterThan(0.95);

        const stageWidth = await stage.evaluate(
          (element) => element.getBoundingClientRect().width
        );
        if (previewSize === 'mobile-390') {
          expect(stageWidth).toBeLessThanOrEqual(390);
        } else {
          expect(stageWidth).toBeGreaterThan(700);
          expect(stageWidth).toBeLessThanOrEqual(760);
        }

        if (layout === 'field-notes') {
          expect(
            geometry.segments.every((segment) => segment.paddingLeft <= 1)
          ).toBe(true);
          expect(
            geometry.segments.every((segment) => segment.borderTopWidth <= 0.1)
          ).toBe(true);

          const marker = page.getByTestId('field-notes-mark');
          if (previewSize === 'desktop-760') {
            await expect(marker).toBeVisible();
            await expect(marker).toContainText('Field');
            await expect(marker).toContainText('Notes');
          } else {
            await expect(marker).toBeHidden();
          }
        }

        if (layout === 'editorial-feature' && previewSize === 'desktop-760') {
          expect(
            geometry.segments
              .filter((segment) => segment.leadingHeading)
              .every(
                (segment) =>
                  segment.markdownDisplay === 'grid' &&
                  segment.maxParagraphGap <= 48
              )
          ).toBe(true);
          expect(
            geometry.segments
              .filter((segment) => !segment.leadingHeading)
              .every((segment) => segment.markdownDisplay !== 'grid')
          ).toBe(true);
        }
      }
    }
  }
});

test('uses a horizontally scrollable gallery in the mobile preview', async ({
  page,
}) => {
  await page.goto('/posts/wxposts/renderer-preview');

  const track = page.getByTestId('gallery-track');
  const initial = await track.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    scrollLeft: element.scrollLeft,
  }));

  expect(initial.scrollWidth).toBeGreaterThan(initial.clientWidth);
  expect(initial.scrollLeft).toBe(0);

  await page.getByRole('button', { name: 'Next gallery image' }).click();
  await expect
    .poll(() => track.evaluate((element) => element.scrollLeft))
    .toBeGreaterThan(0);
});

test('collapses the renderer cleanly in a real narrow viewport', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/posts/wxposts/renderer-preview');

  const article = page.getByTestId('wxpost-article');
  await expect(page.locator('#wxpost-layout')).toBeEnabled();

  for (const fixtureId of WXPOST_FIXTURE_IDS) {
    await page.getByTestId(`fixture-option-${fixtureId}`).click();

    for (const layout of WXPOST_LAYOUTS) {
      await page.locator('#wxpost-layout').selectOption(layout);
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
  }
});
