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
  article_revision: 4,
  created_at: '2026-07-25T12:00:00+00:00',
};

test('filters the shared Posts index and links WxPosts to their public route', async ({
  page,
}) => {
  let markWxPostRequestStarted: () => void = () => undefined;
  const wxpostRequestStarted = new Promise<void>((resolve) => {
    markWxPostRequestStarted = resolve;
  });
  let releaseWxPostResponse: () => void = () => undefined;
  const wxpostResponseReleased = new Promise<void>((resolve) => {
    releaseWxPostResponse = resolve;
  });

  await page.route(/\/posts\?.*kind=/, async (route) => {
    const kind = new URL(route.request().url()).searchParams.get('kind');
    if (kind === 'wxpost') {
      markWxPostRequestStarted();
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
  await expect(page.getByTestId(/delete-content-/)).toHaveCount(0);
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
  const regularPostColumns = await page
    .getByTestId('content-card-layout-post-post-1')
    .evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(regularPostColumns.trim().split(/\s+/)).toHaveLength(1);
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
    releaseWxPostResponse();
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

test('paginates every content filter and returns to page one after deleting the last item', async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('token', 'member-token');
  });
  await page.route(/\/whoami$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        uid: 'member-1',
        username: 'amy',
        full_name: 'Amy Fang',
      },
    });
  });

  const postItems = Array.from({ length: 11 }, (_, index) => ({
    ...ordinaryPost,
    id: `post-${index + 1}`,
    title: `Post item ${index + 1}`,
    slug: `post-item-${index + 1}`,
  }));
  let wxpostItems = Array.from({ length: 11 }, (_, index) => ({
    ...wxpost,
    id: `wxpost-${index + 1}`,
    title: `WxPost item ${index + 1}`,
    slug: `wxpost-item-${index + 1}`,
  }));
  const allItems = Array.from({ length: 11 }, (_, index) => ({
    ...(index % 2 === 0 ? ordinaryPost : wxpost),
    id: `all-${index + 1}`,
    title: `All item ${index + 1}`,
    slug: `all-item-${index + 1}`,
  }));
  const requests: string[] = [];

  await page.route(/\/posts\?.*kind=/, async (route) => {
    const url = new URL(route.request().url());
    const kind = url.searchParams.get('kind') ?? 'all';
    const currentPage = Number(url.searchParams.get('page'));
    const pageSize = Number(url.searchParams.get('page_size'));
    const source =
      kind === 'post' ? postItems : kind === 'wxpost' ? wxpostItems : allItems;
    const start = (currentPage - 1) * pageSize;
    requests.push(`${kind}:${currentPage}`);

    await route.fulfill({
      status: 200,
      json: {
        items: source.slice(start, start + pageSize),
        total: source.length,
        page: currentPage,
        page_size: pageSize,
        pages: Math.ceil(source.length / pageSize),
      },
    });
  });
  await page.route(
    /\/posts\/wxposts\/wxpost-11\/publication$/,
    async (route) => {
      wxpostItems = wxpostItems.filter((item) => item.id !== 'wxpost-11');
      await route.fulfill({ status: 200, json: { deleted: true } });
    }
  );

  await page.goto('/posts');
  await expect(page.getByText('Showing 1 to 10 of 11 posts')).toBeVisible();
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(
    page.getByRole('heading', { name: 'All item 11' })
  ).toBeVisible();
  await expect(page.getByText('Showing 11 to 11 of 11 posts')).toBeVisible();

  await page.getByTestId('posts-filter-post').click();
  await expect(
    page.getByRole('heading', { name: 'Post item 1', exact: true })
  ).toBeVisible();
  await expect(page.getByText('Showing 1 to 10 of 11 posts')).toBeVisible();
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(
    page.getByRole('heading', { name: 'Post item 11' })
  ).toBeVisible();

  await page.getByTestId('posts-filter-wxpost').click();
  await expect(
    page.getByRole('heading', { name: 'WxPost item 1', exact: true })
  ).toBeVisible();
  await expect(page.getByText('Showing 1 to 10 of 11 posts')).toBeVisible();
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(
    page.getByRole('heading', { name: 'WxPost item 11' })
  ).toBeVisible();

  await page
    .getByTestId('delete-content-wxpost-wxpost-11')
    .evaluate((button) => (button as HTMLButtonElement).click());
  await page
    .getByTestId('delete-content-dialog')
    .getByRole('button', { name: 'Delete public WxPost' })
    .evaluate((button) => {
      window.localStorage.setItem('token', 'member-token');
      (button as HTMLButtonElement).click();
    });

  await expect(
    page.getByRole('heading', { name: 'WxPost item 1', exact: true })
  ).toBeVisible();
  await expect(page.getByText('Showing 1 to 10 of 10 posts')).toBeVisible();
  expect(requests).toEqual([
    'all:1',
    'all:2',
    'post:1',
    'post:2',
    'wxpost:1',
    'wxpost:2',
    'wxpost:1',
  ]);
});

