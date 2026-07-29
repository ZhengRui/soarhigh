import { expect, test } from '@playwright/test';

import {
  mockAuthenticatedMember,
  mockWxPostReadApis,
} from './support/wxpostAuthoring';

test('keeps the drafts page aligned with the new WXPost page', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  await page.route(/\/posts\/wxposts\/workspaces$/, async (route) => {
    await route.fulfill({ status: 200, json: { items: [] } });
  });

  await page.goto('/posts/wxposts/new');
  const newPageShell = await page
    .getByTestId('wxpost-page-shell')
    .boundingBox();
  const newPageBackLink = await page
    .getByRole('link', { name: 'Back to Posts' })
    .boundingBox();

  await page.goto('/posts/wxposts/drafts');
  const draftsPageShell = await page
    .getByTestId('wxpost-page-shell')
    .boundingBox();
  const draftsPageBackLink = page.getByRole('link', {
    name: 'Back to New WeChat Post',
  });

  await expect(draftsPageBackLink).toHaveAttribute(
    'href',
    '/posts/wxposts/new'
  );
  expect(draftsPageShell?.x).toBe(newPageShell?.x);
  expect(draftsPageShell?.width).toBe(newPageShell?.width);
  expect((await draftsPageBackLink.boundingBox())?.x).toBe(newPageBackLink?.x);
});

test('lists shared WXPost drafts and lets any member delete one', async ({
  page,
}) => {
  await mockAuthenticatedMember(page);
  await mockWxPostReadApis(page);
  let deleted = false;
  let listRequests = 0;
  await page.route(/\/posts\/wxposts\/workspaces$/, async (route) => {
    listRequests += 1;
    await route.fulfill({
      status: 200,
      json: {
        items: deleted
          ? []
          : [
              {
                workspaceId: 'wxpost-4f2c9a7bd861',
                createdBy: { id: 'member-123', name: 'Test Member' },
                createdAt: '2026-07-29T03:00:00Z',
                updatedAt: '2026-07-29T03:15:00Z',
                meetingId: 'meeting-462',
                articleType: 'meeting-recap',
                customArticleType: null,
                manifestVersion: 4,
                sourceCount: 3,
                readySourceCount: 1,
                includedSourceCount: 1,
                hasDraft: false,
              },
            ],
      },
    });
  });
  await page.route(
    /\/posts\/wxposts\/workspaces\/wxpost-4f2c9a7bd861$/,
    async (route) => {
      expect(route.request().headers()['x-expected-manifest-version']).toBe(
        '4'
      );
      deleted = true;
      await route.fulfill({
        status: 200,
        json: {
          workspaceId: 'wxpost-4f2c9a7bd861',
          deleted: true,
        },
      });
    }
  );

  await page.goto('/posts/wxposts/drafts');
  await expect(
    page.getByRole('heading', { name: 'WXPost Drafts' })
  ).toBeVisible();
  const workspace = page.getByTestId('workspace-wxpost-4f2c9a7bd861');
  await expect(workspace.getByText('Meeting #462')).toBeVisible();
  await expect(workspace.getByText('Meeting Recap')).toBeVisible();
  await expect(workspace.getByText(/Created by Test Member/)).toBeVisible();
  await expect(
    workspace.getByRole('link', { name: 'Continue' })
  ).toHaveAttribute('href', '/posts/wxposts/new?workspace=wxpost-4f2c9a7bd861');

  await workspace.getByRole('button', { name: /Delete Meeting #462/ }).click();
  const dialog = page.getByTestId('delete-workspace-dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: 'Delete draft' }).click();
  await expect(page.getByText('No WXPost drafts yet.')).toBeVisible();
  expect(listRequests).toBe(1);
});
