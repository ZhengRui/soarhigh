import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

// Get all posts (public ones for anon, all for authenticated)
export const getPosts = requestTemplate(
  (options: { page?: number; page_size?: number } = {}) => {
    const page = options.page || 1;
    const page_size = options.page_size || 10;

    const url = `${apiEndpoint}/posts?page=${page}&page_size=${page_size}`;

    return {
      url,
      method: 'GET',
    };
  },
  responseHandlerTemplate,
  null,
  true,
  true // soft auth
);

// Get single post
export const getPost = requestTemplate(
  (slug: string) => ({
    url: `${apiEndpoint}/posts/${slug}`,
    method: 'GET',
  }),
  responseHandlerTemplate,
  null,
  true,
  true // soft auth
);

// Create post (requires auth)
export const createPost = requestTemplate(
  (data: {
    title: string;
    slug: string;
    content: string;
    is_public: boolean;
  }) => ({
    url: `${apiEndpoint}/posts`,
    method: 'POST',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify(data),
  }),
  responseHandlerTemplate,
  null,
  true // requires auth
);

// Update post (requires auth)
export const updatePost = requestTemplate(
  (data: {
    title?: string;
    slug: string;
    content?: string;
    is_public?: boolean;
  }) => ({
    url: `${apiEndpoint}/posts/${data.slug}`,
    method: 'PATCH',
    headers: new Headers({
      'Content-Type': 'application/json',
      Accept: 'application/json',
    }),
    body: JSON.stringify(data),
  }),
  responseHandlerTemplate,
  null,
  true // requires auth
);

// Delete post (requires auth)
export const deletePost = requestTemplate(
  (slug: string) => ({
    url: `${apiEndpoint}/posts/${slug}`,
    method: 'DELETE',
  }),
  responseHandlerTemplate,
  null,
  true // requires auth
);
