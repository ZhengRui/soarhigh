export const dynamic = 'force-dynamic';

function apiUrl(path: string) {
  const base = (process.env.NEXT_PUBLIC_API_ENDPOINT ?? '').replace(/\/$/, '');
  return `${base}${path}`;
}

export async function GET(
  _request: Request,
  {
    params,
  }: {
    params: Promise<{ token: string; sourceId: string }>;
  }
) {
  const { token, sourceId } = await params;
  const response = await fetch(
    apiUrl(
      `/posts/wxposts/draft-previews/${encodeURIComponent(token)}/media/${encodeURIComponent(sourceId)}`
    ),
    { cache: 'no-store' }
  );
  if (!response.ok) {
    return new Response(null, {
      status: response.status,
      headers: { 'Cache-Control': 'private, no-store' },
    });
  }
  return new Response(response.body, {
    status: 200,
    headers: {
      'Cache-Control': 'private, no-store',
      'Content-Type':
        response.headers.get('content-type') ?? 'application/octet-stream',
    },
  });
}
