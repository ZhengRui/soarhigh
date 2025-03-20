import React, { useState, useEffect, useRef } from 'react';
import {
  PlusCircle,
  Save,
  X,
  PencilLine,
  Loader2,
  Vote as VoteIcon,
  ChevronDown,
  RefreshCw,
} from 'lucide-react';
import { useVoteForm } from '@/hooks/votes/useVoteForm';
import { useVoteStatus } from '@/hooks/votes/useVoteStatus';
import { useSaveVoteForm } from '@/hooks/votes/useSaveVoteForm';
import { useUpdateVoteStatus } from '@/hooks/votes/useUpdateVoteStatus';
import { useDefaultVoteForm } from '@/hooks/votes/useDefaultVoteForm';
import { CategoryCandidatesIF, AttendeeIF } from '@/interfaces';
import { RoleTakerInput } from './RoleTakerInput';
import { SEGMENT_TYPE_MAP } from '@/utils/defaultSegments';
import toast from 'react-hot-toast';

// Component for Switch since we don't have the ui library
const Switch = ({
  checked,
  onCheckedChange,
  disabled,
  isLoading,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  isLoading?: boolean;
}) => {
  return (
    <button
      type='button'
      onClick={() => !disabled && !isLoading && onCheckedChange(!checked)}
      disabled={disabled || isLoading}
      className={`relative inline-flex h-6 w-11 items-center rounded-full ${
        checked ? 'bg-indigo-600' : 'bg-gray-200'
      } ${disabled || isLoading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span className='sr-only'>Toggle voting status</span>
      <span
        className={`${
          checked ? 'translate-x-6' : 'translate-x-1'
        } inline-flex items-center justify-center h-4 w-4 transform rounded-full bg-white transition`}
      >
        {isLoading && (
          <Loader2 className='w-3 h-3 text-indigo-500 animate-spin' />
        )}
      </span>
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
  const {
    data: voteFormData,
    isLoading: isLoadingVoteForm,
    refetch: refetchVoteForm,
  } = useVoteForm(meetingId);
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

  // Add state for segment type dropdown and editing
  const [openSegmentTypeIndex, setOpenSegmentTypeIndex] = useState<{
    categoryIndex: number;
    candidateIndex: number;
  } | null>(null);
  const [editingSegmentTypeIndices, setEditingSegmentTypeIndices] = useState<{
    categoryIndex: number;
    candidateIndex: number;
  } | null>(null);

  // Add state for tracking refresh operation
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Calculate highest vote counts for each category
  const highestVoteCounts = React.useMemo(() => {
    if (!voteForm) return {};

    const result: Record<string, number> = {};

    voteForm.forEach((category) => {
      if (category.candidates.length === 0) return;

      const maxCount = Math.max(
        ...category.candidates.map((c) => c.count || 0)
      );
      if (maxCount > 0) {
        result[category.category] = maxCount;
      }
    });

    return result;
  }, [voteForm]);

  // Refs for handling outside clicks
  const categoryDropdownRef = useRef<HTMLDivElement>(null);
  const categoryNameRef = useRef<HTMLDivElement>(null);
  // Add refs for segment type dropdown
  const segmentTypeDropdownRef = useRef<HTMLDivElement>(null);
  const segmentTypeRef = useRef<HTMLDivElement>(null);

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

  // Add useEffect for handling outside clicks on segment type dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        segmentTypeDropdownRef.current &&
        !segmentTypeDropdownRef.current.contains(event.target as Node) &&
        segmentTypeRef.current &&
        !segmentTypeRef.current.contains(event.target as Node)
      ) {
        setOpenSegmentTypeIndex(null);
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
    updatedVoteForm[categoryIndex].candidates.push({
      name: '',
      segment: '',
      count: 0,
    });
    setVoteForm(updatedVoteForm);
  };

  const handleCandidateChange = (
    categoryIndex: number,
    candidateIndex: number,
    value: AttendeeIF
  ) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm[categoryIndex].candidates[candidateIndex] = {
      name: value.name,
      segment:
        updatedVoteForm[categoryIndex].candidates[candidateIndex]?.segment ||
        '',
      count:
        updatedVoteForm[categoryIndex].candidates[candidateIndex]?.count || 0,
    };
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
      // await saveVoteFormAsync({
      //   meetingId,
      //   voteForm,
      // });

      // Then toggle the voting status
      await updateVoteStatusAsync({
        meetingId,
        open: !voteStatus.open,
      });
    } catch (error) {
      console.error('Error toggling voting status:', error);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    try {
      // strip of empty candidates
      const updatedVoteForm = voteForm.map((category) => ({
        ...category,
        candidates: category.candidates.filter((candidate) => candidate.name),
      }));

      // check for duplicates
      const duplicateCandidates = updatedVoteForm.some((category) =>
        category.candidates.some((candidate, index) =>
          category.candidates
            .slice(0, index)
            .some((c) => c.name === candidate.name)
        )
      );

      if (duplicateCandidates) {
        toast.error(
          'Duplicate candidates found. Please ensure each candidate name is unique within a category.'
        );
        return;
      }

      await saveVoteFormAsync({
        meetingId,
        voteForm: updatedVoteForm,
      });
    } catch (error) {
      console.error('Error saving vote form:', error);
    }
  };

  const handleSegmentTypeChange = (
    categoryIndex: number,
    candidateIndex: number,
    segmentType: string
  ) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm[categoryIndex].candidates[candidateIndex] = {
      ...updatedVoteForm[categoryIndex].candidates[candidateIndex],
      segment: segmentType,
    };
    setVoteForm(updatedVoteForm);
    setOpenSegmentTypeIndex(null);
  };

  const handleSegmentTypeEditClick = (
    categoryIndex: number,
    candidateIndex: number,
    e: React.MouseEvent
  ) => {
    e.stopPropagation();
    setEditingSegmentTypeIndices({ categoryIndex, candidateIndex });
    setOpenSegmentTypeIndex(null);
  };

  const handleSegmentTypeInputBlur = () => {
    setEditingSegmentTypeIndices(null);
  };

  const handleCustomSegmentTypeChange = (
    categoryIndex: number,
    candidateIndex: number,
    value: string
  ) => {
    const updatedVoteForm = [...voteForm];
    updatedVoteForm[categoryIndex].candidates[candidateIndex] = {
      ...updatedVoteForm[categoryIndex].candidates[candidateIndex],
      segment: value,
    };
    setVoteForm(updatedVoteForm);
  };

  // Function to handle refresh of vote data
  const handleRefreshVotes = async () => {
    setIsRefreshing(true);
    try {
      const result = await refetchVoteForm();
      if (result.data) {
        // Create a mapping of category+name to new data
        const newDataMap: Record<string, any> = {};
        result.data.forEach((category) => {
          category.candidates.forEach((candidate) => {
            const key = `${category.category}|${candidate.name}`;
            newDataMap[key] = candidate;
          });
        });

        // Update current voteForm with new counts but preserve order
        const updatedVoteForm = voteForm.map((category) => ({
          ...category,
          candidates: category.candidates.map((candidate) => {
            const key = `${category.category}|${candidate.name}`;
            const newCandidate = newDataMap[key];

            // If found, update the count while preserving other properties
            if (newCandidate) {
              return {
                ...candidate,
                count: newCandidate.count,
              };
            }
            return candidate;
          }),
        }));

        setVoteForm(updatedVoteForm);
        toast.success('Vote counts updated');
      }
    } catch (error) {
      toast.error('Failed to refresh vote data');
      console.error('Error refreshing vote data:', error);
    } finally {
      setIsRefreshing(false);
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
        <div className='flex items-center gap-2'>
          <span className='hidden xs:block text-xs sm:text-sm text-gray-600'>
            Voting is {voteStatus?.open ? 'Open' : 'Closed'}
          </span>
          <Switch
            checked={voteStatus?.open || false}
            onCheckedChange={handleToggleVoting}
            disabled={isSubmitting}
            isLoading={isUpdatingStatus}
          />
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
                    className='absolute left-0 top-12 mt-1 w-full bg-gray-50 rounded-md shadow-lg border border-gray-200 z-30'
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
                <div className='space-y-2'>
                  {categoryItem.candidates.map(
                    (candidate, candidateIndex: number) => {
                      // Check if this candidate has the highest vote count
                      const isHighestVote =
                        highestVoteCounts[categoryItem.category] > 0 &&
                        candidate.count ===
                          highestVoteCounts[categoryItem.category];

                      return (
                        <div
                          key={candidateIndex}
                          className={`flex items-start sm:items-center justify-between gap-2 rounded-md py-1 px-2 relative ${
                            isHighestVote ? 'bg-indigo-200' : 'bg-gray-200'
                          }`}
                        >
                          <div className='grid grid-cols-1 sm:grid-cols-3 gap-2 w-full'>
                            <div className='relative'>
                              <RoleTakerInput
                                value={{
                                  name: candidate.name,
                                  member_id: '',
                                  id: '',
                                }}
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
                              <span
                                className={`absolute top-1/2 transform -translate-y-1/2 right-0 -translate-x-3 text-xs font-medium rounded-md inline-flex items-center justify-center h-6 p-1.5 ${
                                  isHighestVote
                                    ? 'text-indigo-600 bg-indigo-200'
                                    : 'text-gray-400 bg-gray-100'
                                }`}
                              >
                                {candidate.count}
                              </span>
                            </div>

                            {/* Segment Type Selector */}
                            <div className='relative sm:col-span-2 flex items-center'>
                              <div className='select-none w-full'>
                                <div className='flex items-center gap-2 w-full'>
                                  {editingSegmentTypeIndices?.categoryIndex ===
                                    categoryIndex &&
                                  editingSegmentTypeIndices?.candidateIndex ===
                                    candidateIndex ? (
                                    <input
                                      type='text'
                                      value={candidate.segment || ''}
                                      onChange={(e) =>
                                        handleCustomSegmentTypeChange(
                                          categoryIndex,
                                          candidateIndex,
                                          e.target.value
                                        )
                                      }
                                      onBlur={handleSegmentTypeInputBlur}
                                      className='text-xs font-medium w-full px-2 py-2 border rounded bg-white border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200'
                                      autoFocus
                                      onClick={(e) => e.stopPropagation()}
                                      placeholder='Enter segment type'
                                    />
                                  ) : (
                                    <div className='flex items-center gap-1 w-full'>
                                      <div
                                        ref={
                                          openSegmentTypeIndex?.categoryIndex ===
                                            categoryIndex &&
                                          openSegmentTypeIndex?.candidateIndex ===
                                            candidateIndex
                                            ? segmentTypeRef
                                            : null
                                        }
                                        className='flex items-center gap-1 cursor-pointer w-full sm:w-auto'
                                        onClick={() => {
                                          setOpenSegmentTypeIndex(
                                            openSegmentTypeIndex?.categoryIndex ===
                                              categoryIndex &&
                                              openSegmentTypeIndex?.candidateIndex ===
                                                candidateIndex
                                              ? null
                                              : {
                                                  categoryIndex,
                                                  candidateIndex,
                                                }
                                          );
                                        }}
                                      >
                                        <span className='text-xs font-medium text-gray-600 border border-transparent py-2 sm:py-1.5 px-2 rounded bg-gray-100 truncate w-full text-wrap'>
                                          {candidate.segment ||
                                            'Select segment'}
                                        </span>
                                        <ChevronDown
                                          className={`w-3.5 h-3.5 text-gray-400 transition-transform duration-200 ${
                                            openSegmentTypeIndex?.categoryIndex ===
                                              categoryIndex &&
                                            openSegmentTypeIndex?.candidateIndex ===
                                              candidateIndex
                                              ? 'transform rotate-180'
                                              : ''
                                          }`}
                                        />
                                      </div>
                                      <button
                                        onClick={(e) =>
                                          handleSegmentTypeEditClick(
                                            categoryIndex,
                                            candidateIndex,
                                            e
                                          )
                                        }
                                        className='text-gray-400 hover:text-gray-500 transition-colors cursor-pointer opacity-0 group-hover:opacity-100 duration-300'
                                        title='Edit segment type'
                                      >
                                        <PencilLine className='w-3 h-3' />
                                      </button>
                                    </div>
                                  )}
                                </div>
                                {openSegmentTypeIndex?.categoryIndex ===
                                  categoryIndex &&
                                  openSegmentTypeIndex?.candidateIndex ===
                                    candidateIndex && (
                                    <div
                                      ref={segmentTypeDropdownRef}
                                      className='absolute left-0 top-full mt-1 w-full bg-gray-50 rounded-md shadow-lg border border-gray-200 z-30'
                                    >
                                      <div className='py-1 max-h-40 overflow-auto'>
                                        {Object.keys(SEGMENT_TYPE_MAP).map(
                                          (type) => (
                                            <div
                                              key={type}
                                              className='px-3 py-1.5 text-xs text-gray-700 hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer truncate'
                                              onClick={() =>
                                                handleSegmentTypeChange(
                                                  categoryIndex,
                                                  candidateIndex,
                                                  type
                                                )
                                              }
                                            >
                                              {type}
                                            </div>
                                          )
                                        )}
                                      </div>
                                    </div>
                                  )}
                              </div>
                            </div>
                          </div>

                          <button
                            type='button'
                            onClick={() =>
                              handleRemoveCandidate(
                                categoryIndex,
                                candidateIndex
                              )
                            }
                            className='text-gray-400 hover:text-red-500 focus:outline-none'
                          >
                            <X className='w-4 h-4' />
                          </button>
                        </div>
                      );
                    }
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
          disabled={voteStatus?.open || isSubmitting}
          className={`w-full flex items-center justify-center gap-2 py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 ${
            voteStatus?.open ? 'cursor-not-allowed' : ''
          }`}
        >
          {isSubmitting ? (
            <Loader2 className='w-4 h-4 animate-spin' />
          ) : (
            <Save className='w-4 h-4' />
          )}
          {'Save Voting Setup'}
        </button>
      </div>

      {/* Floating refresh button - only visible when voting is open */}
      {voteStatus?.open && (
        <div className='fixed left-6 bottom-6 z-50'>
          <button
            type='button'
            onClick={handleRefreshVotes}
            disabled={isRefreshing}
            className='flex items-center justify-center h-12 w-12 rounded-full bg-indigo-600 text-white shadow-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors'
            title='Refresh vote data'
          >
            {isRefreshing ? (
              <Loader2 className='h-5 w-5 animate-spin' />
            ) : (
              <RefreshCw className='h-5 w-5' />
            )}
          </button>
        </div>
      )}
    </form>
  );
}
