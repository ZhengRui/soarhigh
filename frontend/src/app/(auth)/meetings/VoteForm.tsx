import React, { useState, useEffect, useRef } from 'react';
import {
  PlusCircle,
  Save,
  X,
  PencilLine,
  Loader2,
  Vote as VoteIcon,
  Copy,
  ChevronDown,
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { useVoteForm } from '@/hooks/votes/useVoteForm';
import { useVoteStatus } from '@/hooks/votes/useVoteStatus';
import { useSaveVoteForm } from '@/hooks/votes/useSaveVoteForm';
import { useUpdateVoteStatus } from '@/hooks/votes/useUpdateVoteStatus';
import { useDefaultVoteForm } from '@/hooks/votes/useDefaultVoteForm';
import { CategoryCandidatesIF, AttendeeIF } from '@/interfaces';
import { RoleTakerInput } from './RoleTakerInput';

// Component for Switch since we don't have the ui library
const Switch = ({
  checked,
  onCheckedChange,
  disabled,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}) => {
  return (
    <button
      type='button'
      onClick={() => !disabled && onCheckedChange(!checked)}
      disabled={disabled}
      className={`relative inline-flex h-6 w-11 items-center rounded-full ${
        checked ? 'bg-indigo-600' : 'bg-gray-200'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span className='sr-only'>Toggle voting status</span>
      <span
        className={`${
          checked ? 'translate-x-6' : 'translate-x-1'
        } inline-block h-4 w-4 transform rounded-full bg-white transition`}
      />
    </button>
  );
};

const VOTE_CATEGORIES = [
  'Best Prepared Speaker',
  'Best Host',
  'Best Table Topic Speaker',
  'Best Facilitator',
  'Best Evaluator',
  'Best Supporter',
  'Best Meeting Manager',
];

type VoteFormProps = {
  meetingId: string;
};

export function VoteForm({ meetingId }: VoteFormProps) {
  // Use the vote-related hooks
  const { data: voteFormData, isLoading: isLoadingVoteForm } =
    useVoteForm(meetingId);
  const { data: voteStatus, isLoading: isLoadingVoteStatus } =
    useVoteStatus(meetingId);
  const { defaultVoteForm, isLoading: isLoadingDefaultForm } =
    useDefaultVoteForm(meetingId);
  const { mutateAsync: saveVoteFormAsync, isPending: isSavingForm } =
    useSaveVoteForm();
  const { mutateAsync: updateVoteStatusAsync, isPending: isUpdatingStatus } =
    useUpdateVoteStatus();

  // Local state
  const [voteForm, setVoteForm] = useState<CategoryCandidatesIF[]>([]);
  const [editingCategoryIndex, setEditingCategoryIndex] = useState<
    number | null
  >(null);
  const [openCategoryDropdownIndex, setOpenCategoryDropdownIndex] = useState<
    number | null
  >(null);
  const [votingUrl, setVotingUrl] = useState('');

  // Refs for handling outside clicks
  const categoryDropdownRef = useRef<HTMLDivElement>(null);
  const categoryNameRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        categoryDropdownRef.current &&
        !categoryDropdownRef.current.contains(event.target as Node) &&
        categoryNameRef.current &&
        !categoryNameRef.current.contains(event.target as Node)
      ) {
        setOpenCategoryDropdownIndex(null);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Initialize voteForm from the fetched data or default form
  useEffect(() => {
    if (voteFormData && voteFormData.length > 0) {
      setVoteForm(voteFormData);
    } else if (defaultVoteForm && defaultVoteForm.length > 0) {
      setVoteForm(defaultVoteForm);
    }
  }, [voteFormData, defaultVoteForm]);

  // Generate voting URL for sharing
  useEffect(() => {
    if (meetingId) {
      const baseUrl = window.location.origin;
      setVotingUrl(`${baseUrl}/meetings/${meetingId}/vote`);
    }
  }, [meetingId]);

  const copyVotingLink = () => {
    navigator.clipboard.writeText(votingUrl);
    toast.success('Voting link copied to clipboard');
  };

  const handleCategoryChange = (index: number, value: string) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm[index].category = value;
    setVoteForm(updatedVoteForm);
    setOpenCategoryDropdownIndex(null);
  };

  const handleCustomCategoryChange = (index: number, value: string) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm[index].category = value;
    setVoteForm(updatedVoteForm);
  };

  const handleAddCategory = () => {
    setVoteForm([
      ...voteForm,
      {
        category: 'Custom Category',
        candidates: [],
      },
    ]);
  };

  const handleRemoveCategory = (index: number) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm.splice(index, 1);
    setVoteForm(updatedVoteForm);
  };

  const handleAddCandidate = (categoryIndex: number) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm[categoryIndex].candidates.push('');
    setVoteForm(updatedVoteForm);
  };

  const handleCandidateChange = (
    categoryIndex: number,
    candidateIndex: number,
    value: AttendeeIF
  ) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm[categoryIndex].candidates[candidateIndex] = value.name;
    setVoteForm(updatedVoteForm);
  };

  const handleRemoveCandidate = (
    categoryIndex: number,
    candidateIndex: number
  ) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm[categoryIndex].candidates.splice(candidateIndex, 1);
    setVoteForm(updatedVoteForm);
  };

  const handleEditClick = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingCategoryIndex(index);
  };

  const handleCategoryInputBlur = () => {
    setEditingCategoryIndex(null);
  };

  const handleToggleVoting = async () => {
    if (!voteStatus) return;

    try {
      // First, save the form to ensure all candidates are properly recorded
      await saveVoteFormAsync({
        meetingId,
        voteForm,
      });

      // Then toggle the voting status
      await updateVoteStatusAsync({
        meetingId,
        isOpen: !voteStatus.open,
      });
    } catch (error) {
      console.error('Error toggling voting status:', error);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    try {
      await saveVoteFormAsync({
        meetingId,
        voteForm,
      });
    } catch (error) {
      console.error('Error saving vote form:', error);
    }
  };

  const isLoading =
    isLoadingVoteForm || isLoadingVoteStatus || isLoadingDefaultForm;
  const isSubmitting = isSavingForm || isUpdatingStatus;

  if (isLoading) {
    return (
      <div className='flex justify-center items-center py-12'>
        <Loader2 className='w-6 h-6 animate-spin text-indigo-600' />
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className='py-6 px-8 pb-14'>
      <div className='flex justify-between items-center mb-6 border-b pb-4'>
        <h2 className='text-2xl font-semibold text-gray-800 flex items-center'>
          <VoteIcon className='w-5 h-5 mr-2 text-indigo-600' />
          Voting Setup
        </h2>

        {/* Voting Status Control */}
        <div className='flex items-center space-x-4'>
          <div className='flex items-center space-x-2'>
            <span className='text-sm text-gray-600'>
              Voting is {voteStatus?.open ? 'Open' : 'Closed'}
            </span>
            <Switch
              checked={voteStatus?.open || false}
              onCheckedChange={handleToggleVoting}
              disabled={isSubmitting}
            />
          </div>

          {voteStatus?.open && (
            <button
              type='button'
              onClick={copyVotingLink}
              className='flex items-center text-sm px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 text-gray-700'
            >
              <Copy className='w-3.5 h-3.5 mr-1' />
              Copy Link
            </button>
          )}
        </div>
      </div>

      {/* Instructions */}
      <div className='mb-6 text-sm text-gray-600 bg-blue-50 border border-blue-100 p-3 rounded'>
        <p className='mb-1'>
          <strong>Instructions:</strong>
        </p>
        <ul className='list-disc pl-5 space-y-1'>
          <li>Define voting categories and candidates below.</li>
          <li>Toggle the switch above to open/close voting.</li>
          {voteStatus?.open && (
            <li>Share the voting link with meeting attendees.</li>
          )}
        </ul>
      </div>

      {/* Categories and Candidates */}
      <div className='grid grid-cols-1 gap-6'>
        {voteForm.map((categoryItem, categoryIndex: number) => (
          <div key={categoryIndex} className='relative group'>
            {/* Category container with remove button */}
            <div className='border rounded-md p-4 relative'>
              <button
                type='button'
                onClick={() => handleRemoveCategory(categoryIndex)}
                className='absolute top-2 right-2 text-gray-400 hover:text-red-500'
              >
                <X className='w-4 h-4' />
              </button>

              {/* Category Selection - Similar to MeetingAwardsForm */}
              <div className='mb-4'>
                {editingCategoryIndex === categoryIndex ? (
                  <input
                    type='text'
                    value={categoryItem.category}
                    onChange={(e) =>
                      handleCustomCategoryChange(categoryIndex, e.target.value)
                    }
                    placeholder='Enter category name'
                    onBlur={handleCategoryInputBlur}
                    className='text-sm font-medium text-gray-900 w-full px-0 py-1 border-b border-gray-100 focus:border-gray-200 bg-transparent focus:outline-none transition-colors'
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <div className='flex items-center'>
                    <div
                      ref={
                        openCategoryDropdownIndex === categoryIndex
                          ? categoryNameRef
                          : null
                      }
                      className='flex items-center gap-1 cursor-pointer'
                      onClick={() => {
                        setOpenCategoryDropdownIndex(
                          openCategoryDropdownIndex === categoryIndex
                            ? null
                            : categoryIndex
                        );
                      }}
                    >
                      <span className='text-sm font-medium text-gray-900 break-words border-b border-transparent py-1'>
                        {categoryItem.category}
                      </span>
                      <ChevronDown
                        className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${
                          openCategoryDropdownIndex === categoryIndex
                            ? 'transform rotate-180'
                            : ''
                        }`}
                      />
                    </div>
                    <button
                      onClick={(e) => handleEditClick(categoryIndex, e)}
                      className='ml-1.5 text-gray-400 hover:text-gray-500 transition-colors cursor-pointer opacity-0 group-hover:opacity-100 duration-300'
                      title='Edit category'
                    >
                      <PencilLine className='w-3.5 h-3.5' />
                    </button>
                  </div>
                )}

                {openCategoryDropdownIndex === categoryIndex && (
                  <div
                    ref={categoryDropdownRef}
                    className='absolute left-0 top-16 mt-1 w-full bg-gray-50 rounded-md shadow-lg border border-gray-200 z-30'
                  >
                    <div className='py-1 max-h-50 overflow-auto'>
                      {VOTE_CATEGORIES.map((category) => (
                        <div
                          key={category}
                          className='px-4 py-2 text-xs text-gray-700 hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer'
                          onClick={() =>
                            handleCategoryChange(categoryIndex, category)
                          }
                        >
                          {category}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Candidates Section */}
              <div className='mt-3'>
                {/* <div className='text-xs font-medium text-gray-600 mb-2'>
                  Candidates:
                </div> */}

                <div className='space-y-2'>
                  {categoryItem.candidates.map(
                    (candidate, candidateIndex: number) => (
                      <div
                        key={candidateIndex}
                        className='flex items-center justify-between bg-gray-50 rounded-md py-1 px-2'
                      >
                        <div className='flex-1'>
                          <RoleTakerInput
                            value={{ name: candidate, member_id: '', id: '' }}
                            onChange={(value) =>
                              handleCandidateChange(
                                categoryIndex,
                                candidateIndex,
                                value
                              )
                            }
                            placeholder='Enter candidate name'
                            disableMemberLookup={true}
                          />
                        </div>
                        <button
                          type='button'
                          onClick={() =>
                            handleRemoveCandidate(categoryIndex, candidateIndex)
                          }
                          className='ml-2 text-gray-400 hover:text-red-500 focus:outline-none'
                        >
                          <X className='w-4 h-4' />
                        </button>
                      </div>
                    )
                  )}

                  <button
                    type='button'
                    onClick={() => handleAddCandidate(categoryIndex)}
                    className='flex items-center text-xs mt-2 text-gray-600 hover:text-indigo-700'
                  >
                    <PlusCircle className='w-3.5 h-3.5 mr-1' />
                    Add Candidate
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Add Category Button */}
      <div className='mt-6'>
        <button
          type='button'
          onClick={handleAddCategory}
          className='flex items-center text-sm text-indigo-600 hover:text-indigo-800'
        >
          <PlusCircle className='w-4 h-4 mr-1' />
          Add Another Category
        </button>
      </div>

      {/* Submit Button */}
      <div className='mt-14 pt-6 border-t'>
        <button
          type='submit'
          disabled={isSubmitting}
          className='w-full flex items-center justify-center gap-2 py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50'
        >
          {isSubmitting ? (
            <Loader2 className='w-4 h-4 animate-spin' />
          ) : (
            <Save className='w-4 h-4' />
          )}
          {'Save Voting Setup'}
        </button>
      </div>
    </form>
  );
}
