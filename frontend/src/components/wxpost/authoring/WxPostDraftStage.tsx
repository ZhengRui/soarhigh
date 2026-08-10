'use client';

import { Loader2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import { WxPostRenderer } from '@/components/wxpost/WxPostRenderer';
import {
  applyWxPostDirectiveItemDelete,
  applyWxPostMediaDelete,
  applyWxPostTextEdit,
  getWxPostDirectiveItemDeleteDetails,
  WxPostEditValidationError,
  type WxPostMediaDeleteTarget,
} from '@/components/wxpost/renderer/editing';
import type {
  WxPostArticleDocument,
  WxPostPresentation,
  WxPostPreviewSize,
  WxPostRenderDocument,
} from '@/components/wxpost/types';
import {
  getWorkspaceContext,
  saveWorkspaceDraft,
  validateWorkspaceDraft,
  WorkspaceApiError,
  type WorkspaceContext,
} from '@/utils/wxpostWorkspace';

import { WxPostDraftAssistant } from './WxPostDraftAssistant';
import { type DraftMode, WxPostDraftControls } from './WxPostDraftControls';
import { WxPostDraftDialogs } from './WxPostDraftDialogs';
import { WxPostPublicationControls } from './WxPostPublicationControls';
import { useWxPostCoverPicker } from './useWxPostCoverPicker';
import { useWxPostDraftAssistant } from './useWxPostDraftAssistant';
import { useWxPostDraftMedia } from './useWxPostDraftMedia';
import { useWxPostPublication } from './useWxPostPublication';

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function WxPostDraftStage({
  active,
  workspaceId,
  context,
  contextLabel,
  onContextChange,
  initialMode = 'edit',
}: {
  active: boolean;
  workspaceId: string;
  context: WorkspaceContext;
  contextLabel?: string;
  onContextChange: (context: WorkspaceContext) => void;
  initialMode?: DraftMode;
}) {
  const savedDraft = context.draft;
  const [document, setDocument] = useState(savedDraft?.document ?? null);
  const [renderDocument, setRenderDocument] =
    useState<WxPostRenderDocument | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [selectedText, setSelectedText] = useState<string | null>(null);
  const [mode, setMode] = useState<DraftMode>(initialMode);
  const [previewSize, setPreviewSize] =
    useState<WxPostPreviewSize>('desktop-760');
  const [mobileHermesOpen, setMobileHermesOpen] = useState(false);
  const [portalReady, setPortalReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [savePending, setSavePending] = useState(false);
  const [discardConfirming, setDiscardConfirming] = useState(false);
  const [mediaDeleteTarget, setMediaDeleteTarget] =
    useState<WxPostMediaDeleteTarget | null>(null);
  const [directiveItemDeleteTarget, setDirectiveItemDeleteTarget] = useState<{
    key: string;
    label: string;
    removesBlock: boolean;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [versionConflict, setVersionConflict] = useState(false);
  const [conflictKind, setConflictKind] = useState<'draft' | 'publication'>(
    'draft'
  );
  const [conflictRefreshPending, setConflictRefreshPending] = useState(false);
  const [conflictRefreshError, setConflictRefreshError] = useState<
    string | null
  >(null);
  const articleRef = useRef<HTMLDivElement>(null);
  const loadedDraftVersionRef = useRef<number | null>(null);
  const documentRef = useRef<WxPostArticleDocument | null>(
    savedDraft?.document ?? null
  );
  const renderDocumentRef = useRef<WxPostRenderDocument | null>(null);
  const savedRenderDocumentRef = useRef<WxPostRenderDocument | null>(null);
  const editBaseRef = useRef<{
    key: string;
    document: WxPostArticleDocument;
    renderDocument: WxPostRenderDocument;
  } | null>(null);

  const savedDocumentJson = useMemo(
    () => JSON.stringify(savedDraft?.document ?? null),
    [savedDraft?.document]
  );
  const dirty =
    document !== null && JSON.stringify(document) !== savedDocumentJson;

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useEffect(() => {
    if (window.matchMedia('(max-width: 1023px)').matches) {
      setPreviewSize('mobile-390');
    }
  }, []);

  useEffect(() => {
    if (!active || mode === 'preview') {
      if (renderDocumentRef.current) {
        setRenderDocument(renderDocumentRef.current);
      }
      editBaseRef.current = null;
      setActiveKey(null);
      setSelectedText(null);
      setMobileHermesOpen(false);
    }
  }, [active, mode]);

  const loadDocument = useCallback(
    async (nextDocument: WxPostArticleDocument) => {
      const validated = await validateWorkspaceDraft(nextDocument);
      return {
        nextDocument,
        renderDocument: validated.renderDocument,
      };
    },
    []
  );

  useEffect(() => {
    if (!savedDraft) return;
    if (
      loadedDraftVersionRef.current === savedDraft.draftVersion &&
      renderDocumentRef.current
    ) {
      setLoading(false);
      return;
    }
    let activeEffect = true;
    const versionChanged =
      loadedDraftVersionRef.current !== savedDraft.draftVersion;
    const nextDocument =
      versionChanged || !documentRef.current
        ? savedDraft.document
        : documentRef.current;
    if (versionChanged || !renderDocumentRef.current) setLoading(true);
    setError(null);
    void loadDocument(nextDocument)
      .then((loaded) => {
        if (!activeEffect) return;
        documentRef.current = loaded.nextDocument;
        renderDocumentRef.current = loaded.renderDocument;
        savedRenderDocumentRef.current = loaded.renderDocument;
        setDocument(loaded.nextDocument);
        setRenderDocument(loaded.renderDocument);
        loadedDraftVersionRef.current = savedDraft.draftVersion;
      })
      .catch((caught) => {
        if (activeEffect) {
          setError(errorMessage(caught, 'Unable to load this draft.'));
        }
      })
      .finally(() => {
        if (activeEffect) setLoading(false);
      });
    return () => {
      activeEffect = false;
    };
  }, [loadDocument, savedDraft]);

  const selectText = useCallback((key: string) => {
    const currentDocument = documentRef.current;
    const currentRender = renderDocumentRef.current;
    if (!currentDocument || !currentRender) return;
    if (editBaseRef.current?.key !== key) {
      editBaseRef.current = {
        key,
        document: currentDocument,
        renderDocument: currentRender,
      };
    }
    setActiveKey(key);
  }, []);

  const updateText = useCallback((key: string, value: string) => {
    const base =
      editBaseRef.current?.key === key
        ? editBaseRef.current
        : documentRef.current && renderDocumentRef.current
          ? {
              key,
              document: documentRef.current,
              renderDocument: renderDocumentRef.current,
            }
          : null;
    if (!base) return null;
    try {
      const updated = applyWxPostTextEdit(
        base.document,
        base.renderDocument,
        key,
        value
      );
      documentRef.current = updated.document;
      renderDocumentRef.current = updated.renderDocument;
      setDocument(updated.document);
      return null;
    } catch (caught) {
      if (caught instanceof WxPostEditValidationError) {
        toast.error(caught.message, { id: 'wxpost-required-field' });
        return caught.message;
      }
      throw caught;
    }
  }, []);

  const finishInlineEdit = useCallback(() => {
    if (renderDocumentRef.current) {
      setRenderDocument(renderDocumentRef.current);
    }
    editBaseRef.current = null;
    setActiveKey(null);
  }, []);

  const confirmMediaDelete = useCallback(() => {
    if (!mediaDeleteTarget) return;
    const currentDocument = documentRef.current;
    const currentRender = renderDocumentRef.current;
    if (!currentDocument || !currentRender) return;
    try {
      const updated = applyWxPostMediaDelete(
        currentDocument,
        currentRender,
        mediaDeleteTarget
      );
      documentRef.current = updated.document;
      renderDocumentRef.current = updated.renderDocument;
      editBaseRef.current = null;
      setActiveKey(null);
      setSelectedText(null);
      setDocument(updated.document);
      setRenderDocument(updated.renderDocument);
      setMediaDeleteTarget(null);
    } catch (caught) {
      toast.error(errorMessage(caught, 'Unable to remove this media.'));
    }
  }, [mediaDeleteTarget]);

  const requestDirectiveItemDelete = useCallback((key: string) => {
    const currentRender = renderDocumentRef.current;
    if (!currentRender) return;
    try {
      setDirectiveItemDeleteTarget({
        key,
        ...getWxPostDirectiveItemDeleteDetails(currentRender, key),
      });
    } catch (caught) {
      toast.error(errorMessage(caught, 'Unable to select this item.'));
    }
  }, []);

  const confirmDirectiveItemDelete = useCallback(() => {
    if (!directiveItemDeleteTarget) return;
    const currentDocument = documentRef.current;
    const currentRender = renderDocumentRef.current;
    if (!currentDocument || !currentRender) return;
    try {
      const updated = applyWxPostDirectiveItemDelete(
        currentDocument,
        currentRender,
        directiveItemDeleteTarget.key
      );
      documentRef.current = updated.document;
      renderDocumentRef.current = updated.renderDocument;
      editBaseRef.current = null;
      setActiveKey(null);
      setSelectedText(null);
      setDocument(updated.document);
      setRenderDocument(updated.renderDocument);
      setDirectiveItemDeleteTarget(null);
    } catch (caught) {
      toast.error(errorMessage(caught, 'Unable to delete this item.'));
    }
  }, [directiveItemDeleteTarget]);

  const updatePresentation = useCallback((presentation: WxPostPresentation) => {
    if (!documentRef.current) return;
    documentRef.current = {
      ...documentRef.current,
      presentation,
    };
    setDocument(documentRef.current);
  }, []);

  const showVersionConflict = useCallback(
    (kind: 'draft' | 'publication' = 'draft') => {
      setConflictKind(kind);
      setError(null);
      setConflictRefreshError(null);
      setVersionConflict(true);
    },
    []
  );

  const applyCoverUpdate = useCallback(
    (
      nextDocument: WxPostArticleDocument,
      nextRenderDocument: WxPostRenderDocument
    ) => {
      documentRef.current = nextDocument;
      renderDocumentRef.current = nextRenderDocument;
      editBaseRef.current = null;
      setActiveKey(null);
      setSelectedText(null);
      setDocument(nextDocument);
      setRenderDocument(nextRenderDocument);
    },
    []
  );
  const draftMedia = useWxPostDraftMedia({
    workspaceId,
    renderDocument,
    sources: context.manifest.sources,
  });
  const coverPicker = useWxPostCoverPicker({
    workspaceId,
    sources: context.manifest.sources,
    document,
    renderDocument,
    draftAssetUrls: draftMedia.assetUrls,
    draftAssetStates: draftMedia.assetStates,
    onApply: applyCoverUpdate,
  });
  const publication = useWxPostPublication({
    active,
    workspaceId,
    manifestVersion: context.manifest.manifestVersion,
    savedDraft,
    dirty,
    onConflict: () => showVersionConflict('publication'),
  });
  const applyAssistantDraft = useCallback(
    async (nextContext: WorkspaceContext) => {
      const nextDraft = nextContext.draft;
      if (!nextDraft) {
        throw new Error('The Draft Assistant did not return a saved Draft.');
      }
      const loaded = await loadDocument(nextDraft.document).catch((caught) => {
        // Keep the authoritative version in sync even when its preview cannot
        // be prepared. The normal version effect will surface the load error.
        onContextChange(nextContext);
        throw caught;
      });
      documentRef.current = loaded.nextDocument;
      renderDocumentRef.current = loaded.renderDocument;
      savedRenderDocumentRef.current = loaded.renderDocument;
      loadedDraftVersionRef.current = nextDraft.draftVersion;
      editBaseRef.current = null;
      setActiveKey(null);
      setSelectedText(null);
      setDocument(loaded.nextDocument);
      setRenderDocument(loaded.renderDocument);
      setError(null);
      onContextChange(nextContext);
    },
    [loadDocument, onContextChange]
  );
  const assistant = useWxPostDraftAssistant({
    active,
    workspaceId,
    manifestVersion: context.manifest.manifestVersion,
    savedDraft,
    dirty,
    selectedText,
    onDraftChanged: applyAssistantDraft,
    onConflict: () => showVersionConflict(),
    onError: setError,
  });

  const keepCurrentEdits = useCallback(() => {
    setVersionConflict(false);
    setConflictRefreshError(null);
  }, []);

  const loadLatestDraft = useCallback(async () => {
    setConflictRefreshPending(true);
    setConflictRefreshError(null);
    try {
      const latest = await getWorkspaceContext(workspaceId);
      if (!latest.draft) {
        throw new Error('The latest workspace no longer contains a Draft.');
      }
      const loaded = await loadDocument(latest.draft.document);
      documentRef.current = loaded.nextDocument;
      renderDocumentRef.current = loaded.renderDocument;
      savedRenderDocumentRef.current = loaded.renderDocument;
      loadedDraftVersionRef.current = latest.draft.draftVersion;
      editBaseRef.current = null;
      setActiveKey(null);
      setSelectedText(null);
      setDocument(loaded.nextDocument);
      setRenderDocument(loaded.renderDocument);
      setError(null);
      onContextChange(latest);
      setVersionConflict(false);
    } catch {
      setConflictRefreshError(
        'The latest Draft could not be loaded. Your current edits are still here.'
      );
    } finally {
      setConflictRefreshPending(false);
    }
  }, [loadDocument, onContextChange, workspaceId]);

  const save = useCallback(async () => {
    const workingDocument = documentRef.current;
    if (!workingDocument || !savedDraft || !dirty) return;
    setSavePending(true);
    setError(null);
    try {
      const updated = await saveWorkspaceDraft(workspaceId, {
        expectedManifestVersion: context.manifest.manifestVersion,
        expectedDraftVersion: savedDraft.draftVersion,
        document: workingDocument,
      });
      if (!updated.draft) {
        throw new Error('The saved workspace did not return a Draft.');
      }
      loadedDraftVersionRef.current = updated.draft.draftVersion;
      savedRenderDocumentRef.current = renderDocumentRef.current;
      documentRef.current = updated.draft.document;
      setDocument(updated.draft.document);
      onContextChange(updated);
      editBaseRef.current = null;
      setActiveKey(null);
      toast.success('Draft saved successfully!');
    } catch (caught) {
      if (
        caught instanceof WorkspaceApiError &&
        caught.code === 'version_conflict'
      ) {
        showVersionConflict();
        return;
      }
      const message = errorMessage(caught, 'Unable to save this draft.');
      setError(message);
      toast.error(message);
    } finally {
      setSavePending(false);
    }
  }, [
    context.manifest.manifestVersion,
    dirty,
    onContextChange,
    savedDraft,
    showVersionConflict,
    workspaceId,
  ]);

  const discardChanges = useCallback(() => {
    const savedRenderDocument = savedRenderDocumentRef.current;
    if (!savedDraft || !savedRenderDocument || !dirty) return;
    setError(null);
    documentRef.current = savedDraft.document;
    renderDocumentRef.current = savedRenderDocument;
    editBaseRef.current = null;
    setActiveKey(null);
    setSelectedText(null);
    setDocument(savedDraft.document);
    setRenderDocument(savedRenderDocument);
    setDiscardConfirming(false);
  }, [dirty, savedDraft]);

  const renderContext = useMemo(
    () => ({
      contextLabel,
      publisherName: 'SoarHigh Toastmasters',
      assetUrls: draftMedia.assetUrls,
      assetStates: draftMedia.assetStates,
      assetDimensions: draftMedia.assetDimensions,
    }),
    [contextLabel, draftMedia]
  );

  if (!savedDraft || !document) return null;
  const savedVersionPending =
    loadedDraftVersionRef.current !== savedDraft.draftVersion;
  if (error && savedVersionPending && !loading) {
    return (
      <p
        className='rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700'
        role='alert'
      >
        {error}
      </p>
    );
  }
  if (loading || savedVersionPending) {
    return (
      <div
        className='grid min-h-[50vh] place-content-center justify-items-center gap-3 text-center'
        role='status'
      >
        <Loader2
          className='h-8 w-8 animate-spin text-blue-500'
          aria-hidden='true'
        />
        <span className='text-sm font-medium text-slate-500'>
          Preparing Draft preview…
        </span>
      </div>
    );
  }
  if (!renderDocument) {
    return (
      <p
        className='rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700'
        role='alert'
      >
        {error ?? 'Unable to render this Draft.'}
      </p>
    );
  }

  return (
    <section className='grid gap-4' data-testid='draft-workbench'>
      <WxPostDraftControls
        draftVersion={savedDraft.draftVersion}
        dirty={dirty}
        mode={mode}
        presentation={document.presentation}
        previewSize={previewSize}
        coverMediaId={document.coverMediaId ?? null}
        chatPending={assistant.pending}
        savePending={savePending}
        onModeChange={setMode}
        onPresentationChange={updatePresentation}
        onPreviewSizeChange={setPreviewSize}
        onOpenCoverPicker={coverPicker.show}
        onDiscard={() => setDiscardConfirming(true)}
        onSave={() => void save()}
      />

      <div className='-mt-4 rounded-b-xl border border-t-0 border-slate-200 bg-white px-3 pb-3 shadow-sm sm:px-4'>
        <WxPostPublicationControls
          status={publication.status}
          loading={publication.loading}
          loadError={publication.loadError}
          dirty={dirty}
          pending={publication.pending}
          currentDraftVersion={savedDraft.draftVersion}
          onSync={publication.sync}
        />
      </div>

      {error && (
        <p
          className='m-0 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'
          role='alert'
        >
          {error}
        </p>
      )}

      <WxPostDraftDialogs
        conflict={{
          open: versionConflict,
          kind: conflictKind,
          error: conflictRefreshError,
          pending: conflictRefreshPending,
          onKeep: keepCurrentEdits,
          onLoadLatest: () => void loadLatestDraft(),
        }}
        discard={{
          open: discardConfirming,
          onKeep: () => setDiscardConfirming(false),
          onConfirm: discardChanges,
        }}
        coverPicker={{
          open: coverPicker.open,
          candidates: coverPicker.candidates,
          currentCoverId: document.coverMediaId ?? null,
          selectedCoverId: coverPicker.selectedCoverId,
          loading: coverPicker.loading,
          onSelect: coverPicker.select,
          onClose: coverPicker.close,
          onApply: coverPicker.apply,
        }}
        mediaDelete={{
          target: mediaDeleteTarget,
          coverMediaId: document.coverMediaId,
          onCancel: () => setMediaDeleteTarget(null),
          onConfirm: confirmMediaDelete,
        }}
        directiveDelete={{
          target: directiveItemDeleteTarget,
          onCancel: () => setDirectiveItemDeleteTarget(null),
          onConfirm: confirmDirectiveItemDelete,
        }}
      />

      <div
        className={`grid items-start gap-4 ${
          mode === 'edit'
            ? 'lg:grid-cols-[minmax(0,1fr)_minmax(360px,32%)]'
            : 'grid-cols-1'
        }`}
      >
        <div
          ref={articleRef}
          className='min-w-0 overflow-auto rounded-xl border border-slate-200 bg-slate-200/50 p-2.5 sm:p-5'
          onMouseUp={() => {
            if (mode !== 'edit') return;
            const selection = window.getSelection();
            if (
              selection &&
              !selection.isCollapsed &&
              articleRef.current?.contains(selection.anchorNode) &&
              articleRef.current.contains(selection.focusNode)
            ) {
              setSelectedText(selection.toString().trim() || null);
            }
          }}
        >
          <WxPostRenderer
            article={renderDocument}
            presentation={document.presentation}
            previewSize={previewSize}
            context={renderContext}
            onRetryMedia={draftMedia.retryMedia}
            editor={
              mode === 'edit'
                ? {
                    activeKey,
                    onSelect: selectText,
                    onBlur: finishInlineEdit,
                    onChange: updateText,
                    onDeleteMedia: setMediaDeleteTarget,
                    onDeleteDirectiveItem: requestDirectiveItemDelete,
                  }
                : undefined
            }
          />
        </div>

        <WxPostDraftAssistant
          active={active}
          mode={mode}
          portalReady={portalReady}
          mobileOpen={mobileHermesOpen}
          conversation={assistant.conversation}
          assistantStatus={assistant.status}
          chatPending={assistant.pending}
          resetPending={assistant.resetPending}
          progress={assistant.progress}
          selectedText={selectedText}
          message={assistant.message}
          dirty={dirty}
          onMobileOpenChange={setMobileHermesOpen}
          onClearSelection={() => setSelectedText(null)}
          onMessageChange={assistant.setMessage}
          onSend={() => void assistant.send()}
          onReset={assistant.reset}
        />
      </div>
    </section>
  );
}
