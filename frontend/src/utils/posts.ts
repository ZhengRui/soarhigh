import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

export interface Post {
  id: string;
  title: string;
  slug: string;
  content: string;
  is_public: boolean;
  author_id: string;
  created_at: string;
  updated_at: string;
}

export interface PostAuthor {
  uid: string;
  username: string;
  full_name: string;
}

export interface PostWithAuthor extends Post {
  author: PostAuthor;
}

// Get all posts (public ones for anon, all for authenticated)
export const getPosts = requestTemplate(
  () => ({
    url: `${apiEndpoint}/posts`,
    method: 'GET',
  }),
  responseHandlerTemplate,
  null,
  false,
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
  false,
  true // soft auth
);

// Create post (requires auth)
export const createPost = requestTemplate(
  (data: { title: string; content: string; is_public: boolean }) => ({
    url: `${apiEndpoint}/posts`,
    method: 'POST',
    body: JSON.stringify(data),
  }),
  responseHandlerTemplate,
  null,
  true // requires auth
);

// Update post (requires auth)
export const updatePost = requestTemplate(
  (
    slug: string,
    data: { title?: string; content?: string; is_public?: boolean }
  ) => ({
    url: `${apiEndpoint}/posts/${slug}`,
    method: 'PATCH',
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
