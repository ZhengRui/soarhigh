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
  onApply,
}: {
  workspaceId: string;
  sources: WorkspaceSource[];
  document: WxPostArticleDocument | null;
  renderDocument: WxPostRenderDocument | null;
  onApply: (
    document: WxPostArticleDocument,
    renderDocument: WxPostRenderDocument
  ) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selectedCoverId, setSelectedCoverId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const objectUrlsRef = useRef<string[]>([]);
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
  const candidates = useMemo(
    () =>
      coverSources.map((source) => {
        const draftMedia = renderDocument?.media.find(
          (media) => media.id === source.id
        );
        return {
          id: source.id,
          filename: source.filename,
          previewUrl: draftMedia?.sourceUrl || previewUrls[source.id] || null,
          inArticle: bodyMediaIds.has(source.id),
        };
      }),
    [bodyMediaIds, coverSources, previewUrls, renderDocument?.media]
  );

  useEffect(
    () => () => {
      objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    },
    []
  );

  useEffect(() => {
    if (!open) return;
    const loadedIds = new Set([
      ...Object.keys(previewUrls),
      ...(renderDocument?.media
        .filter((media) => media.sourceUrl)
        .map((media) => media.id) ?? []),
    ]);
    const missing = coverSources.filter((source) => !loadedIds.has(source.id));
    if (missing.length === 0) return;
    let active = true;
    setLoading(true);
    void Promise.allSettled(
      missing.map(async (source) => {
        const blob = await getWorkspaceSourceContent(workspaceId, source.id);
        return [source.id, URL.createObjectURL(blob)] as const;
      })
    )
      .then((results) => {
        const entries = results.flatMap((result) =>
          result.status === 'fulfilled' ? [result.value] : []
        );
        if (!active) {
          entries.forEach(([, url]) => URL.revokeObjectURL(url));
          return;
        }
        objectUrlsRef.current.push(...entries.map(([, url]) => url));
        setPreviewUrls((current) => ({
          ...current,
          ...Object.fromEntries(entries),
        }));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [coverSources, open, previewUrls, renderDocument?.media, workspaceId]);

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
                previewUrls[source.id] ?? ''
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
    loading,
    candidates,
    show,
    close: () => setOpen(false),
    select: setSelectedCoverId,
    apply,
  };
}