test('reveals the public WxPost delete action responsively and deletes from the index', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.addInitScript(() => {
    window.localStorage.setItem('token', 'member-token');
  });
  await page.route(/\/whoami$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        uid: 'member-1',
        username: 'amy',
        full_name: 'Amy Fang',
      },
    });
  });
  let contentItems = [wxpost, ordinaryPost];
  await page.route(/\/posts\?.*kind=/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: contentItems,
        total: contentItems.length,
        page: 1,
        page_size: 10,
        pages: 1,
      },
    });
  });

  let deletedWxPost: { id: string; revision: number } | null = null;
  await page.route(
    /\/posts\/wxposts\/([^/?]+)\/publication$/,
    async (route) => {
      const match = /\/posts\/wxposts\/([^/?]+)\/publication$/.exec(
        new URL(route.request().url()).pathname
      );
      deletedWxPost = {
        id: match?.[1] ?? '',
        revision: route.request().postDataJSON().expectedPublicRevision,
      };
      contentItems = contentItems.filter(
        (item) => item.kind !== 'wxpost' || item.id !== deletedWxPost?.id
      );
      await route.fulfill({ status: 200, json: { deleted: true } });
    }
  );
  await page.goto('/posts');
  const newPostButton = await page
    .getByTestId('new-post-menu-trigger')
    .boundingBox();
  const workspacesButton = await page
    .getByRole('link', { name: 'Wx Workspaces' })
    .boundingBox();
  expect(newPostButton).not.toBeNull();
  expect(workspacesButton).not.toBeNull();
  expect(newPostButton!.height).toBe(workspacesButton!.height);

  const wxPostExcerpt = page.getByText(wxpost.excerpt, { exact: true });
  await expect(wxPostExcerpt).toHaveCSS('-webkit-line-clamp', '2');

  const wxPostDelete = page.getByTestId('delete-content-wxpost-wxpost-1');
  await expect(wxPostDelete).toBeVisible();
  await expect(page.getByTestId('delete-content-post-post-1')).toHaveCount(0);
  await expect(wxPostDelete).toHaveCSS('opacity', '0');

  await wxPostDelete.locator('xpath=ancestor::article').hover();
  await expect(wxPostDelete).toHaveCSS('opacity', '0.6');
  await wxPostDelete.hover();
  await expect(wxPostDelete).toHaveCSS('opacity', '1');
  await expect(wxPostDelete).toHaveCSS('color', 'rgb(185, 28, 28)');

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(wxPostDelete).toHaveCSS('opacity', '0.6');
  await expect(wxPostExcerpt).toHaveCSS('-webkit-line-clamp', '4');

  await page.setViewportSize({ width: 320, height: 844 });
  const boundaryNewPostButton = await page
    .getByTestId('new-post-menu-trigger')
    .boundingBox();
  const boundaryWorkspacesButton = await page
    .getByRole('link', { name: 'Wx Workspaces' })
    .boundingBox();
  expect(boundaryNewPostButton).not.toBeNull();
  expect(boundaryWorkspacesButton).not.toBeNull();
  expect(boundaryWorkspacesButton!.y).toBe(boundaryNewPostButton!.y);

  await page.setViewportSize({ width: 319, height: 844 });
  const narrowNewPostButton = await page
    .getByTestId('new-post-menu-trigger')
    .boundingBox();
  const narrowWorkspacesButton = await page
    .getByRole('link', { name: 'Wx Workspaces' })
    .boundingBox();
  expect(narrowNewPostButton).not.toBeNull();
  expect(narrowWorkspacesButton).not.toBeNull();
  expect(narrowWorkspacesButton!.y).toBeGreaterThan(
    narrowNewPostButton!.y + narrowNewPostButton!.height
  );

  await wxPostDelete.click();
  const dialog = page.getByTestId('delete-content-dialog');
  await expect(dialog).toContainText(
    'The private workspace and Draft will remain.'
  );
  await dialog
    .getByRole('button', { name: 'Delete public WxPost' })
    .evaluate((button) => {
      window.localStorage.setItem('token', 'member-token');
      (button as HTMLButtonElement).click();
    });
  await expect(
    page.getByRole('heading', {
      name: 'The Courage to Try the Next Sentence',
    })
  ).toHaveCount(0);
  expect(deletedWxPost).toEqual({ id: 'wxpost-1', revision: 4 });
});
