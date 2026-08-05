'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Check,
  CloudUpload,
  FileCheck2,
  ImageIcon,
  Loader2,
  Upload,
  Video,
  WandSparkles,
  X,
} from 'lucide-react';
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';

import type { WorkspaceDeletePreflight } from '@/utils/wxpostWorkspace';
import {
  WorkspaceApiError,
  getWorkspaceSourceContent,
} from '@/utils/wxpostWorkspace';

import { ResizableTextarea } from './ResizableTextarea';
import { PANEL_CLASS, SECONDARY_BUTTON_CLASS } from './authoringStyles';
import type { WxPostMaterial } from './types';

function PreviewLoadingPlaceholder({ filename }: { filename: string }) {
  return (
    <div
      className='pointer-events-none absolute inset-0 animate-[pulse_2s_ease-in-out_infinite] bg-[#d7dfe9] motion-reduce:animate-none'
      role='status'
      aria-label={`Loading preview for ${filename}`}
      data-testid='material-preview-loading'
    />
  );
}

function MaterialImage({
  workspaceId,
  material,
  description,
}: {
  workspaceId: string;
  material: WxPostMaterial;
  description: string;
}) {
  const [open, setOpen] = useState(false);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loadedSourceUrl, setLoadedSourceUrl] = useState<string | null>(null);
  const [failedSourceUrl, setFailedSourceUrl] = useState<string | null>(null);
  const [imageDimensions, setImageDimensions] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const contentQuery = useQuery({
    queryKey: ['wxpost-source-content', workspaceId, material.sourceId],
    queryFn: () => getWorkspaceSourceContent(workspaceId, material.sourceId),
    enabled:
      material.kind === 'image' &&
      material.workspaceReady &&
      !material.previewUrl,
    staleTime: 0,
  });

  useEffect(() => {
    if (!contentQuery.data) {
      setObjectUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(contentQuery.data);
    setObjectUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [contentQuery.data]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [open]);

  const sourceUrl = material.previewUrl ?? objectUrl;
  const canLoadWorkspaceContent =
    material.kind === 'image' &&
    material.workspaceReady &&
    !material.previewUrl;
  const imageLoaded = Boolean(sourceUrl && loadedSourceUrl === sourceUrl);
  const imageFailed = Boolean(sourceUrl && failedSourceUrl === sourceUrl);
  const workspaceContentLoading =
    canLoadWorkspaceContent &&
    !contentQuery.isError &&
    (contentQuery.isPending ||
      contentQuery.isFetching ||
      (contentQuery.isSuccess && !objectUrl));
  const previewLoading =
    material.previewLoading ||
    workspaceContentLoading ||
    Boolean(sourceUrl && !imageLoaded && !imageFailed);
  const previewUnavailable = !previewLoading && (!sourceUrl || imageFailed);

  return (
    <>
      {sourceUrl && !imageFailed && (
        <button
          type='button'
          className='group absolute inset-0 block h-full w-full cursor-zoom-in overflow-hidden border-0 bg-[#e8edf4] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600'
          onClick={() => setOpen(true)}
          aria-label={`Preview ${material.filename}`}
          disabled={!imageLoaded}
        >
          <Image
            src={sourceUrl}
            alt={description || material.filename}
            fill
            sizes='(max-width: 640px) 100vw, (max-width: 1100px) 50vw, 33vw'
            className={`object-cover transition duration-200 group-hover:scale-[1.018] ${
              imageLoaded ? 'opacity-100' : 'opacity-0'
            }`}
            unoptimized
            onLoad={(event) => {
              setLoadedSourceUrl(sourceUrl);
              setFailedSourceUrl(null);
              setImageDimensions({
                width: event.currentTarget.naturalWidth,
                height: event.currentTarget.naturalHeight,
              });
            }}
            onError={() => {
              setFailedSourceUrl(sourceUrl);
              setLoadedSourceUrl(null);
            }}
          />
        </button>
      )}

      {previewLoading && (
        <PreviewLoadingPlaceholder filename={material.filename} />
      )}

      {previewUnavailable && (
        <div className='grid h-full place-content-center justify-items-center gap-2 p-5 text-center text-[#66758b] [&_svg]:h-8 [&_svg]:w-8'>
          <ImageIcon aria-hidden='true' />
          <small>Preview unavailable</small>
        </div>
      )}

      {open && sourceUrl && (
        <div
          className='fixed inset-0 z-[80] grid place-items-center bg-[rgb(8_15_28_/_88%)] p-8 max-[480px]:p-4'
          role='dialog'
          aria-modal='true'
          aria-label={`Preview ${material.filename}`}
          data-testid='material-lightbox'
          onMouseDown={(event) => {
            if (
              !(event.target instanceof Element) ||
              !event.target.closest('[data-lightbox-image]')
            ) {
              setOpen(false);
            }
          }}
        >
          <button
            type='button'
            className='absolute right-[22px] top-[22px] grid h-[42px] w-[42px] place-items-center rounded-full border border-white/25 bg-white/10 text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 [&_svg]:h-[22px] [&_svg]:w-[22px]'
            onClick={() => setOpen(false)}
            aria-label='Close image preview'
          >
            <X aria-hidden='true' />
          </button>
          {imageDimensions && (
            <Image
              src={sourceUrl}
              alt={description || material.filename}
              width={imageDimensions.width}
              height={imageDimensions.height}
              sizes='90vw'
              className='block h-auto max-h-[72vh] w-auto max-w-[90vw] object-contain'
              unoptimized
              data-lightbox-image
            />
          )}
          <div className='absolute bottom-6 left-8 right-8 flex items-baseline justify-center gap-3 text-center text-sm text-white max-[480px]:bottom-[18px] max-[480px]:left-[18px] max-[480px]:right-[18px] max-[480px]:flex-col max-[480px]:items-center max-[480px]:gap-1'>
            <strong>{material.filename}</strong>
            {description && (
              <span className='text-slate-300'>{description}</span>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function MaterialCard({
  workspaceId,
  material,
  busy,
  importing,
  describing,
  onImport,
  onToggleIncluded,
  onDescriptionChange,
  onGenerateDescription,
  onDeleteRequest,
}: {
  workspaceId: string;
  material: WxPostMaterial;
  busy: boolean;
  importing: boolean;
  describing: boolean;
  onImport: () => Promise<void>;
  onToggleIncluded: () => Promise<void>;
  onDescriptionChange: (description: string) => void;
  onGenerateDescription: () => Promise<void>;
  onDeleteRequest: () => void;
}) {
  return (
    <article
      className={`min-w-0 overflow-hidden rounded-[14px] border bg-white ${
        material.included ? 'border-[#7da1f2]' : 'border-[#d8e1ed]'
      }`}
      data-testid={`material-${material.sourceId}`}
    >
      <div className='relative h-[220px] overflow-hidden bg-[#e8edf4] max-[480px]:h-[185px]'>
        {material.kind === 'image' ? (
          <MaterialImage
            workspaceId={workspaceId}
            material={material}
            description={material.description}
          />
        ) : (
          <div className='grid h-full place-content-center justify-items-center gap-2 bg-gradient-to-br from-[#eef2f7] to-slate-200 p-5 text-center text-[#4d5d75] [&_small]:text-sm [&_svg]:h-[38px] [&_svg]:w-[38px]'>
            <Video aria-hidden='true' />
            <small>Video preview unavailable</small>
          </div>
        )}

        <span
          aria-hidden='true'
          className='pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-[72px] bg-gradient-to-t from-[rgb(8_15_28_/_68%)] to-transparent'
        />
        <span className='absolute left-3 top-3 z-[2] inline-flex items-center rounded-full border border-white/20 bg-slate-900/50 px-[10px] py-[6px] text-xs font-normal text-white shadow-sm backdrop-blur-[10px]'>
          {material.source}
        </span>
        <strong className='absolute bottom-[13px] left-[14px] right-[58px] z-[2] overflow-hidden text-ellipsis whitespace-nowrap text-sm font-normal text-white [text-shadow:0_1px_3px_rgb(0_0_0_/_42%)]'>
          {material.filename}
        </strong>
        {material.workspaceReady && (
          <span className='absolute bottom-[13px] right-[14px] z-[2] font-mono text-xs font-semibold text-white [text-shadow:0_1px_3px_rgb(0_0_0_/_42%)]'>
            {material.sourceId}
          </span>
        )}
        <button
          type='button'
          className={`absolute right-[11px] top-[11px] z-[3] grid h-8 w-8 place-items-center rounded-full shadow-md focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 disabled:cursor-not-allowed disabled:opacity-45 [&_svg]:h-4 [&_svg]:w-4 ${
            material.workspaceReady
              ? 'bg-red-500 text-white hover:bg-red-600'
              : 'border border-white/25 bg-slate-900/50 text-white backdrop-blur-[10px] hover:bg-slate-900/70'
          }`}
          aria-label={
            material.workspaceReady
              ? `Delete ${material.filename} from workspace`
              : `Import ${material.filename} into workspace`
          }
          title={
            material.workspaceReady
              ? 'Delete from workspace'
              : 'Import into workspace'
          }
          disabled={busy || describing}
          onClick={() => {
            if (material.workspaceReady) {
              onDeleteRequest();
              return;
            }
            void onImport().catch(() => undefined);
          }}
          data-testid={`workspace-${material.sourceId}`}
        >
          {importing ? (
            <Loader2 className='animate-spin' aria-hidden='true' />
          ) : material.workspaceReady ? (
            <X aria-hidden='true' />
          ) : (
            <CloudUpload aria-hidden='true' />
          )}
        </button>
      </div>

      <label className='grid gap-[7px] px-4 pt-[15px] text-sm font-bold text-slate-700 max-[480px]:gap-1.5 max-[480px]:px-3 max-[480px]:pt-3'>
        <span>Description</span>
        <span className='relative block'>
          <ResizableTextarea
            rows={1}
            value={material.description}
            disabled={describing}
            onChange={(event) => onDescriptionChange(event.target.value)}
            placeholder='Add a description'
            className='block min-h-[92px] w-full rounded-[10px] border border-[#cad5e4] bg-white pb-12 pl-3 pr-[54px] pt-[11px] text-[15px] font-normal leading-[1.55] text-[#172033] outline-none placeholder:font-normal placeholder:text-[#93a0b2] hover:border-[#9fb1c8] focus:border-blue-600 max-[480px]:min-h-[84px] max-[480px]:pt-2.5 max-[480px]:text-sm'
            data-testid={`description-${material.sourceId}`}
            resizeHandleTestId={`description-${material.sourceId}-resize-handle`}
          />
          <button
            type='button'
            className='absolute bottom-3 right-3 z-[1] grid h-[30px] w-[30px] place-items-center rounded-full border border-[#d5deea] bg-slate-50 text-[#52627a] hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:h-4 [&_svg]:w-4'
            aria-label='Generate description'
            title={
              material.kind !== 'image'
                ? 'Descriptions can only be generated for images.'
                : !material.workspaceReady
                  ? 'Import this image before generating a description.'
                  : 'Generate an English description'
            }
            disabled={
              busy ||
              describing ||
              material.kind !== 'image' ||
              !material.workspaceReady
            }
            onClick={() => void onGenerateDescription()}
            data-testid={`generate-description-${material.sourceId}`}
          >
            {describing ? (
              <Loader2 className='animate-spin' aria-hidden='true' />
            ) : (
              <WandSparkles aria-hidden='true' />
            )}
          </button>
        </span>
      </label>

      <div className='flex items-center gap-3 px-4 pb-4 pt-[14px] max-[480px]:px-3 max-[480px]:pb-3 max-[480px]:pt-3'>
        <button
          type='button'
          className={`inline-flex min-h-[38px] items-center gap-2 rounded-[10px] border px-3 py-2 text-[13px] font-bold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 disabled:cursor-not-allowed disabled:opacity-50 max-[480px]:!h-9 max-[480px]:!min-h-9 max-[480px]:px-2.5 max-[480px]:py-1.5 [&_svg]:h-[17px] [&_svg]:w-[17px] ${
            material.included
              ? 'border-[#7da1f2] bg-[#eef4ff] text-[#2456c7]'
              : 'border-[#cad5e4] bg-white text-[#40506a]'
          }`}
          disabled={busy}
          onClick={() => void onToggleIncluded().catch(() => undefined)}
          data-testid={`include-${material.sourceId}`}
        >
          {material.included ? <Check /> : <FileCheck2 />}
          {material.included ? 'Included' : 'Use material'}
        </button>
      </div>
    </article>
  );
}

export function MaterialsPanel({
  workspaceId,
  materials,
  busy,
  importingSourceId,
  uploading,
  deletingSourceId,
  describingSourceIds,
  onImport,
  onToggleIncluded,
  onDescriptionChange,
  onGenerateDescription,
  onUpload,
  onDeletePreflight,
  onDelete,
  onOpenDraft,
}: {
  workspaceId: string;
  materials: WxPostMaterial[];
  busy: boolean;
  importingSourceId: string | null;
  uploading: boolean;
  deletingSourceId: string | null;
  describingSourceIds: ReadonlySet<string>;
  onImport: (sourceId: string) => Promise<void>;
  onToggleIncluded: (sourceId: string, included: boolean) => Promise<void>;
  onDescriptionChange: (sourceId: string, description: string) => void;
  onGenerateDescription: (sourceId: string) => Promise<void>;
  onUpload: (file: File) => Promise<void>;
  onDeletePreflight: (sourceId: string) => Promise<WorkspaceDeletePreflight>;
  onDelete: (
    sourceId: string,
    preflight: WorkspaceDeletePreflight
  ) => Promise<void>;
  onOpenDraft: () => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [deleteTarget, setDeleteTarget] = useState<WxPostMaterial | null>(null);
  const [preflight, setPreflight] = useState<WorkspaceDeletePreflight | null>(
    null
  );
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [preflightPending, setPreflightPending] = useState(false);

  async function openDeleteDialog(material: WxPostMaterial) {
    setDeleteTarget(material);
    setPreflight(null);
    setDeleteError(null);
    setPreflightPending(true);
    try {
      setPreflight(await onDeletePreflight(material.sourceId));
    } catch (error) {
      if (
        error instanceof WorkspaceApiError &&
        error.code === 'version_conflict'
      ) {
        setDeleteTarget(null);
        return;
      }
      setDeleteError('Could not check whether this material is in the draft.');
    } finally {
      setPreflightPending(false);
    }
  }

  return (
    <>
      <section className={PANEL_CLASS} data-testid='materials-panel'>
        <div className='flex min-h-[66px] items-center justify-between gap-[18px] border-b border-[#e4e9f1] px-[22px] py-[18px] max-[480px]:min-h-[60px] max-[480px]:gap-3 max-[480px]:px-3 max-[480px]:py-2'>
          <h2 className='m-0 text-[19px] font-bold leading-[1.35] tracking-[-0.012em] text-[#172033] max-[480px]:text-base'>
            Images and video
          </h2>
          <div className='flex items-center gap-3'>
            <span className='text-sm font-semibold text-[#66758b] max-[480px]:hidden'>
              {materials.length} files
            </span>
            <input
              ref={fileInput}
              type='file'
              accept='image/*,video/*'
              className='hidden'
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = '';
                if (file) void onUpload(file).catch(() => undefined);
              }}
              data-testid='material-file-input'
            />
            <button
              type='button'
              className={`${SECONDARY_BUTTON_CLASS} max-[480px]:!h-[38px] max-[480px]:!min-h-[38px] max-[480px]:px-3 max-[480px]:py-2`}
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              {uploading ? (
                <Loader2 className='animate-spin' aria-hidden='true' />
              ) : (
                <Upload aria-hidden='true' />
              )}
              Add files
            </button>
          </div>
        </div>

        <div className='p-[22px] max-[480px]:p-3'>
          {materials.length > 0 ? (
            <div className='grid grid-cols-2 items-start gap-[18px] max-[760px]:grid-cols-1 max-[480px]:gap-3'>
              {materials.map((material) => (
                <MaterialCard
                  key={material.sourceId}
                  workspaceId={workspaceId}
                  material={material}
                  busy={busy}
                  importing={importingSourceId === material.sourceId}
                  describing={describingSourceIds.has(material.sourceId)}
                  onImport={() => onImport(material.sourceId)}
                  onToggleIncluded={() =>
                    onToggleIncluded(material.sourceId, !material.included)
                  }
                  onDescriptionChange={(description) =>
                    onDescriptionChange(material.sourceId, description)
                  }
                  onGenerateDescription={() =>
                    onGenerateDescription(material.sourceId)
                  }
                  onDeleteRequest={() => void openDeleteDialog(material)}
                />
              ))}
            </div>
          ) : (
            <div className='grid min-h-[180px] place-content-center justify-items-center gap-[10px] rounded-xl border border-dashed border-[#cbd6e4] bg-slate-50 text-[15px] text-[#718096] max-[480px]:min-h-[140px] max-[480px]:gap-2 max-[480px]:text-sm [&_svg]:h-7 [&_svg]:w-7 max-[480px]:[&_svg]:h-6 max-[480px]:[&_svg]:w-6'>
              <ImageIcon aria-hidden='true' />
              <span>No media</span>
            </div>
          )}
        </div>
      </section>

      {deleteTarget && (
        <div
          className='fixed inset-0 z-[90] grid place-items-center bg-slate-950/55 p-4'
          role='dialog'
          aria-modal='true'
          aria-labelledby='delete-material-title'
          data-testid='delete-material-dialog'
        >
          <div className='w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl'>
            <h2
              id='delete-material-title'
              className='m-0 text-lg font-bold text-slate-900'
            >
              Delete {deleteTarget.filename}?
            </h2>
            <div className='mt-3 text-sm leading-6 text-slate-600'>
              {preflightPending ? (
                <span className='inline-flex items-center gap-2'>
                  <Loader2
                    className='h-4 w-4 animate-spin'
                    aria-hidden='true'
                  />
                  Checking draft references…
                </span>
              ) : deleteError ? (
                <p className='m-0 text-red-700' role='alert'>
                  {deleteError}
                </p>
              ) : preflight?.blockedByDraft ? (
                <>
                  <p className='m-0 font-semibold text-amber-800'>
                    {preflight.references.includes('coverMediaId')
                      ? `This material is the cover of Draft v${preflight.draftVersion}.`
                      : `This material is used by Draft v${preflight.draftVersion}.`}
                  </p>
                  <p className='mb-0 mt-2'>
                    {preflight.references.includes('coverMediaId')
                      ? 'Change or remove the cover. If it also appears in the article, remove it there too. Save the Draft, then return to Materials to delete the file.'
                      : 'Remove it from the Draft and save the Draft first. Then return to Materials to delete the file.'}
                  </p>
                </>
              ) : (
                <p className='m-0'>
                  {deleteTarget.source === 'Meeting Library'
                    ? 'This removes the workspace copy. You can import it again from the meeting library.'
                    : 'This permanently removes the uploaded workspace file.'}
                </p>
              )}
            </div>
            <div className='mt-5 flex justify-end gap-2'>
              <button
                type='button'
                className={SECONDARY_BUTTON_CLASS}
                disabled={busy}
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </button>
              {preflight?.blockedByDraft ? (
                <button
                  type='button'
                  className='inline-flex min-h-11 items-center justify-center rounded-[11px] border border-blue-600 bg-blue-600 px-4 py-[10px] text-sm font-bold text-white hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-800'
                  onClick={() => {
                    setDeleteTarget(null);
                    onOpenDraft();
                  }}
                >
                  Go to Draft
                </button>
              ) : (
                <button
                  type='button'
                  className='inline-flex min-h-11 items-center justify-center gap-2 rounded-[11px] border border-red-700 bg-red-700 px-4 py-[10px] text-sm font-bold text-white hover:bg-red-800 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-red-900 disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-slate-300'
                  disabled={busy || !preflight || Boolean(deleteError)}
                  onClick={() => {
                    if (!preflight) return;
                    void onDelete(deleteTarget.sourceId, preflight)
                      .then(() => setDeleteTarget(null))
                      .catch((error) => {
                        if (
                          error instanceof WorkspaceApiError &&
                          error.code === 'source_referenced_by_draft'
                        ) {
                          void openDeleteDialog(deleteTarget);
                          return;
                        }
                        setDeleteTarget(null);
                      });
                  }}
                >
                  {deletingSourceId === deleteTarget.sourceId && (
                    <Loader2 className='h-4 w-4 animate-spin' />
                  )}
                  Delete
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
