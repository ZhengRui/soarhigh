import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

import type {
  WxPostPresentation,
  WxPostRenderMode,
  WxPostWechatDraftResult,
  WxPostWechatDraftStatus,
} from '@/components/wxpost/types';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

const wechatResponseHandler = async (response: Response) => {
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error('The WeChat draft service returned an invalid response.');
  }
  if (!response.ok) {
    const detail =
      data && typeof data === 'object' && 'detail' in data ? data.detail : null;
    throw new Error(
      typeof detail === 'string'
        ? detail
        : `The WeChat draft request failed (${response.status}).`
    );
  }
  return data;
};

export const getWxPost = requestTemplate(
  (slug: string) => ({
    url: `${apiEndpoint}/posts/wxposts/${encodeURIComponent(slug)}`,
    method: 'GET',
  }),
  responseHandlerTemplate
);

export const deletePublicWxPost = requestTemplate(
  (wxpostId: string, expectedPublicRevision: number) => ({
    url: `${apiEndpoint}/posts/wxposts/${encodeURIComponent(wxpostId)}/publication`,
    method: 'DELETE',
    headers: new Headers({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    }),
    body: JSON.stringify({
      expectedPublicRevision,
    }),
  }),
  responseHandlerTemplate,
  null,
  true
);

export const getWxPostWechatDraft = requestTemplate(
  (wxpostId: string) => ({
    url: `${apiEndpoint}/posts/wxposts/${encodeURIComponent(wxpostId)}/wechat-draft`,
    method: 'GET',
  }),
  wechatResponseHandler,
  null,
  true
) as (wxpostId: string) => Promise<WxPostWechatDraftStatus>;

export const publishWxPostWechatDraft = requestTemplate(
  (
    wxpostId: string,
    expectedPublicRevision: number,
    presentation: WxPostPresentation,
    renderMode: WxPostRenderMode
  ) => ({
    url: `${apiEndpoint}/posts/wxposts/${encodeURIComponent(wxpostId)}/wechat-draft`,
    method: 'POST',
    headers: new Headers({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    }),
    body: JSON.stringify({
      expectedPublicRevision,
      presentation,
      confirmed: true,
      renderMode,
    }),
  }),
  wechatResponseHandler,
  null,
  true
) as (
  wxpostId: string,
  expectedPublicRevision: number,
  presentation: WxPostPresentation,
  renderMode: WxPostRenderMode
) => Promise<WxPostWechatDraftResult>;

export const getWxPostWechatPreview = requestTemplate(
  (wxpostId: string) => ({
    url: `${apiEndpoint}/posts/wxposts/${encodeURIComponent(wxpostId)}/wechat-draft/preview`,
    method: 'POST',
  }),
  wechatResponseHandler,
  null,
  true
) as (wxpostId: string) => Promise<{ previewUrl: string }>;

export const resetUncertainWxPostWechatDraft = requestTemplate(
  (wxpostId: string, expectedPublicRevision: number) => ({
    url: `${apiEndpoint}/posts/wxposts/${encodeURIComponent(wxpostId)}/wechat-draft/reset-uncertain`,
    method: 'POST',
    headers: new Headers({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    }),
    body: JSON.stringify({
      expectedPublicRevision,
      confirmedNoDraft: true,
    }),
  }),
  wechatResponseHandler,
  null,
  true
) as (
  wxpostId: string,
  expectedPublicRevision: number
) => Promise<WxPostWechatDraftStatus>;
