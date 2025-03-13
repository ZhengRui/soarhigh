import { createClient } from '@supabase/supabase-js';
import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  {
    auth: {
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: true,
    },
  }
);

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

export const whoami = async (token?: string) => {
  const token_ = token || localStorage.getItem('token');

  if (!token_) {
    return null;
  }

  const headers = new Headers({ Accept: 'application/json' });
  headers.set('Authorization', `Bearer ${token_}`);

  const request = new Request(apiEndpoint + '/whoami', {
    method: 'GET',
    headers: headers,
  });

  const response = await fetch(request);
  if (response.status !== 200) {
    return null;
  }

  const user = await response.json();

  return user;
};

export const signin = async (username: string, password: string) => {
  const { data, error } = await supabase.auth.signInWithPassword({
    email: `${username}@soarhigh.internal`,
    password,
  });

  if (error) {
    throw error;
  }

  localStorage.setItem('token', data.session?.access_token);

  return {
    uid: data.user.id,
    username: data.user.user_metadata.username,
    full_name: data.user.user_metadata.full_name,
  };
};

export const getMembers = requestTemplate(
  () => ({
    url: apiEndpoint + '/members',
    method: 'GET',
  }),
  responseHandlerTemplate,
  null,
  true
);

export const isAdmin = requestTemplate(
  () => ({
    url: `${apiEndpoint}/is-admin`,
    method: 'GET',
  }),
  responseHandlerTemplate,
  null,
  true
);
