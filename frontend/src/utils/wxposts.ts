import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

export const getWxPost = requestTemplate(
  (slug: string) => ({
    url: `${apiEndpoint}/posts/wxposts/${encodeURIComponent(slug)}`,
    method: 'GET',
  }),
  responseHandlerTemplate
);
