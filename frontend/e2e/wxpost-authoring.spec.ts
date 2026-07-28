import { expect, test, type Page } from '@playwright/test';

const MEETING_462 = {
  id: 'meeting-462',
  type: 'Regular',
  no: 462,
  theme: 'Culture, belonging, and the courage to speak',
  manager: {
    id: 'manager-462',
    member_id: 'albert',
    name: 'Albert Ding',
  },
  date: '2026-07-15',
  start_time: '19:15',
  end_time: '21:30',
  location: 'Gobel Power Energy · Shenzhen',
  introduction:
    'Food, clothes, festivals, and travel stories—culture is present in the ordinary details of everyday life. We grow up in different places, shaped by different customs, languages, and ways of seeing the world. Meeting 462 invites members and guests to share what feels familiar, what surprised them when travelling, and which traditions they would carry into a new home.\n\n吃的、穿的、过节怎么过、旅行去了哪里——这些日常细节里，都是文化的影子。随便聊，随便问，一起坐下来，把天南海北的生活都摊开来看看。',
  segments: [
    {
      id: 'segment-1',
      type: 'Registration and warm-up',
      start_time: '19:15',
      duration: '15',
      end_time: '19:30',
      role_taker: {
        member_id: 'reception',
        name: 'Reception team',
      },
    },
    {
      id: 'segment-2',
      type: 'Opening',
      start_time: '19:30',
      duration: '10',
      end_time: '19:40',
      role_taker: {
        member_id: 'tm',
        name: 'Albert Ding',
      },
    },
    {
      id: 'segment-3',
      type: 'Table Topics',
      start_time: '19:40',
      duration: '25',
      end_time: '20:05',
      role_taker: {
        member_id: 'joyce',
        name: 'Joyce Feng',
      },
      title: 'Culture in daily life',
    },
    {
      id: 'segment-4',
      type: 'Prepared Speech',
      start_time: '20:05',
      duration: '12',
      end_time: '20:17',
      role_taker: {
        member_id: 'rui',
        name: 'Rui Zheng',
      },
      title: 'A Tale of Two Homes',
    },
    {
      id: 'segment-5',
      type: 'Prepared Speech',
      start_time: '20:17',
      duration: '12',
      end_time: '20:29',
      role_taker: {
        member_id: 'nina',
        name: 'Nina',
      },
      title: 'Listening Across Cultures',
    },
    {
      id: 'segment-6',
      type: 'Evaluations',
      start_time: '20:29',
      duration: '31',
      end_time: '21:00',
      role_taker: {
        member_id: 'roc',
        name: 'Roc',
      },
    },
    {
      id: 'segment-7',
      type: 'Recognition and closing',
      start_time: '21:00',
      duration: '30',
      end_time: '21:30',
      role_taker: {
        member_id: 'albert',
        name: 'Albert Ding',
      },
    },
  ],
  status: 'published',
  awards: [
    {
      meeting_id: 'meeting-462',
      category: 'Best Prepared Speaker',
      winner: 'Rui Zheng',
    },
    {
      meeting_id: 'meeting-462',
      category: 'Best Table Topic Speaker',
      winner: 'Nina',
    },
  ],
};

const MEETING_461 = {
  ...MEETING_462,
  id: 'meeting-461',
  type: 'Workshop',
  no: 461,
  date: '2026-07-08',
  theme: 'Build a speech people remember',
  introduction:
    'A practical workshop for shaping a clear idea into a memorable speech.',
  segments: [
    {
      id: 'workshop-segment',
      type: 'Workshop',
      start_time: '19:30',
      duration: '90',
      end_time: '21:00',
      role_taker: {
        member_id: 'facilitator',
        name: 'Workshop facilitator',
      },
      title: 'From idea to stage',
    },
  ],
  awards: [],
};

const MEETING_449 = {
  ...MEETING_461,
  id: 'meeting-449',
  type: 'Special Event',
  no: undefined,
  date: '2026-04-08',
  theme: 'Beyond the Mask: Authenticity in Connection',
};

const FIRST_SOURCE_KEY = 'meetings/462/meeting-room.jpg';

const MEETING_OPTIONS = [
  MEETING_462,
  MEETING_461,
  ...Array.from({ length: 98 }, (_, index) => ({
    ...MEETING_461,
    id: `meeting-extra-${index + 1}`,
    no: 1000 - index,
    theme: `Meeting theme ${1000 - index}`,
  })),
  MEETING_449,
];

