import { expect, test } from '@playwright/test';

const ordinaryPost = {
  kind: 'post',
  id: 'post-1',
  title: 'How We Prepare a Speech',
  slug: 'how-we-prepare-a-speech',
  excerpt: 'A practical note from a club member.',
  author: { member_id: 'member-1', name: 'Amy Fang' },
  is_public: true,
  cover_image_url: null,
  created_at: '2026-07-24T12:00:00+00:00',
};

const wxpost = {
  kind: 'wxpost',
  id: 'wxpost-1',
  title: 'The Courage to Try the Next Sentence',
  slug: 'the-courage-to-try-the-next-sentence',
  excerpt: 'A meeting recap about learning in public.',
  author: { member_id: null, name: 'SoarHigh Toastmasters' },
  is_public: true,
  cover_image_url: null,
  created_at: '2026-07-25T12:00:00+00:00',
};

test('filters the shared Posts index and links WXPosts to their public route', async ({
  page,
}) => {
  let markWxpostRequestStarted: () => void = () => undefined;
  const wxpostRequestStarted = new Promise<void>((resolve) => {
    markWxpostRequestStarted = resolve;
  });
  let releaseWxpostResponse: () => void = () => undefined;
  const wxpostResponseReleased = new Promise<void>((resolve) => {
    releaseWxpostResponse = resolve;
  });

  await page.route(/\/posts\?.*kind=/, async (route) => {
    const kind = new URL(route.request().url()).searchParams.get('kind');
    if (kind === 'wxpost') {
      markWxpostRequestStarted();
      await wxpostResponseReleased;
    }
    const items =
      kind === 'post'
        ? [ordinaryPost]
        : kind === 'wxpost'
          ? [wxpost]
          : [wxpost, ordinaryPost];

    await route.fulfill({
      status: 200,
      json: {
        items,
        total: items.length,
        page: 1,
        page_size: 10,
        pages: 1,
      },
    });
  });

  await page.goto('/posts');

  await expect(
    page.getByRole('heading', {
      name: 'The Courage to Try the Next Sentence',
    })
  ).toBeVisible();
  await expect(page.getByTestId('wxpost-badge')).toBeVisible();
  await expect(
    page.getByRole('link', {
      name: /The Courage to Try the Next Sentence/,
    })
  ).toHaveAttribute(
    'href',
    '/posts/wxposts/the-courage-to-try-the-next-sentence'
  );

  await page.getByTestId('posts-filter-post').click();
  await expect(
    page.getByRole('heading', { name: 'How We Prepare a Speech' })
  ).toBeVisible();
  await expect(
    page.getByRole('heading', {
      name: 'The Courage to Try the Next Sentence',
    })
  ).toHaveCount(0);

  await page.getByTestId('posts-filter-wxpost').click();
  await wxpostRequestStarted;
  try {
    await expect(page.getByTestId('posts-loading')).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'How We Prepare a Speech' })
    ).toHaveCount(0);
  } finally {
    releaseWxpostResponse();
  }
  await expect(
    page.getByRole('heading', {
      name: 'The Courage to Try the Next Sentence',
    })
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'How We Prepare a Speech' })
  ).toHaveCount(0);
});
