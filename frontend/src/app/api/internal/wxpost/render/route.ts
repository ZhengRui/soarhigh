import { timingSafeEqual } from 'node:crypto';

import { compileWxPost } from '@/components/wxpost/renderer/compiler';
import { compileWxPostForWechat } from '@/components/wxpost/renderer/wechatMiniEmitter';
import {
  WXPOST_APPEARANCES,
  WXPOST_LAYOUTS,
  WXPOST_PALETTES,
  WXPOST_TYPEFACES,
  type WxPostCompileRequest,
} from '@/components/wxpost/types';

const RENDER_MODES = ['canonical', 'mini'] as const;
type RenderMode = (typeof RENDER_MODES)[number];

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MAX_REQUEST_BYTES = 2 * 1024 * 1024;

function authorized(request: Request) {
  const expected = process.env.WXPOST_SERVICE_TOKEN;
  const authorization = request.headers.get('authorization');
  if (!expected || !authorization?.startsWith('Bearer ')) return false;
  const received = authorization.slice('Bearer '.length);
  const expectedBytes = Buffer.from(expected);
  const receivedBytes = Buffer.from(received);
  return (
    expectedBytes.length === receivedBytes.length &&
    timingSafeEqual(expectedBytes, receivedBytes)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function isCompileRequest(value: unknown): value is WxPostCompileRequest {
  if (!isRecord(value)) return false;
  const document = value.renderDocument;
  const presentation = value.presentation;
  const context = value.context;
  return Boolean(
    isRecord(document) &&
      document.renderVersion === 1 &&
      typeof document.title === 'string' &&
      Array.isArray(document.body) &&
      Array.isArray(document.media) &&
      isRecord(presentation) &&
      WXPOST_LAYOUTS.includes(
        presentation.layout as (typeof WXPOST_LAYOUTS)[number]
      ) &&
      WXPOST_PALETTES.includes(
        presentation.palette as (typeof WXPOST_PALETTES)[number]
      ) &&
      WXPOST_APPEARANCES.includes(
        presentation.appearance as (typeof WXPOST_APPEARANCES)[number]
      ) &&
      WXPOST_TYPEFACES.includes(
        presentation.typeface as (typeof WXPOST_TYPEFACES)[number]
      ) &&
      isRecord(context)
  );
}

function isRenderMode(value: unknown): value is RenderMode {
  return RENDER_MODES.includes(value as RenderMode);
}

function jsonError(status: number, message: string) {
  return Response.json(
    { error: { code: 'render_failed', message } },
    { status, headers: { 'Cache-Control': 'no-store' } }
  );
}

export async function POST(request: Request) {
  if (!process.env.WXPOST_SERVICE_TOKEN) {
    return jsonError(503, 'WxPost renderer authentication is not configured.');
  }
  if (!authorized(request)) {
    return jsonError(401, 'Invalid WxPost service credential.');
  }
  const contentLength = Number(request.headers.get('content-length') ?? 0);
  if (contentLength > MAX_REQUEST_BYTES) {
    return jsonError(413, 'WxPost render request is too large.');
  }

  let rawBody: string;
  try {
    rawBody = await request.text();
  } catch {
    return jsonError(400, 'WxPost render request must be valid JSON.');
  }
  if (Buffer.byteLength(rawBody) > MAX_REQUEST_BYTES) {
    return jsonError(413, 'WxPost render request is too large.');
  }

  let payload: unknown;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return jsonError(400, 'WxPost render request must be valid JSON.');
  }
  const requestedRenderMode = isRecord(payload)
    ? payload.renderMode
    : undefined;
  if (requestedRenderMode !== undefined && !isRenderMode(requestedRenderMode)) {
    return jsonError(422, 'WxPost render request does not match the contract.');
  }
  if (!isCompileRequest(payload)) {
    return jsonError(422, 'WxPost render request does not match the contract.');
  }
  const renderMode: RenderMode = requestedRenderMode ?? 'canonical';

  try {
    const result =
      renderMode === 'mini'
        ? compileWxPostForWechat(payload)
        : compileWxPost(payload);
    return Response.json(result, {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch {
    return jsonError(422, 'WxPost render input could not be compiled.');
  }
}