async function mockAuthenticatedMember(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'wxpost-authoring-e2e-token');

    const removeItem = Storage.prototype.removeItem;
    Storage.prototype.removeItem = function removeItemForAuthoringTest(key) {
      if (key === 'token') return;
      removeItem.call(this, key);
    };
  });

  await page.route(/\/whoami$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        uid: 'member-e2e',
        username: 'e2e',
        full_name: 'WXPost E2E',
      },
    });
  });
}

async function mockWxPostReadApis(page: Page) {
  await page.route(
    /\/meetings\/options\?page=(1|2|3)&page_size=50$/,
    async (route) => {
      const pageNumber = Number(
        new URL(route.request().url()).searchParams.get('page')
      );
      const pageStart = (pageNumber - 1) * 50;
      await route.fulfill({
        status: 200,
        json: {
          items: MEETING_OPTIONS.slice(pageStart, pageStart + 50).map(
            ({ id, no, type, theme, date }) => ({
              id,
              no,
              type,
              theme,
              date,
            })
          ),
          total: 101,
          page: pageNumber,
          page_size: 50,
          pages: 3,
        },
      });
    }
  );

  await page.route(/\/meetings\/meeting-462$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: MEETING_462,
    });
  });

  await page.route(/\/meetings\/meeting-461$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: MEETING_461,
    });
  });

  await page.route(/\/meetings\/meeting-449$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: MEETING_449,
    });
  });

  await page.route(/\/meetings\/meeting-462\/media$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: [
          {
            filename: 'meeting-room.jpg',
            url: '/images/toastmasters.png',
            fileKey: 'meetings/462/meeting-room.jpg',
            uploadedAt: '2026-07-15T12:00:00Z',
          },
          {
            filename: 'group-photo.jpg',
            url: '/images/toastmasters_excel.png',
            fileKey: 'meetings/462/group-photo.jpg',
            uploadedAt: '2026-07-15T12:01:00Z',
          },
          {
            filename: 'closing-video.mp4',
            url: 'https://example.com/closing-video.mp4',
            fileKey: 'meetings/462/closing-video.mp4',
            uploadedAt: '2026-07-15T12:02:00Z',
          },
        ],
      },
    });
  });

  await page.route(/\/meetings\/meeting-461\/media$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: { items: [] },
    });
  });
}

async function openAuthoringPage(page: Page) {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await page.goto('/posts/wxposts/new');
  await expect(
    page.getByRole('heading', { name: 'New WeChat Post' })
  ).toBeVisible();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#462'
  );
}

test('opens the WXPost setup flow from the authenticated Posts page', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await page.route(/\/posts\?.*kind=/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        pages: 0,
      },
    });
  });

  await page.goto('/posts');
  await page.getByTestId('new-wxpost-link').click();
  await expect(page).toHaveURL('/posts/wxposts/new');
  await expect(
    page.getByRole('heading', { name: 'New WeChat Post' })
  ).toBeVisible();
});

test('uses real meeting data from the dropdown and keeps source independent from article type', async ({
  page,
}) => {
  await openAuthoringPage(page);

  const setup = page.getByTestId('setup-stage');
  await expect(setup.getByTestId('article-type-meeting-recap')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page.getByTestId('association-linked')).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await page.getByTestId('meeting-select-trigger').click();
  const meetingOptions = page
    .getByTestId('meeting-select-options')
    .getByRole('option');
  await expect(meetingOptions).toHaveCount(50);
  await page
    .getByTestId('meeting-select-options')
    .getByRole('listbox')
    .evaluate((list) => {
      list.scrollTop = list.scrollHeight;
      list.dispatchEvent(new Event('scroll', { bubbles: true }));
    });
  await expect(meetingOptions).toHaveCount(100);
  await page
    .getByTestId('meeting-select-options')
    .getByRole('listbox')
    .evaluate((list) => {
      list.scrollTop = list.scrollHeight;
      list.dispatchEvent(new Event('scroll', { bubbles: true }));
    });
  await expect(meetingOptions).toHaveCount(101);
  await expect(page.getByTestId('meeting-option-meeting-449')).toContainText(
    'Beyond the Mask'
  );
  await expect(page.getByTestId('meeting-option-meeting-449')).toContainText(
    'Special Event · Apr 8, 2026'
  );
  await expect(
    page.getByTestId('meeting-option-meeting-449')
  ).not.toContainText('Special Event · Special Event');
  await page.getByTestId('meeting-option-meeting-461').click();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#461'
  );

  await setup.getByTestId('article-type-member-story').click();
  await expect(setup.getByTestId('article-type-member-story')).toHaveAttribute(
    'aria-pressed',
    'true'
  );

  await expect(page.getByText('Workshop #461 · Member Story')).toBeVisible();

  await page.getByTestId('association-independent').click();
  await expect(page.getByTestId('meeting-select-trigger')).toHaveCount(0);
  await expect(
    page.getByText('Independent article · Member Story')
  ).toBeVisible();

  await page.getByTestId('continue-to-materials').click();
  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId('meeting-context')).toHaveCount(0);
  await expect(page.getByText('No media', { exact: true })).toBeVisible();
  await expect(
    page.getByTestId('materials-stage').getByTestId('article-type-member-story')
  ).toHaveAttribute('aria-pressed', 'true');
});

