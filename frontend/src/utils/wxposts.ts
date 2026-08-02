import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

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
