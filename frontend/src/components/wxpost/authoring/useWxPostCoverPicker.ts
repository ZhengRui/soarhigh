'use client';

import { useCallback, useMemo, useState } from 'react';
import toast from 'react-hot-toast';

import {
  applyWxPostCoverChange,
  wxPostBodyMediaIds,
} from '@/components/wxpost/renderer/editing';
import type {
  WxPostArticleDocument,
  WxPostMediaAsset,
  WxPostRenderDocument,
} from '@/components/wxpost/types';
import type { WorkspaceSource } from '@/utils/wxpostWorkspace';

import { useWorkspaceMediaResources } from './useWorkspaceMediaResources';

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function coverMediaFromSource(
  source: WorkspaceSource & { kind: 'image' },
  sourceUrl: string
): WxPostMediaAsset {
  const hasDescription = Boolean(source.description.trim());
  return {
    id: source.id,
    kind: 'image',
    sourceUrl,
    description: hasDescription ? source.description : source.filename,
    include: true,
    order: 0,
    descriptionSource:
      hasDescription && source.descriptionSource === 'ai' ? 'ai' : 'user',
    descriptionStatus:
      hasDescription && source.descriptionStatus === 'needs_confirmation'
        ? 'needs_confirmation'
        : 'confirmed',
  };
}

export function useWxPostCoverPicker({
  workspaceId,
  sources,
  document,
  renderDocument,
  draftAssetUrls,
  draftAssetStates,
  onApply,
}: {
  workspaceId: string;
  sources: WorkspaceSource[];
  document: WxPostArticleDocument | null;
  renderDocument: WxPostRenderDocument | null;
  draftAssetUrls: Record<string, string>;
  draftAssetStates: Record<string, 'loading' | 'ready' | 'failed'>;
  onApply: (
    document: WxPostArticleDocument,
    renderDocument: WxPostRenderDocument
  ) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selectedCoverId, setSelectedCoverId] = useState<string | null>(null);
  const coverSources = useMemo(
    () =>
      sources.filter(
        (source): source is WorkspaceSource & { kind: 'image' } =>
          source.workspaceReady && source.kind === 'image'
      ),
    [sources]
  );
  const bodyMediaIds = useMemo(
    () =>
      renderDocument ? wxPostBodyMediaIds(renderDocument) : new Set<string>(),
    [renderDocument]
  );
  const draftManagedKey = Object.keys(draftAssetStates).sort().join('|');
  const draftManagedIds = useMemo(
    () => new Set(draftManagedKey ? draftManagedKey.split('|') : []),
    [draftManagedKey]
  );
  const coverOnlyResources = useMemo(
    () =>
      coverSources.flatMap((source) =>
        !draftManagedIds.has(source.id) && source.contentSha256
          ? [
              {
                id: source.id,
                kind: 'image' as const,
                contentSha256: source.contentSha256,
                dimensions: source.dimensions,
              },
            ]
          : []
      ),
    [coverSources, draftManagedIds]
  );
  const coverResources = useWorkspaceMediaResources({
    workspaceId,
    items: coverOnlyResources,
    enabled: open,
  });
  const candidates = useMemo(
    () =>
      coverSources.map((source) => {
        return {
          id: source.id,
          filename: source.filename,
          previewUrl:
            draftAssetUrls[source.id] ||
            coverResources.assetUrls[source.id] ||
            null,
          inArticle: bodyMediaIds.has(source.id),
        };
      }),
    [bodyMediaIds, coverResources.assetUrls, coverSources, draftAssetUrls]
  );

  const show = useCallback(() => {
    setSelectedCoverId(document?.coverMediaId ?? null);
    setOpen(true);
  }, [document?.coverMediaId]);

  const apply = useCallback(() => {
    if (!document || !renderDocument) return;
    try {
      const existing = selectedCoverId
        ? document.media.some((media) => media.id === selectedCoverId)
        : true;
      const source = selectedCoverId
        ? coverSources.find((candidate) => candidate.id === selectedCoverId)
        : null;
      if (!existing && !source) {
        throw new Error('The selected cover image is no longer available.');
      }
      const newCover =
        !existing && source
          ? {
              documentMedia: coverMediaFromSource(
                source,
                `https://workspace.invalid/${encodeURIComponent(workspaceId)}/materials/${source.id}`
              ),
              renderMedia: coverMediaFromSource(
                source,
                draftAssetUrls[source.id] ||
                  coverResources.assetUrls[source.id] ||
                  ''
              ),
            }
          : undefined;
      const updated = applyWxPostCoverChange(
        document,
        renderDocument,
        selectedCoverId,
        newCover
      );
      onApply(updated.document, updated.renderDocument);
      setOpen(false);
    } catch (caught) {
      toast.error(errorMessage(caught, 'Unable to change the Draft cover.'));
    }
  }, [
    coverSources,
    coverResources.assetUrls,
    draftAssetUrls,
    document,
    onApply,
    renderDocument,
    selectedCoverId,
    workspaceId,
  ]);

  return {
    open,
    selectedCoverId,
    loading:
      open &&
      coverSources.some(
        (source) =>
          draftAssetStates[source.id] === 'loading' ||
          coverResources.assetStates[source.id] === 'loading'
      ),
    candidates,
    show,
    close: () => setOpen(false),
    select: setSelectedCoverId,
    apply,
  };
}
