'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import {
  getWorkspaceSourceContent,
  type WorkspaceSource,
} from '@/utils/wxpostWorkspace';

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
  const [loading, setLoading] = useState(false);
  const [previewUrls, setPreviewUrls] = useState<
    Record<string, { contentSha256: string; url: string }>
  >({});
  const objectUrlsRef = useRef(new Map<string, string>());
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
  const draftManagedIds = useMemo(
    () => new Set(Object.keys(draftAssetStates)),
    [draftAssetStates]
  );
  const candidates = useMemo(
    () =>
      coverSources.map((source) => {
        const localPreview = previewUrls[source.id];
        return {
          id: source.id,
          filename: source.filename,
          previewUrl:
            draftAssetUrls[source.id] ||
            (localPreview?.contentSha256 === source.contentSha256
              ? localPreview.url
              : null),
          inArticle: bodyMediaIds.has(source.id),
        };
      }),
    [bodyMediaIds, coverSources, draftAssetUrls, previewUrls]
  );

  useEffect(
    () => () => {
      objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      objectUrlsRef.current.clear();
    },
    []
  );

  useEffect(() => {
    if (!open) return;
    const missing = coverSources.filter(
      (source) =>
        !draftManagedIds.has(source.id) &&
        previewUrls[source.id]?.contentSha256 !== source.contentSha256
    );
    if (missing.length === 0) return;
    let active = true;
    setLoading(true);
    void Promise.allSettled(
      missing.map(async (source) => {
        if (!source.contentSha256) {
          throw new Error(`Source ${source.id} has no content version.`);
        }
        const blob = await getWorkspaceSourceContent(
          workspaceId,
          source.id,
          source.contentSha256
        );
        return [
          source.id,
          source.contentSha256,
          URL.createObjectURL(blob),
        ] as const;
      })
    )
      .then((results) => {
        const entries = results.flatMap((result) =>
          result.status === 'fulfilled' ? [result.value] : []
        );
        if (!active) {
          entries.forEach(([, , url]) => URL.revokeObjectURL(url));
          return;
        }
        entries.forEach(([id, , url]) => {
          const previousUrl = objectUrlsRef.current.get(id);
          if (previousUrl) URL.revokeObjectURL(previousUrl);
          objectUrlsRef.current.set(id, url);
        });
        setPreviewUrls((current) => ({
          ...current,
          ...Object.fromEntries(
            entries.map(([id, contentSha256, url]) => [
              id,
              { contentSha256, url },
            ])
          ),
        }));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [coverSources, draftManagedIds, open, previewUrls, workspaceId]);

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
                previewUrls[source.id]?.contentSha256 === source.contentSha256
                  ? previewUrls[source.id].url
                  : ''
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
    document,
    onApply,
    previewUrls,
    renderDocument,
    selectedCoverId,
    workspaceId,
  ]);

  return {
    open,
    selectedCoverId,
    loading:
      loading ||
      (open &&
        coverSources.some(
          (source) => draftAssetStates[source.id] === 'loading'
        )),
    candidates,
    show,
    close: () => setOpen(false),
    select: setSelectedCoverId,
    apply,
  };
}
