'use client';

import {
  Check,
  Loader2,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  suggestWorkspaceVoiceToneInstruction,
  WORKSPACE_VOICE_TONE_PRESETS,
  type WorkspaceCustomVoiceToneProfile,
  type WorkspaceVoiceTonePreset,
} from '@/utils/wxpostWorkspace';

import {
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from './authoringStyles';

const FIELD_CLASS =
  'block w-full rounded-[10px] border border-[#cad5e4] bg-white px-[13px] py-3 text-[15px] font-normal leading-[1.55] text-[#172033] outline-none placeholder:text-[#93a0b2] hover:border-[#9fb1c8] focus:border-blue-600';

function selectedCustomProfiles(profiles: WorkspaceCustomVoiceToneProfile[]) {
  return profiles.filter((profile) => profile.selected);
}

export function VoiceToneField({
  workspaceId,
  presets,
  customProfiles,
  onPresetsChange,
  onCustomProfilesChange,
}: {
  workspaceId: string;
  presets: WorkspaceVoiceTonePreset[];
  customProfiles: WorkspaceCustomVoiceToneProfile[];
  onPresetsChange: (value: WorkspaceVoiceTonePreset[]) => void;
  onCustomProfilesChange: (value: WorkspaceCustomVoiceToneProfile[]) => void;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [instruction, setInstruction] = useState('');
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState(false);

  const selectedCount =
    presets.length + selectedCustomProfiles(customProfiles).length;
  const selectedDetails = useMemo(
    () => [
      ...presets.flatMap((presetId) => {
        const preset = WORKSPACE_VOICE_TONE_PRESETS.find(
          (item) => item.id === presetId
        );
        return preset
          ? [{ name: preset.label, instruction: preset.instruction }]
          : [];
      }),
      ...selectedCustomProfiles(customProfiles),
    ],
    [customProfiles, presets]
  );

  const togglePreset = (preset: WorkspaceVoiceTonePreset) => {
    if (presets.includes(preset)) {
      onPresetsChange(presets.filter((item) => item !== preset));
      return;
    }
    if (selectedCount < 3) onPresetsChange([...presets, preset]);
  };

  const toggleCustomProfile = (index: number) => {
    const profile = customProfiles[index];
    if (!profile || (!profile.selected && selectedCount >= 3)) return;
    onCustomProfilesChange(
      customProfiles.map((item, itemIndex) =>
        itemIndex === index ? { ...item, selected: !item.selected } : item
      )
    );
  };

  const openNewProfile = () => {
    setEditingIndex(null);
    setName('');
    setInstruction('');
    setDialogError(null);
    setDialogOpen(true);
  };

  const openProfileEditor = (index: number) => {
    const profile = customProfiles[index];
    if (!profile) return;
    setEditingIndex(index);
    setName(profile.name);
    setInstruction(profile.instruction);
    setDialogError(null);
    setDialogOpen(true);
  };

  const closeDialog = () => {
    if (suggesting) return;
    setDialogOpen(false);
    setDialogError(null);
  };

  const saveProfile = () => {
    const nextName = name.trim();
    const nextInstruction = instruction.trim();
    if (!nextName || !nextInstruction) {
      setDialogError('Add both a name and an instruction.');
      return;
    }
    const duplicate = customProfiles.some(
      (profile, index) =>
        index !== editingIndex &&
        profile.name.trim().toLocaleLowerCase() === nextName.toLocaleLowerCase()
    );
    if (duplicate) {
      setDialogError('A custom profile with this name already exists.');
      return;
    }

    if (editingIndex === null) {
      if (selectedCount >= 3) {
        setDialogError('Deselect one voice and tone before adding another.');
        return;
      }
      onCustomProfilesChange([
        ...customProfiles,
        { name: nextName, instruction: nextInstruction, selected: true },
      ]);
    } else {
      onCustomProfilesChange(
        customProfiles.map((profile, index) =>
          index === editingIndex
            ? {
                ...profile,
                name: nextName,
                instruction: nextInstruction,
              }
            : profile
        )
      );
    }
    setDialogOpen(false);
    setDialogError(null);
  };

  const removeProfile = () => {
    if (editingIndex === null) return;
    onCustomProfilesChange(
      customProfiles.filter((_, index) => index !== editingIndex)
    );
    setDialogOpen(false);
  };

  const suggestInstruction = async () => {
    const nextName = name.trim();
    if (!nextName) {
      setDialogError('Add a name before asking Hermes.');
      return;
    }
    setSuggesting(true);
    setDialogError(null);
    try {
      const response = await suggestWorkspaceVoiceToneInstruction(
        workspaceId,
        nextName
      );
      setInstruction(response.instruction);
    } catch (error) {
      setDialogError(
        error instanceof Error
          ? error.message
          : 'Hermes could not suggest an instruction.'
      );
    } finally {
      setSuggesting(false);
    }
  };

  return (
    <fieldset className='mb-5 min-w-0 border-0 p-0 max-[480px]:mb-4'>
      <legend className='sr-only'>Voice &amp; tone</legend>
      <div className='mb-[9px] flex items-baseline justify-between gap-3'>
        <span className='text-sm font-bold text-slate-700'>
          Voice &amp; tone
        </span>
        <span className='text-xs font-medium text-slate-500'>
          {selectedCount}/3 selected
        </span>
      </div>

      <div className='flex flex-wrap gap-2'>
        {WORKSPACE_VOICE_TONE_PRESETS.map((preset) => {
          const selected = presets.includes(preset.id);
          const disabled = !selected && selectedCount >= 3;
          return (
            <button
              key={preset.id}
              type='button'
              className={`inline-flex min-h-10 items-center gap-1.5 rounded-full border px-[14px] py-[9px] text-sm font-semibold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 max-[480px]:min-h-[34px] max-[480px]:px-2.5 max-[480px]:py-1.5 max-[480px]:text-[13px] ${
                selected
                  ? 'border-[#4b7df0] bg-[#eaf2ff] text-[#1749bb]'
                  : 'border-[#d3dce8] bg-white text-[#516079] hover:border-[#9fb8e7] hover:bg-[#f8fbff] disabled:cursor-not-allowed disabled:opacity-45'
              }`}
              aria-pressed={selected}
              disabled={disabled}
              title={preset.instruction}
              onClick={() => togglePreset(preset.id)}
              data-testid={`voice-tone-${preset.id}`}
            >
              {selected && <Check className='h-3.5 w-3.5' aria-hidden='true' />}
              {preset.label}
            </button>
          );
        })}

        {customProfiles.map((profile, index) => {
          const disabled = !profile.selected && selectedCount >= 3;
          return (
            <span
              key={`${profile.name}-${index}`}
              className={`inline-flex min-h-10 overflow-hidden rounded-full border max-[480px]:min-h-[34px] ${
                profile.selected
                  ? 'border-[#4b7df0] bg-[#eaf2ff] text-[#1749bb]'
                  : 'border-[#d3dce8] bg-white text-[#516079]'
              }`}
            >
              <button
                type='button'
                className='inline-flex items-center gap-1.5 px-3 py-[9px] text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-45 max-[480px]:px-2.5 max-[480px]:py-1.5 max-[480px]:text-[13px]'
                aria-pressed={profile.selected}
                disabled={disabled}
                title={profile.instruction}
                onClick={() => toggleCustomProfile(index)}
                data-testid={`custom-voice-tone-${index}`}
              >
                {profile.selected && (
                  <Check className='h-3.5 w-3.5' aria-hidden='true' />
                )}
                {profile.name}
              </button>
              <button
                type='button'
                className='grid w-9 place-items-center border-l border-current/15 transition hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600'
                aria-label={`Edit ${profile.name}`}
                onClick={() => openProfileEditor(index)}
              >
                <Pencil className='h-3.5 w-3.5' aria-hidden='true' />
              </button>
            </span>
          );
        })}

        <button
          type='button'
          className='inline-flex min-h-10 items-center gap-1.5 rounded-full border border-dashed border-[#afbdd0] bg-white px-[14px] py-[9px] text-sm font-semibold text-[#46556f] transition hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600 disabled:cursor-not-allowed disabled:opacity-45 max-[480px]:min-h-[34px] max-[480px]:px-2.5 max-[480px]:py-1.5 max-[480px]:text-[13px]'
          disabled={selectedCount >= 3}
          onClick={openNewProfile}
          data-testid='add-custom-voice-tone'
        >
          <Plus className='h-4 w-4' aria-hidden='true' />
          Custom
        </button>
      </div>

      <div
        className='mt-3 min-h-5 space-y-1.5 text-xs leading-5 text-slate-500 max-[480px]:mt-2'
        data-testid='voice-tone-details'
      >
        {selectedDetails.length === 0 ? (
          <p className='m-0'>
            Optional. Choose up to three styles to guide the draft.
          </p>
        ) : (
          selectedDetails.map((detail) => (
            <p key={detail.name} className='m-0'>
              <span className='font-semibold text-slate-600'>
                {detail.name}:
              </span>{' '}
              {detail.instruction}
            </p>
          ))
        )}
      </div>

      {dialogOpen && (
        <div
          className='fixed inset-0 z-[95] grid place-items-center bg-slate-950/55 p-4'
          role='dialog'
          aria-modal='true'
          aria-labelledby='voice-tone-dialog-title'
          data-testid='voice-tone-dialog'
        >
          <div className='w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl max-[480px]:p-4'>
            <div className='flex items-start justify-between gap-4'>
              <div>
                <h2
                  id='voice-tone-dialog-title'
                  className='m-0 text-lg font-bold text-slate-900 max-[480px]:text-base'
                >
                  {editingIndex === null
                    ? 'Add a custom voice & tone'
                    : 'Edit custom voice & tone'}
                </h2>
                <p className='mb-0 mt-1 text-sm leading-5 text-slate-500 max-[480px]:text-[13px]'>
                  This profile belongs only to the current workspace.
                </p>
              </div>
              <button
                type='button'
                className='grid h-8 w-8 shrink-0 place-items-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50'
                aria-label='Close'
                disabled={suggesting}
                onClick={closeDialog}
              >
                <X className='h-4 w-4' aria-hidden='true' />
              </button>
            </div>

            <div className='mt-5 grid gap-4 max-[480px]:mt-4 max-[480px]:gap-3'>
              <label className='grid gap-2 text-sm font-bold text-slate-700'>
                Name
                <input
                  className={FIELD_CLASS}
                  value={name}
                  maxLength={64}
                  placeholder='For example: Warm and conversational'
                  onChange={(event) => setName(event.target.value)}
                  data-testid='custom-voice-tone-name'
                />
              </label>
              <div className='grid gap-2 text-sm font-bold text-slate-700'>
                <div className='flex items-center justify-between gap-3'>
                  <label htmlFor='custom-voice-tone-instruction'>
                    Instruction
                  </label>
                  <button
                    type='button'
                    className='inline-flex items-center gap-1.5 text-xs font-semibold text-blue-700 hover:text-blue-800 disabled:cursor-not-allowed disabled:text-slate-400'
                    disabled={suggesting || !name.trim()}
                    onClick={() => void suggestInstruction()}
                    data-testid='suggest-voice-tone-instruction'
                  >
                    {suggesting ? (
                      <Loader2
                        className='h-3.5 w-3.5 animate-spin'
                        aria-hidden='true'
                      />
                    ) : (
                      <Sparkles className='h-3.5 w-3.5' aria-hidden='true' />
                    )}
                    {suggesting ? 'Asking Hermes…' : 'Suggest with Hermes'}
                  </button>
                </div>
                <textarea
                  id='custom-voice-tone-instruction'
                  className={`${FIELD_CLASS} min-h-32 resize-y`}
                  value={instruction}
                  maxLength={1000}
                  placeholder='Describe how the article should sound'
                  onChange={(event) => setInstruction(event.target.value)}
                  data-testid='custom-voice-tone-instruction'
                />
              </div>
            </div>

            {dialogError && (
              <p className='mb-0 mt-3 text-sm text-red-700' role='alert'>
                {dialogError}
              </p>
            )}

            <div className='mt-5 flex items-center justify-between gap-3 max-[480px]:flex-col-reverse max-[480px]:items-stretch'>
              {editingIndex === null ? (
                <span />
              ) : (
                <button
                  type='button'
                  className='inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-3 text-sm font-semibold text-red-700 transition hover:bg-red-50'
                  disabled={suggesting}
                  onClick={removeProfile}
                  data-testid='delete-custom-voice-tone'
                >
                  <Trash2 className='h-4 w-4' aria-hidden='true' />
                  Delete
                </button>
              )}
              <div className='flex justify-end gap-2 max-[480px]:[&_button]:flex-1'>
                <button
                  type='button'
                  className={SECONDARY_BUTTON_CLASS}
                  disabled={suggesting}
                  onClick={closeDialog}
                >
                  Cancel
                </button>
                <button
                  type='button'
                  className={PRIMARY_BUTTON_CLASS}
                  disabled={suggesting}
                  onClick={saveProfile}
                  data-testid='save-custom-voice-tone'
                >
                  {editingIndex === null ? 'Add tone' : 'Save tone'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </fieldset>
  );
}
