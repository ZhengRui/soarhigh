'use client';

import type { ComponentProps } from 'react';

import type { WxPostArticleDocument } from '@/components/wxpost/types';
import type { WxPostMediaDeleteTarget } from '@/components/wxpost/renderer/editing';

import { WxPostCoverPicker } from './WxPostCoverPicker';
import { WorkspaceConflictDialog } from './WorkspaceConflictDialog';

const DESTRUCTIVE_BUTTON_CLASS =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-[11px] border border-red-700 bg-red-700 px-4 py-[10px] text-sm font-bold text-white hover:bg-red-800 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-red-900';

type DirectiveDeleteTarget = {
  key: string;
  label: string;
  removesBlock: boolean;
};

export function WxPostDraftDialogs({
  conflict,
  discard,
  coverPicker,
  mediaDelete,
  directiveDelete,
}: {
  conflict: {
    open: boolean;
    kind: 'draft' | 'publication';
    error: string | null;
    pending: boolean;
    onKeep: () => void;
    onLoadLatest: () => void;
  };
  discard: {
    open: boolean;
    onKeep: () => void;
    onConfirm: () => void;
  };
  coverPicker: ComponentProps<typeof WxPostCoverPicker> & { open: boolean };
  mediaDelete: {
    target: WxPostMediaDeleteTarget | null;
    coverMediaId: WxPostArticleDocument['coverMediaId'];
    onCancel: () => void;
    onConfirm: () => void;
  };
  directiveDelete: {
    target: DirectiveDeleteTarget | null;
    onCancel: () => void;
    onConfirm: () => void;
  };
}) {
  const { open: coverPickerOpen, ...coverPickerProps } = coverPicker;
  return (
    <>
      {conflict.open && (
        <WorkspaceConflictDialog
          title={
            conflict.kind === 'publication'
              ? 'Load latest Draft and public status?'
              : 'Load latest Draft?'
          }
          error={conflict.error}
          pending={conflict.pending}
          testId='draft-conflict-dialog'
          onKeepCurrent={conflict.onKeep}
          onLoadLatest={conflict.onLoadLatest}
        >
          {conflict.kind === 'publication'
            ? 'This Draft or public WxPost changed elsewhere. Loading the latest state will discard any unsaved Draft changes. The public update was not applied.'
            : 'This workspace changed since this page loaded. Loading the latest version will discard your unsaved Draft changes. The Draft change you just attempted was not applied.'}
        </WorkspaceConflictDialog>
      )}

      {discard.open && (
        <WorkspaceConflictDialog
          title='Discard unsaved changes?'
          error={null}
          pending={false}
          testId='discard-draft-dialog'
          keepLabel='Keep editing'
          loadLabel='Discard changes'
          pendingLabel='Discarding…'
          onKeepCurrent={discard.onKeep}
          onLoadLatest={discard.onConfirm}
        >
          This restores the currently saved Draft. Your unsaved text,
          presentation, and media-placement changes will be lost.
        </WorkspaceConflictDialog>
      )}

      {coverPickerOpen && <WxPostCoverPicker {...coverPickerProps} />}

      {mediaDelete.target && (
        <WorkspaceConflictDialog
          title={
            mediaDelete.coverMediaId === mediaDelete.target.mediaId
              ? `Remove ${mediaDelete.target.mediaId} from the article?`
              : `Remove ${mediaDelete.target.mediaId} from Draft?`
          }
          error={null}
          pending={false}
          testId='delete-draft-media-dialog'
          keepLabel='Cancel'
          loadLabel={
            mediaDelete.coverMediaId === mediaDelete.target.mediaId
              ? 'Remove from article'
              : 'Remove media'
          }
          confirmClassName={DESTRUCTIVE_BUTTON_CLASS}
          onKeepCurrent={mediaDelete.onCancel}
          onLoadLatest={mediaDelete.onConfirm}
        >
          {mediaDelete.coverMediaId === mediaDelete.target.mediaId
            ? `This removes the media and its caption from the article. ${mediaDelete.target.mediaId} will remain selected as the cover until you change or remove it.`
            : 'This removes the media and its caption from the local Draft. The change is not permanent until you save the Draft.'}
        </WorkspaceConflictDialog>
      )}

      {directiveDelete.target && (
        <WorkspaceConflictDialog
          title={`Delete this ${directiveDelete.target.label}?`}
          error={null}
          pending={false}
          testId='delete-draft-directive-item-dialog'
          keepLabel='Cancel'
          loadLabel='Delete item'
          confirmClassName={DESTRUCTIVE_BUTTON_CLASS}
          onKeepCurrent={directiveDelete.onCancel}
          onLoadLatest={directiveDelete.onConfirm}
        >
          {directiveDelete.target.removesBlock
            ? 'This is the only item, so deleting it will remove the whole block. The change is not permanent until you save the Draft.'
            : 'This removes the item from the local Draft. The change is not permanent until you save the Draft.'}
        </WorkspaceConflictDialog>
      )}
    </>
  );
}
