'use client';

import { Loader2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import { WxPostRenderer } from '@/components/wxpost/WxPostRenderer';
import { applyWxPostTextEdit } from '@/components/wxpost/renderer/editing';
import type {
  WxPostArticleDocument,
  WxPostPresentation,
  WxPostPreviewSize,
  WxPostRenderDocument,
} from '@/components/wxpost/types';
import {
  getWorkspaceDraftSession,
  getWorkspaceContext,
  getWorkspaceSourceContent,
  reviseWorkspaceDraft,
  saveWorkspaceDraft,
  validateWorkspaceDraft,
  WorkspaceApiError,
  type WorkspaceContext,
  type WorkspaceDraftSession,
} from '@/utils/wxpostWorkspace';

import { type DraftMode, WxPostDraftControls } from './WxPostDraftControls';
import { WxPostHermesPanel } from './WxPostHermesPanel';
import { WorkspaceConflictDialog } from './WorkspaceConflictDialog';

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

async function hydrateMedia(
  workspaceId: string,
  readyIds: ReadonlySet<string>,
  renderDocument: WxPostRenderDocument
) {
  const objectUrls: string[] = [];
  try {
    const hydrated = await Promise.all(
      renderDocument.media.map(async (media) => {
        if (!media.include) return media;
        if (!readyIds.has(media.id)) return { ...media, sourceUrl: '' };
        const blob = await getWorkspaceSourceContent(workspaceId, media.id);
        const sourceUrl = URL.createObjectURL(blob);
        objectUrls.push(sourceUrl);
        return { ...media, sourceUrl };
      })
    );
    return {
      renderDocument: { ...renderDocument, media: hydrated },
      revoke: () => objectUrls.forEach((url) => URL.revokeObjectURL(url)),
    };
  } catch (error) {
    objectUrls.forEach((url) => URL.revokeObjectURL(url));
    throw error;
  }
}

export function WxPostDraftStage({
  active,
  workspaceId,
  context,
  contextLabel,
  onContextChange,
  onRegenerate,
  regeneratePending,
}: {
  active: boolean;
  workspaceId: string;
  context: WorkspaceContext;
  contextLabel?: string;
  onContextChange: (context: WorkspaceContext) => void;
  onRegenerate: () => Promise<void>;
  regeneratePending: boolean;
}) {
  const savedDraft = context.draft;
  const [document, setDocument] = useState(savedDraft?.document ?? null);
  const [renderDocument, setRenderDocument] =
    useState<WxPostRenderDocument | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [selectedText, setSelectedText] = useState<string | null>(null);
  const [session, setSession] = useState<WorkspaceDraftSession | null>(null);
  const [sessionStatus, setSessionStatus] = useState<
    'connecting' | 'online' | 'unavailable'
  >('connecting');
  const [mode, setMode] = useState<DraftMode>('edit');
  const [previewSize, setPreviewSize] =
    useState<WxPostPreviewSize>('desktop-760');
  const [mobileHermesOpen, setMobileHermesOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [savePending, setSavePending] = useState(false);
  const [chatPending, setChatPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [versionConflict, setVersionConflict] = useState(false);
  const [conflictRefreshPending, setConflictRefreshPending] = useState(false);
  const [conflictRefreshError, setConflictRefreshError] = useState<
    string | null
  >(null);
  const articleRef = useRef<HTMLDivElement>(null);
  const objectUrlsRef = useRef<() => void>(() => {});
  const loadedDraftVersionRef = useRef<number | null>(null);
  const documentRef = useRef<WxPostArticleDocument | null>(
    savedDraft?.document ?? null
  );
  const renderDocumentRef = useRef<WxPostRenderDocument | null>(null);
  const editBaseRef = useRef<{
    key: string;
    document: WxPostArticleDocument;
    renderDocument: WxPostRenderDocument;
  } | null>(null);

  const savedDocumentJson = useMemo(
    () => JSON.stringify(savedDraft?.document ?? null),
    [savedDraft?.document]
  );
  const availableMediaKey = useMemo(
    () =>
      context.manifest.sources
        .filter(
          (source) =>
            source.workspaceReady &&
            (source.kind === 'image' || source.kind === 'video')
        )
        .map((source) => source.id)
        .sort()
        .join('|'),
    [context.manifest.sources]
  );
  const availableMediaIds = useMemo(
    () => new Set(availableMediaKey ? availableMediaKey.split('|') : []),
    [availableMediaKey]
  );
  const dirty =
    document !== null && JSON.stringify(document) !== savedDocumentJson;

  useEffect(() => {
    if (window.matchMedia('(max-width: 1023px)').matches) {
      setPreviewSize('mobile-390');
    }
  }, []);

  useEffect(() => {
    if (mode === 'preview') {
      if (renderDocumentRef.current) {
        setRenderDocument(renderDocumentRef.current);
      }
      editBaseRef.current = null;
      setActiveKey(null);
      setSelectedText(null);
      setMobileHermesOpen(false);
    }
  }, [mode]);

  const loadDocument = useCallback(
    async (nextDocument: WxPostArticleDocument) => {
      const validated = await validateWorkspaceDraft(nextDocument);
      const hydrated = await hydrateMedia(
        workspaceId,
        availableMediaIds,
        validated.renderDocument
      );
      return {
        nextDocument,
        renderDocument: hydrated.renderDocument,
        revoke: hydrated.revoke,
      };
    },
    [availableMediaIds, workspaceId]
  );

  useEffect(() => {
    if (!savedDraft) return;
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
        if (!activeEffect) {
          loaded.revoke();
          return;
        }
        objectUrlsRef.current();
        objectUrlsRef.current = loaded.revoke;
        documentRef.current = loaded.nextDocument;
        renderDocumentRef.current = loaded.renderDocument;
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

  useEffect(
    () => () => {
      objectUrlsRef.current();
    },
    []
  );

  useEffect(() => {
    if (!active || session) return;
    void getWorkspaceDraftSession(workspaceId)
      .then((history) => {
        setSession(history);
        setSessionStatus('online');
      })
      .catch(() => {
        setSession({ workspaceId, sessionId: null, messages: [] });
        setSessionStatus('unavailable');
      });
  }, [active, session, workspaceId]);

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
    if (!base) return;
    const updated = applyWxPostTextEdit(
      base.document,
      base.renderDocument,
      key,
      value
    );
    documentRef.current = updated.document;
    renderDocumentRef.current = updated.renderDocument;
    setDocument(updated.document);
  }, []);

  const finishInlineEdit = useCallback(() => {
    if (renderDocumentRef.current) {
      setRenderDocument(renderDocumentRef.current);
    }
    editBaseRef.current = null;
    setActiveKey(null);
  }, []);

  const updatePresentation = useCallback((presentation: WxPostPresentation) => {
    if (!documentRef.current) return;
    documentRef.current = {
      ...documentRef.current,
      presentation,
    };
    setDocument(documentRef.current);
  }, []);

  const showVersionConflict = useCallback(() => {
    setError(null);
    setConflictRefreshError(null);
    setVersionConflict(true);
  }, []);

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
      objectUrlsRef.current();
      objectUrlsRef.current = loaded.revoke;
      documentRef.current = loaded.nextDocument;
      renderDocumentRef.current = loaded.renderDocument;
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

  const sendMessage = useCallback(async () => {
    const request = message.trim();
    if (!request || !savedDraft || dirty) return;
    setChatPending(true);
    setError(null);
    setSession((current) => ({
      workspaceId,
      sessionId: current?.sessionId ?? null,
      messages: [...(current?.messages ?? []), { role: 'user', text: request }],
    }));
    setMessage('');
    try {
      const result = await reviseWorkspaceDraft(workspaceId, {
        expectedManifestVersion: context.manifest.manifestVersion,
        expectedDraftVersion: savedDraft.draftVersion,
        message: request,
        selectedText,
      });
      onContextChange(result.context);
      setSessionStatus('online');
      setSelectedText(null);
      editBaseRef.current = null;
      setActiveKey(null);
      setSession((current) => ({
        workspaceId,
        sessionId: result.sessionId,
        messages: [
          ...(current?.messages ?? []),
          { role: 'assistant', text: result.reply },
        ],
      }));
    } catch (caught) {
      if (
        caught instanceof WorkspaceApiError &&
        caught.code === 'version_conflict'
      ) {
        setMessage(request);
        setSession((current) =>
          current
            ? { ...current, messages: current.messages.slice(0, -1) }
            : current
        );
        showVersionConflict();
        return;
      }
      if (
        caught instanceof WorkspaceApiError &&
        ['hermes_unavailable', 'hermes_turn_failed'].includes(caught.code ?? '')
      ) {
        setSessionStatus('unavailable');
      }
      const failure = errorMessage(
        caught,
        'Hermes could not revise the draft.'
      );
      setMessage(request);
      setSession((current) =>
        current
          ? { ...current, messages: current.messages.slice(0, -1) }
          : current
      );
      setError(failure);
      toast.error(failure);
    } finally {
      setChatPending(false);
    }
  }, [
    context.manifest.manifestVersion,
    dirty,
    message,
    onContextChange,
    savedDraft,
    selectedText,
    showVersionConflict,
    workspaceId,
  ]);

  const regenerate = useCallback(async () => {
    try {
      await onRegenerate();
    } catch (caught) {
      if (
        caught instanceof WorkspaceApiError &&
        caught.code === 'version_conflict'
      ) {
        showVersionConflict();
      }
      return;
    }
    try {
      setSession(await getWorkspaceDraftSession(workspaceId));
      setSessionStatus('online');
    } catch {
      setSessionStatus('unavailable');
      // The saved Draft remains authoritative if history refresh is unavailable.
    }
  }, [onRegenerate, showVersionConflict, workspaceId]);

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
          Preparing Draft preview and media…
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
        mobileHermesOpen={mobileHermesOpen}
        regeneratePending={regeneratePending}
        chatPending={chatPending}
        savePending={savePending}
        onModeChange={setMode}
        onPresentationChange={updatePresentation}
        onPreviewSizeChange={setPreviewSize}
        onOpenHermes={() => setMobileHermesOpen(true)}
        onRegenerate={() => void regenerate()}
        onSave={() => void save()}
      />

      {error && (
        <p
          className='m-0 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'
          role='alert'
        >
          {error}
        </p>
      )}

      {versionConflict && (
        <WorkspaceConflictDialog
          title='Load latest Draft?'
          error={conflictRefreshError}
          pending={conflictRefreshPending}
          testId='draft-conflict-dialog'
          onKeepCurrent={keepCurrentEdits}
          onLoadLatest={() => void loadLatestDraft()}
        >
          This workspace changed since this page loaded. Loading the latest
          version will discard your unsaved Draft changes. The Draft change you
          just attempted was not applied.
        </WorkspaceConflictDialog>
      )}

      <div
        className={`grid items-start gap-4 ${
          mode === 'edit' ? 'lg:grid-cols-[minmax(0,1fr)_320px]' : 'grid-cols-1'
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
            context={{
              contextLabel,
              publisherName: 'SoarHigh Toastmasters',
            }}
            editor={
              mode === 'edit'
                ? {
                    activeKey,
                    onSelect: selectText,
                    onBlur: finishInlineEdit,
                    onChange: updateText,
                  }
                : undefined
            }
          />
        </div>

        {mode === 'edit' && (
          <aside className='sticky top-4 hidden max-h-[calc(100vh-2rem)] min-h-[34rem] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:block'>
            <WxPostHermesPanel
              mobile={false}
              session={session}
              sessionStatus={sessionStatus}
              chatPending={chatPending}
              selectedText={selectedText}
              message={message}
              dirty={dirty}
              onClose={() => setMobileHermesOpen(false)}
              onClearSelection={() => setSelectedText(null)}
              onMessageChange={setMessage}
              onSend={() => void sendMessage()}
            />
          </aside>
        )}
      </div>

      {mode === 'edit' && mobileHermesOpen && (
        <div
          className='fixed inset-0 z-50 lg:hidden'
          role='dialog'
          aria-modal='true'
          aria-label='Hermes editor'
          data-testid='mobile-hermes-dialog'
        >
          <button
            type='button'
            className='absolute inset-0 bg-slate-950/35'
            aria-label='Dismiss Hermes editor'
            onClick={() => setMobileHermesOpen(false)}
          />
          <div className='absolute inset-x-0 bottom-0 flex max-h-[78dvh] min-h-[32rem] flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-[0_-16px_40px_rgba(15,23,42,0.18)]'>
            <WxPostHermesPanel
              mobile
              session={session}
              sessionStatus={sessionStatus}
              chatPending={chatPending}
              selectedText={selectedText}
              message={message}
              dirty={dirty}
              onClose={() => setMobileHermesOpen(false)}
              onClearSelection={() => setSelectedText(null)}
              onMessageChange={setMessage}
              onSend={() => void sendMessage()}
            />
          </div>
        </div>
      )}
    </section>
  );
}
