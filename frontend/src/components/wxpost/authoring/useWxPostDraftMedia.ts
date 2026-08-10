'use client';

import { useMemo } from 'react';

import type { WxPostRenderDocument } from '@/components/wxpost/types';
import type { WorkspaceSource } from '@/utils/wxpostWorkspace';

import {
  useWorkspaceMediaResources,
  type WorkspaceMediaResource,
} from './useWorkspaceMediaResources';

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
    const itemById = new Map<string, WorkspaceMediaResource>();
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
  return useWorkspaceMediaResources({ workspaceId, items: plan });
}
