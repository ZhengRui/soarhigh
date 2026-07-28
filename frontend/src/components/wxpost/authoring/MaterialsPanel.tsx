'use client';

import {
  Check,
  CloudUpload,
  FileCheck2,
  ImageIcon,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
  Video,
  WandSparkles,
  X,
} from 'lucide-react';
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';

import type { WxPostMaterial } from './types';

const PANEL_CLASS =
  'overflow-hidden rounded-2xl border border-[#d9e1ec] bg-white shadow-sm max-[480px]:rounded-[14px]';
const SECONDARY_BUTTON_CLASS =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-[11px] border border-[#cfd9e6] bg-white px-4 py-[10px] text-sm font-bold text-[#40506a] hover:border-[#9fb1c8] hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 disabled:cursor-not-allowed disabled:border-[#dce3ec] disabled:bg-[#eef2f6] disabled:text-[#96a2b2] [&_svg]:h-[17px] [&_svg]:w-[17px]';

function IconAction({
  label,
  danger = false,
  children,
}: {
  label: string;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type='button'
      className={`grid h-[38px] w-[38px] place-items-center rounded-[10px] border border-[#d2dbe7] bg-white disabled:cursor-not-allowed disabled:opacity-70 [&_svg]:h-[17px] [&_svg]:w-[17px] ${
        danger ? 'text-[#b54b55]' : 'text-[#66758b]'
      }`}
      aria-label={label}
      title={label}
      disabled
    >
      {children}
    </button>
  );
}

function MaterialCard({
  material,
  description,
  onDescriptionChange,
  onPreview,
}: {
  material: WxPostMaterial;
  description: string;
  onDescriptionChange: (value: string) => void;
  onPreview: () => void;
}) {
  const isImage = material.kind === 'image';

  return (
    <article
      className={`min-w-0 overflow-hidden rounded-[14px] border bg-white ${
        material.included ? 'border-[#7da1f2]' : 'border-[#d8e1ed]'
      }`}
      data-testid={`material-${material.sourceKey}`}
    >
      <div className='relative h-[220px] overflow-hidden bg-[#e8edf4] max-[480px]:h-[205px]'>
        {isImage ? (
          <button
            type='button'
            className='group absolute inset-0 block h-full w-full cursor-zoom-in overflow-hidden border-0 bg-[#e8edf4] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600'
            onClick={onPreview}
            aria-label={`Preview ${material.filename}`}
          >
            <Image
              src={material.url}
              alt={description || material.filename}
              fill
              sizes='(max-width: 640px) 100vw, (max-width: 1100px) 50vw, 33vw'
              className='object-cover transition-transform duration-200 group-hover:scale-[1.018]'
              unoptimized
            />
          </button>
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
        <button
          type='button'
          className={`absolute right-[11px] top-[11px] z-[3] grid h-8 w-8 place-items-center rounded-full border text-white shadow-md backdrop-blur-[10px] disabled:cursor-not-allowed disabled:opacity-100 [&_svg]:h-[15px] [&_svg]:w-[15px] ${
            material.workspaceReady
              ? 'border-green-300/80 bg-emerald-50/90 text-[#16834a]'
              : 'border-white/25 bg-slate-900/50'
          }`}
          aria-label={
            material.uploading
              ? `Uploading ${material.filename}`
              : material.workspaceReady
                ? `${material.filename} is available in workspace`
                : `Import ${material.filename} into workspace`
          }
          title={
            material.workspaceReady
              ? 'Available in workspace'
              : 'Import into workspace'
          }
          disabled
          data-testid={`workspace-${material.sourceKey}`}
        >
          {material.uploading ? (
            <Loader2 className='animate-spin' aria-hidden='true' />
          ) : (
            <CloudUpload aria-hidden='true' />
          )}
        </button>
      </div>

      <label className='grid gap-[7px] px-4 pt-[15px] text-sm font-bold text-slate-700 max-[480px]:px-[14px]'>
        <span>Description</span>
        <span className='relative block'>
          <textarea
            value={description}
            onChange={(event) => onDescriptionChange(event.target.value)}
            placeholder='Add a description'
            className='block min-h-[92px] w-full resize-y rounded-[10px] border border-[#cad5e4] bg-white pb-12 pl-3 pr-[54px] pt-[11px] text-[15px] font-normal leading-[1.55] text-[#172033] outline-none placeholder:font-normal placeholder:text-[#93a0b2] hover:border-[#9fb1c8] focus:border-blue-600'
            data-testid={`description-${material.sourceKey}`}
          />
          <button
            type='button'
            className='absolute bottom-3 right-3 grid h-[30px] w-[30px] place-items-center rounded-full border border-[#d5deea] bg-slate-50 text-[#52627a] disabled:cursor-not-allowed disabled:opacity-80 [&_svg]:h-4 [&_svg]:w-4'
            aria-label='Generate description'
            title='Generate description'
            disabled
          >
            <WandSparkles aria-hidden='true' />
          </button>
        </span>
      </label>

      <div className='flex items-center justify-between gap-3 px-4 pb-4 pt-[14px] max-[480px]:px-[14px]'>
        <button
          type='button'
          className={`inline-flex min-h-[38px] items-center gap-2 rounded-[10px] border px-3 py-2 text-[13px] font-bold disabled:cursor-not-allowed disabled:opacity-80 [&_svg]:h-[17px] [&_svg]:w-[17px] ${
            material.included
              ? 'border-[#72d19b] bg-[#eefbf3] text-[#137a43]'
              : 'border-[#cad5e4] bg-white text-[#40506a]'
          }`}
          disabled
          data-testid={`include-${material.sourceKey}`}
        >
          {material.included ? <Check /> : <FileCheck2 />}
          {material.included ? 'Included' : 'Use material'}
        </button>
        <IconAction label='Delete material' danger>
          <Trash2 />
        </IconAction>
      </div>
    </article>
  );
}

export function MaterialsPanel({
  materials,
  isLoading,
  errorMessage,
  onRetry,
  collectionKey,
}: {
  materials: WxPostMaterial[];
  isLoading: boolean;
  errorMessage: string | null;
  onRetry?: () => void;
  collectionKey: string;
}) {
  const [descriptions, setDescriptions] = useState<Record<string, string>>({});
  const [previewMaterial, setPreviewMaterial] = useState<WxPostMaterial | null>(
    null
  );
  const activeCollectionKey = useRef(collectionKey);

  useEffect(() => {
    const collectionChanged = activeCollectionKey.current !== collectionKey;
    activeCollectionKey.current = collectionKey;

    setDescriptions((current) =>
      Object.fromEntries(
        materials.map((material) => [
          material.sourceKey,
          collectionChanged
            ? material.description
            : (current[material.sourceKey] ?? material.description),
        ])
      )
    );
  }, [collectionKey, materials]);

  useEffect(() => {
    if (!previewMaterial) return;

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPreviewMaterial(null);
    };

    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [previewMaterial]);

  return (
    <>
      <section className={PANEL_CLASS} data-testid='materials-panel'>
        <div className='flex min-h-[66px] items-center justify-between gap-[18px] border-b border-[#e4e9f1] px-[22px] py-[18px] max-[480px]:min-h-[60px] max-[480px]:p-4'>
          <h2 className='m-0 text-[19px] font-bold leading-[1.35] tracking-[-0.012em] text-[#172033] max-[480px]:text-lg'>
            Images and video
          </h2>
          <div className='flex items-center gap-3'>
            <span className='text-sm font-semibold text-[#66758b] max-[480px]:hidden'>
              {materials.length} files
            </span>
            <button type='button' className={SECONDARY_BUTTON_CLASS} disabled>
              <Upload aria-hidden='true' />
              Add files
            </button>
          </div>
        </div>

        <div className='p-[22px] max-[480px]:p-4'>
          {errorMessage ? (
            <div className='grid min-h-[180px] place-content-center justify-items-center gap-[10px] rounded-xl border border-dashed border-[#cbd6e4] bg-slate-50 text-[15px] text-[#718096] [&_svg]:h-7 [&_svg]:w-7'>
              <ImageIcon aria-hidden='true' />
              <span>{errorMessage}</span>
              {onRetry && (
                <button
                  type='button'
                  className='mt-1 inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-[#cfd9e6] bg-white px-3 py-2 text-sm font-bold text-[#40506a] hover:border-[#9fb1c8] hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 [&_svg]:h-4 [&_svg]:w-4'
                  onClick={onRetry}
                  data-testid='retry-materials-load'
                >
                  <RefreshCw aria-hidden='true' />
                  Retry
                </button>
              )}
            </div>
          ) : isLoading ? (
            <div className='grid min-h-[180px] place-content-center justify-items-center gap-[10px] rounded-xl border border-dashed border-[#cbd6e4] bg-slate-50 text-[15px] text-[#718096] [&_svg]:h-7 [&_svg]:w-7'>
              <Loader2 className='animate-spin' aria-hidden='true' />
              <span>Loading media…</span>
            </div>
          ) : materials.length > 0 ? (
            <div className='grid grid-cols-2 gap-[18px] max-[760px]:grid-cols-1'>
              {materials.map((material) => (
                <MaterialCard
                  key={material.sourceKey}
                  material={material}
                  description={descriptions[material.sourceKey] || ''}
                  onDescriptionChange={(value) =>
                    setDescriptions((current) => ({
                      ...current,
                      [material.sourceKey]: value,
                    }))
                  }
                  onPreview={() => setPreviewMaterial(material)}
                />
              ))}
            </div>
          ) : (
            <div className='grid min-h-[180px] place-content-center justify-items-center gap-[10px] rounded-xl border border-dashed border-[#cbd6e4] bg-slate-50 text-[15px] text-[#718096] [&_svg]:h-7 [&_svg]:w-7'>
              <ImageIcon aria-hidden='true' />
              <span>No media</span>
            </div>
          )}
        </div>
      </section>

      {previewMaterial && (
        <div
          className='fixed inset-0 z-[80] grid place-items-center bg-[rgb(8_15_28_/_88%)] p-8 max-[480px]:p-4'
          role='dialog'
          aria-modal='true'
          aria-label={`Preview ${previewMaterial.filename}`}
          data-testid='material-lightbox'
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPreviewMaterial(null);
          }}
        >
          <button
            type='button'
            className='absolute right-[22px] top-[22px] grid h-[42px] w-[42px] cursor-pointer place-items-center rounded-full border border-white/25 bg-white/10 text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 [&_svg]:h-[22px] [&_svg]:w-[22px]'
            onClick={() => setPreviewMaterial(null)}
            aria-label='Close image preview'
          >
            <X aria-hidden='true' />
          </button>
          <div className='relative h-[min(72vh,780px)] w-[min(1100px,90vw)]'>
            <Image
              src={previewMaterial.url}
              alt={
                descriptions[previewMaterial.sourceKey] ||
                previewMaterial.filename
              }
              fill
              sizes='90vw'
              className='object-contain'
              unoptimized
            />
          </div>
          <div className='absolute bottom-6 left-8 right-8 flex items-baseline justify-center gap-3 text-center text-sm text-white max-[480px]:bottom-[18px] max-[480px]:left-[18px] max-[480px]:right-[18px] max-[480px]:flex-col max-[480px]:items-center max-[480px]:gap-1'>
            <strong>{previewMaterial.filename}</strong>
            {descriptions[previewMaterial.sourceKey] && (
              <span className='text-slate-300'>
                {descriptions[previewMaterial.sourceKey]}
              </span>
            )}
          </div>
        </div>
      )}
    </>
  );
}