test('shows complete linked meeting context from the API and keeps nested sections collapsed', async ({
  page,
}) => {
  await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();

  const contextToggle = page.getByTestId('meeting-context-toggle');
  await expect(contextToggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByTestId('meeting-description')).toHaveCount(0);

  await contextToggle.click();
  await expect(contextToggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByText('Venue', { exact: true })).toBeVisible();
  await expect(
    page
      .getByTestId('meeting-context')
      .getByText('Gobel Power Energy · Shenzhen', { exact: true })
  ).toBeVisible();

  await page.getByTestId('meeting-description-toggle').click();
  await expect(page.getByTestId('meeting-description')).toContainText(
    '把天南海北的生活都摊开来看看'
  );

  await page.getByTestId('meeting-agenda-toggle').click();
  const agenda = page.getByTestId('meeting-agenda');
  await expect(agenda.getByRole('row')).toHaveCount(8);
  await expect(
    agenda.getByRole('columnheader', { name: 'Role taker' })
  ).toBeVisible();
  await expect(
    agenda.getByRole('columnheader', {
      name: 'Speech / workshop title',
    })
  ).toBeVisible();
  await expect(agenda.getByText('A Tale of Two Homes')).toBeVisible();

  await page.getByTestId('meeting-awards-toggle').click();
  const awards = page.getByTestId('meeting-awards');
  await expect(awards.getByText('Best Prepared Speaker')).toBeVisible();
  await expect(awards.getByText('Rui Zheng')).toBeVisible();
});

test('edits material descriptions, previews images, and changes article type without mutations', async ({
  page,
}) => {
  const mutationRequests: string[] = [];
  const pageErrors: string[] = [];

  page.on('request', (request) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      mutationRequests.push(`${request.method()} ${request.url()}`);
    }
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();

  const materialsStage = page.getByTestId('materials-stage');
  const firstMaterial = page.getByTestId(`material-${FIRST_SOURCE_KEY}`);
  await expect(firstMaterial.getByText('Meeting Library')).toHaveCount(1);
  await expect(firstMaterial.getByText('meeting-room.jpg')).toHaveCount(1);
  await expect(
    firstMaterial.getByRole('button', { name: 'Use material' })
  ).toBeVisible();
  await expect(
    firstMaterial.getByRole('button', { name: 'Generate description' })
  ).toBeVisible();
  await expect(firstMaterial.getByText('Preview', { exact: true })).toHaveCount(
    0
  );

  await materialsStage.getByTestId('article-type-action-guide').click();
  await expect(
    materialsStage.getByTestId('article-type-action-guide')
  ).toHaveAttribute('aria-pressed', 'true');

  const description = page.getByTestId(`description-${FIRST_SOURCE_KEY}`);
  await description.fill(
    'Members arrive early and make space for one another.'
  );
  await expect(description).toHaveValue(
    'Members arrive early and make space for one another.'
  );
  await description.focus();
  await expect
    .poll(() =>
      description.evaluate(
        (element) => getComputedStyle(element).borderTopWidth
      )
    )
    .toBe('1px');

  await page.getByRole('button', { name: 'Preview meeting-room.jpg' }).click();
  await expect(page.getByTestId('material-lightbox')).toBeVisible();
  await expect(page.getByTestId('material-lightbox')).toContainText(
    'Members arrive early and make space for one another.'
  );
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('material-lightbox')).toHaveCount(0);

  await page.getByRole('button', { name: 'Change setup' }).click();
  await page.getByRole('button', { name: '2 Materials', exact: true }).click();
  await expect(page.getByTestId(`description-${FIRST_SOURCE_KEY}`)).toHaveValue(
    'Members arrive early and make space for one another.'
  );
  await expect(
    materialsStage.getByTestId('article-type-action-guide')
  ).toHaveAttribute('aria-pressed', 'true');

  await expect(
    page.getByTestId(`workspace-${FIRST_SOURCE_KEY}`)
  ).toBeDisabled();
  await expect(page.getByTestId(`include-${FIRST_SOURCE_KEY}`)).toBeDisabled();

  await page.getByTestId('writing-approach-image-driven').click();
  await expect(
    page.getByTestId('writing-approach-image-driven')
  ).toHaveAttribute('aria-pressed', 'true');

  const transcriptBox = await page
    .getByTestId('meeting-transcript')
    .boundingBox();
  const notesBox = await page.getByTestId('extra-notes').boundingBox();
  expect(transcriptBox).not.toBeNull();
  expect(notesBox).not.toBeNull();
  expect(notesBox!.y).toBeGreaterThan(transcriptBox!.y + transcriptBox!.height);

  expect(mutationRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('shows the meeting error instead of staying in a loading state', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  let meetingShouldFail = true;
  let mediaShouldFail = true;
  await page.route(/\/meetings\/meeting-462$/, async (route) => {
    await route.fulfill(
      meetingShouldFail
        ? {
            status: 500,
            json: { detail: 'Unable to load meeting' },
          }
        : {
            status: 200,
            json: MEETING_462,
          }
    );
  });
  await page.route(/\/meetings\/meeting-462\/media$/, async (route) => {
    await route.fulfill(
      mediaShouldFail
        ? {
            status: 500,
            json: { detail: 'Unable to load meeting media' },
          }
        : {
            status: 200,
            json: {
              items: [
                {
                  filename: 'meeting-room.jpg',
                  url: '/images/toastmasters.png',
                  fileKey: FIRST_SOURCE_KEY,
                  uploadedAt: '2026-07-15T12:00:00Z',
                },
              ],
            },
          }
    );
  });

  await page.goto('/posts/wxposts/new');
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#462'
  );
  await page.getByTestId('continue-to-materials').click();

  await expect(page.getByText('Unable to load meeting details')).toBeVisible();
  await expect(page.getByText('Loading media…')).toHaveCount(0);

  meetingShouldFail = false;
  await page.getByTestId('retry-materials-load').click();
  await expect(page.getByText('Unable to load meeting media')).toBeVisible();

  mediaShouldFail = false;
  await page.getByTestId('retry-materials-load').click();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();
});

