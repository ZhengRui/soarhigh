'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { WxPostRenderDocument } from '@/components/wxpost/types';
import {
  getWorkspaceSourceContent,
  type WorkspaceSource,
} from '@/utils/wxpostWorkspace';

export const DRAFT_MEDIA_TIMEOUT_MS = 15_000;

export type WxPostDraftMediaState = 'loading' | 'ready' | 'failed';

type MediaPlanItem = {
  id: string;
  kind: 'image' | 'video';
  contentSha256: string;
  dimensions: { width: number; height: number } | null;
};

async function decodeImage(url: string) {
  const image = new Image();
  image.src = url;
  await image.decode();
}

export function useWxPostDraftMedia({
  workspaceId,
  renderDocument,
  sources,
}: {
  workspaceId: string;
  renderDocument: WxPostRenderDocument | null;
  sources: WorkspaceSource[];
}) {
  const plan = useMemo(() => {
    const sourceById = new Map(sources.map((source) => [source.id, source]));
    const itemById = new Map<string, MediaPlanItem>();
    for (const media of renderDocument?.media ?? []) {
      const source = sourceById.get(media.id);
      if (
        !media.include ||
        !source?.workspaceReady ||
        !source.contentSha256 ||
        (source.kind !== 'image' && source.kind !== 'video')
      ) {
        continue;
      }
      itemById.set(media.id, {
        id: media.id,
        kind: source.kind,
        contentSha256: source.contentSha256,
        dimensions: source.dimensions,
      });
    }
    return [...itemById.values()];
  }, [renderDocument?.media, sources]);
  const planKey = JSON.stringify(plan);
  const planRef = useRef(plan);
  planRef.current = plan;

  const [assetUrls, setAssetUrls] = useState<Record<string, string>>({});
  const [assetStates, setAssetStates] = useState<
    Record<string, WxPostDraftMediaState>
  >({});
  const objectUrlsRef = useRef(new Map<string, string>());
  const controllersRef = useRef(new Map<string, AbortController>());
  const requestTokensRef = useRef(new Map<string, symbol>());
  const generationRef = useRef(0);

  const loadMedia = useCallback(
    async (item: MediaPlanItem, generation: number) => {
      controllersRef.current.get(item.id)?.abort();
      const controller = new AbortController();
      const token = Symbol(item.id);
      controllersRef.current.set(item.id, controller);
      requestTokensRef.current.set(item.id, token);
      setAssetStates((current) => ({ ...current, [item.id]: 'loading' }));
      setAssetUrls((current) => ({ ...current, [item.id]: '' }));
      let objectUrl: string | null = null;
      let pendingObjectUrl: string | null = null;
      let timeout = 0;
      try {
        objectUrl = await Promise.race([
          (async () => {
            const blob = await getWorkspaceSourceContent(
              workspaceId,
              item.id,
              item.contentSha256,
              controller.signal
            );
            const createdObjectUrl = URL.createObjectURL(blob);
            pendingObjectUrl = createdObjectUrl;
            if (item.kind === 'image') await decodeImage(createdObjectUrl);
            return createdObjectUrl;
          })(),
          new Promise<never>((_, reject) => {
            timeout = window.setTimeout(() => {
              controller.abort();
              reject(
                new DOMException('Draft media timed out.', 'TimeoutError')
              );
            }, DRAFT_MEDIA_TIMEOUT_MS);
          }),
        ]);
        if (
          generation !== generationRef.current ||
          requestTokensRef.current.get(item.id) !== token
        ) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        const previousUrl = objectUrlsRef.current.get(item.id);
        if (previousUrl) URL.revokeObjectURL(previousUrl);
        const readyObjectUrl = objectUrl;
        objectUrlsRef.current.set(item.id, readyObjectUrl);
        setAssetUrls((current) => ({
          ...current,
          [item.id]: readyObjectUrl,
        }));
        setAssetStates((current) => ({ ...current, [item.id]: 'ready' }));
      } catch {
        const failedObjectUrl = objectUrl ?? pendingObjectUrl;
        if (failedObjectUrl) URL.revokeObjectURL(failedObjectUrl);
        if (
          generation === generationRef.current &&
          requestTokensRef.current.get(item.id) === token
        ) {
          setAssetStates((current) => ({ ...current, [item.id]: 'failed' }));
        }
      } finally {
        window.clearTimeout(timeout);
        if (requestTokensRef.current.get(item.id) === token) {
          controllersRef.current.delete(item.id);
          requestTokensRef.current.delete(item.id);
        }
      }
    },
    [workspaceId]
  );

  useEffect(() => {
    generationRef.current += 1;
    const generation = generationRef.current;
    controllersRef.current.forEach((controller) => controller.abort());
    controllersRef.current.clear();
    objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    objectUrlsRef.current.clear();
    setAssetUrls(Object.fromEntries(planRef.current.map(({ id }) => [id, ''])));
    setAssetStates(
      Object.fromEntries(planRef.current.map(({ id }) => [id, 'loading']))
    );
    planRef.current.forEach((item) => void loadMedia(item, generation));
    return () => {
      generationRef.current += 1;
      controllersRef.current.forEach((controller) => controller.abort());
      controllersRef.current.clear();
      objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      objectUrlsRef.current.clear();
    };
  }, [loadMedia, planKey]);

  const retryMedia = useCallback(
    (mediaId: string) => {
      const item = planRef.current.find(({ id }) => id === mediaId);
      if (item) void loadMedia(item, generationRef.current);
    },
    [loadMedia]
  );

  const assetDimensions = useMemo(
    () =>
      Object.fromEntries(plan.map(({ id, dimensions }) => [id, dimensions])),
    [plan]
  );

  return useMemo(
    () => ({ assetUrls, assetStates, assetDimensions, retryMedia }),
    [assetDimensions, assetStates, assetUrls, retryMedia]
  );
}
