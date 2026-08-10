'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { getWorkspaceSourceContent } from '@/utils/wxpostWorkspace';

const WORKSPACE_MEDIA_TIMEOUT_MS = 15_000;

type WorkspaceMediaResourceState = 'loading' | 'ready' | 'failed';

export type WorkspaceMediaResource = {
  id: string;
  kind: 'image' | 'video';
  contentSha256: string;
  dimensions: { width: number; height: number } | null;
};

type ResourceEntry = {
  item: WorkspaceMediaResource;
  key: string;
  state?: WorkspaceMediaResourceState;
  url?: string;
  controller?: AbortController;
  token?: symbol;
};

function resourceKey(workspaceId: string, item: WorkspaceMediaResource) {
  return JSON.stringify([
    workspaceId,
    item.id,
    item.kind,
    item.contentSha256,
    item.dimensions,
  ]);
}

function abortReason(signal: AbortSignal) {
  return signal.reason instanceof Error
    ? signal.reason
    : new DOMException('Workspace media loading was aborted.', 'AbortError');
}

function decodeImage(url: string, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const image = new Image();
    let settled = false;
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      signal.removeEventListener('abort', onAbort);
      callback();
    };
    const onAbort = () => finish(() => reject(abortReason(signal)));
    if (signal.aborted) {
      onAbort();
      return;
    }
    signal.addEventListener('abort', onAbort, { once: true });
    image.src = url;
    void image.decode().then(
      () => finish(resolve),
      (error: unknown) => finish(() => reject(error))
    );
  });
}

function cancelEntry(entry: ResourceEntry) {
  entry.controller?.abort();
  entry.controller = undefined;
  entry.token = undefined;
}

function disposeEntry(entry: ResourceEntry) {
  cancelEntry(entry);
  if (entry.url) URL.revokeObjectURL(entry.url);
  entry.url = undefined;
  entry.state = undefined;
}

export function useWorkspaceMediaResources({
  workspaceId,
  items,
  enabled = true,
}: {
  workspaceId: string;
  items: WorkspaceMediaResource[];
  enabled?: boolean;
}) {
  const entriesRef = useRef(new Map<string, ResourceEntry>());
  const enabledRef = useRef(false);
  const [, setRevision] = useState(0);
  const publish = useCallback(() => {
    setRevision((current) => current + 1);
  }, []);

  const loadResource = useCallback(
    async (entry: ResourceEntry) => {
      cancelEntry(entry);
      if (entry.url) URL.revokeObjectURL(entry.url);
      entry.url = undefined;
      entry.state = 'loading';
      const controller = new AbortController();
      const token = Symbol(entry.item.id);
      entry.controller = controller;
      entry.token = token;
      publish();

      let objectUrl: string | null = null;
      let timeout = 0;
      try {
        const blob = await Promise.race([
          getWorkspaceSourceContent(
            workspaceId,
            entry.item.id,
            entry.item.contentSha256,
            controller.signal
          ),
          new Promise<never>((_, reject) => {
            timeout = window.setTimeout(() => {
              controller.abort();
              reject(
                new DOMException('Workspace media timed out.', 'TimeoutError')
              );
            }, WORKSPACE_MEDIA_TIMEOUT_MS);
          }),
        ]);
        if (controller.signal.aborted) throw abortReason(controller.signal);
        objectUrl = URL.createObjectURL(blob);
        if (entry.item.kind === 'image') {
          await decodeImage(objectUrl, controller.signal);
        }
        if (
          entriesRef.current.get(entry.item.id) !== entry ||
          entry.token !== token
        ) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        entry.url = objectUrl;
        entry.state = 'ready';
        objectUrl = null;
        publish();
      } catch {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        if (
          entriesRef.current.get(entry.item.id) === entry &&
          entry.token === token
        ) {
          entry.state = 'failed';
          publish();
        }
      } finally {
        window.clearTimeout(timeout);
        if (entry.token === token) {
          entry.controller = undefined;
          entry.token = undefined;
        }
      }
    },
    [publish, workspaceId]
  );

  useEffect(() => {
    const becameEnabled = enabled && !enabledRef.current;
    enabledRef.current = enabled;
    const desired = new Map(
      items.map((item) => [
        item.id,
        { item, key: resourceKey(workspaceId, item) },
      ])
    );
    let changed = false;
    for (const [id, entry] of entriesRef.current) {
      if (desired.get(id)?.key !== entry.key) {
        disposeEntry(entry);
        entriesRef.current.delete(id);
        changed = true;
      }
    }

    const pending: ResourceEntry[] = [];
    for (const { item, key } of desired.values()) {
      let entry = entriesRef.current.get(item.id);
      if (!entry) {
        entry = { item, key };
        entriesRef.current.set(item.id, entry);
        changed = true;
      }
      if (
        enabled &&
        (!entry.state || (entry.state === 'failed' && becameEnabled))
      ) {
        pending.push(entry);
      } else if (!enabled && entry.state === 'loading') {
        cancelEntry(entry);
        entry.state = undefined;
        changed = true;
      }
    }
    if (changed) publish();
    pending.forEach((entry) => void loadResource(entry));
  }, [enabled, items, loadResource, publish, workspaceId]);

  useEffect(() => {
    const entries = entriesRef.current;
    return () => {
      entries.forEach(disposeEntry);
      entries.clear();
    };
  }, []);

  const retryMedia = useCallback(
    (mediaId: string) => {
      const entry = entriesRef.current.get(mediaId);
      if (entry && enabledRef.current) void loadResource(entry);
    },
    [loadResource]
  );

  const assetUrls: Record<string, string> = {};
  const assetStates: Record<string, WorkspaceMediaResourceState> = {};
  const assetDimensions: Record<
    string,
    { width: number; height: number } | null
  > = {};
  for (const item of items) {
    const entry = entriesRef.current.get(item.id);
    const current = entry?.key === resourceKey(workspaceId, item);
    if (current && entry.url) assetUrls[item.id] = entry.url;
    if (current && entry.state) {
      assetStates[item.id] = entry.state;
    } else if (enabled) {
      assetStates[item.id] = 'loading';
    }
    assetDimensions[item.id] = item.dimensions;
  }
  return { assetUrls, assetStates, assetDimensions, retryMedia };
}