test('retries the meeting options request without reloading the page', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  let shouldFail = true;
  await page.route(
    /\/meetings\/options\?page=1&page_size=50$/,
    async (route) => {
      await route.fulfill(
        shouldFail
          ? {
              status: 500,
              json: { detail: 'Unable to load meeting options' },
            }
          : {
              status: 200,
              json: {
                items: MEETING_OPTIONS.slice(0, 50).map(
                  ({ id, no, type, theme, date }) => ({
                    id,
                    no,
                    type,
                    theme,
                    date,
                  })
                ),
                total: 101,
                page: 1,
                page_size: 50,
                pages: 3,
              },
            }
      );
    }
  );

  await page.goto('/posts/wxposts/new');
  await expect(page.getByText('Unable to load meetings')).toBeVisible();

  shouldFail = false;
  await page.getByTestId('retry-meeting-options').click();
  await expect(page.getByTestId('meeting-select-trigger')).toContainText(
    '#462'
  );
});

test('resets meeting-specific inputs when the selected meeting changes', async ({
  page,
}) => {
  await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();
  await page
    .getByTestId('meeting-transcript')
    .fill('Transcript that belongs only to meeting 462');

  await page.getByRole('button', { name: 'Change setup' }).click();
  await page.getByTestId('meeting-select-trigger').click();
  await page.getByTestId('meeting-option-meeting-461').click();
  await page.getByRole('button', { name: '2 Materials', exact: true }).click();

  await expect(page.getByTestId('meeting-transcript')).toHaveValue('');
  await expect(page.getByTestId('extra-notes')).toHaveValue('');
  await expect(page.getByTestId('writing-guidance')).toHaveValue('');
});

test('keeps the full materials workflow readable on a 390px mobile viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthoringPage(page);
  await page.getByTestId('continue-to-materials').click();

  await expect(page.getByTestId('materials-stage')).toBeVisible();
  await expect(page.getByTestId(`material-${FIRST_SOURCE_KEY}`)).toBeVisible();

  const geometry = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    materialWidths: Array.from(
      document.querySelectorAll<HTMLElement>('[data-testid^="material-"]')
    ).map((material) => material.getBoundingClientRect().width),
  }));

  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  expect(geometry.materialWidths.length).toBeGreaterThan(0);
  expect(
    geometry.materialWidths.every(
      (width) => width <= geometry.viewportWidth - 20
    )
  ).toBe(true);

  await page.getByTestId('meeting-context-toggle').click();
  await page.getByTestId('meeting-agenda-toggle').click();
  await expect(page.getByText('Listening Across Cultures')).toBeVisible();
});
