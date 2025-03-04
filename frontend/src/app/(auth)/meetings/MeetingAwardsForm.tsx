import { useState, useRef, useEffect } from 'react';
import { AwardCategory } from '../awards/AwardForm';
import { RoleTakerInput } from './RoleTakerInput';
import {
  PlusCircle,
  Save,
  Award,
  X,
  PencilLine,
  ChevronDown,
} from 'lucide-react';
import { AttendeeIF, AwardIF } from '@/interfaces';
import { toast } from 'react-hot-toast';
import { useSaveMeetingAwards } from '@/hooks/useSaveAwards';
import { useMeeting } from '@/hooks/useMeeting';

// Default award categories from the existing AwardForm
const AWARD_CATEGORIES: AwardCategory[] = [
  'Best Prepared Speaker',
  'Best Host',
  'Best Table Topic Speaker',
  'Best Facilitator',
  'Best Evaluator',
  'Best Supporter',
];

interface MeetingAward {
  category: string;
  isCustom: boolean;
  customTitle?: string;
  winner: AttendeeIF | undefined;
}

type MeetingAwardsFormProps = {
  meetingId: string;
};

export function MeetingAwardsForm({ meetingId }: MeetingAwardsFormProps) {
  const { data: meeting } = useMeeting(meetingId);

  // Initialize with default awards or existing awards from the meeting
  const [awards, setAwards] = useState<MeetingAward[]>([]);

  // Set up initial awards either from existing meeting awards or defaults
  useEffect(() => {
    if (meeting) {
      if (meeting.awards && meeting.awards.length > 0) {
        // Use existing awards
        setAwards(
          meeting.awards.map((award: AwardIF) => ({
            category: award.category,
            isCustom: !AWARD_CATEGORIES.includes(
              award.category as AwardCategory
            ),
            customTitle: !AWARD_CATEGORIES.includes(
              award.category as AwardCategory
            )
              ? award.category
              : undefined,
            winner: { name: award.winner, member_id: '', id: '' },
          }))
        );
      } else {
        // Use default awards
        setAwards(
          AWARD_CATEGORIES.map((category) => ({
            category,
            isCustom: false,
            winner: undefined,
          }))
        );
      }
    }
  }, [meeting]);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editingTypeIndex, setEditingTypeIndex] = useState<number | null>(null);
  const [openTypeDropdownIndex, setOpenTypeDropdownIndex] = useState<
    number | null
  >(null);

  const typeDropdownRef = useRef<HTMLDivElement>(null);
  const categoryTypeRef = useRef<HTMLDivElement>(null);

  const saveMeetingAwardsMutation = useSaveMeetingAwards();

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        typeDropdownRef.current &&
        !typeDropdownRef.current.contains(event.target as Node) &&
        categoryTypeRef.current &&
        !categoryTypeRef.current.contains(event.target as Node)
      ) {
        setOpenTypeDropdownIndex(null);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Add a new award input field
  const handleAddAward = () => {
    setAwards([
      ...awards,
      {
        category: 'Custom Award',
        isCustom: true,
        customTitle: '',
        winner: undefined,
      },
    ]);
  };

  // Remove an award input field
  const handleRemoveAward = (index: number) => {
    const newAwards = [...awards];
    newAwards.splice(index, 1);
    setAwards(newAwards);
  };

  // Update award category
  const handleCategoryChange = (index: number, value: string) => {
    const newAwards = [...awards];
    newAwards[index] = {
      ...newAwards[index],
      category: value,
      isCustom: false, // It's a predefined category
      customTitle: undefined,
    };
    setAwards(newAwards);
    setOpenTypeDropdownIndex(null);
  };

  // Update custom title for custom awards
  const handleCustomTitleChange = (index: number, value: string) => {
    const newAwards = [...awards];
    newAwards[index] = {
      ...newAwards[index],
      category: 'Custom Award',
      isCustom: true,
      customTitle: value,
    };
    setAwards(newAwards);
  };

  // Update award winner
  const handleWinnerChange = (index: number, winner: AttendeeIF) => {
    const newAwards = [...awards];
    newAwards[index] = {
      ...newAwards[index],
      winner,
    };
    setAwards(newAwards);
  };

  // Handle clicking the edit button
  const handleEditClick = (index: number, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent dropdown from opening
    setEditingTypeIndex(index);
    setOpenTypeDropdownIndex(null); // Close dropdown if open
  };

  // Handle exiting edit mode
  const handleTypeInputBlur = () => {
    setEditingTypeIndex(null);
  };

  // Submit awards to API
  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    setIsSubmitting(true);
    try {
      // Format awards data for API
      const formattedAwards = awards.map((award) => ({
        meeting_id: meetingId,
        category: award.isCustom
          ? award.customTitle
            ? award.customTitle
            : 'Custom'
          : award.category,
        winner: award.winner?.name || '',
      }));

      // Call the mutation to save awards
      await saveMeetingAwardsMutation.mutateAsync({
        meetingId,
        awards: formattedAwards,
      });

      toast.success('Awards saved successfully');
    } catch (error) {
      console.error('Error saving awards:', error);
      toast.error('Failed to save awards');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className='py-6 px-8 pb-24'>
      <div className='border-b pb-4 mb-6'>
        <h2 className='text-xl font-semibold text-gray-800 flex items-center'>
          <Award className='w-5 h-5 mr-2 text-indigo-500' />
          Meeting Awards
        </h2>
        <p className='text-sm text-gray-500 mt-1'>
          Recognize outstanding performances from this meeting
        </p>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
        {awards.map((award, index) => (
          <div key={index} className='relative group'>
            {/* Award container with remove button */}
            <div className='border rounded-md p-4 relative'>
              <button
                type='button'
                onClick={() => handleRemoveAward(index)}
                className='absolute top-2 right-2 text-gray-400 hover:text-red-500'
              >
                <X className='w-4 h-4' />
              </button>

              {/* Award Category Selection - Similar to SegmentsEditor */}
              <div className='mb-4'>
                {editingTypeIndex === index ? (
                  <input
                    type='text'
                    value={
                      award.isCustom ? award.customTitle || '' : award.category
                    }
                    onChange={(e) =>
                      handleCustomTitleChange(index, e.target.value)
                    }
                    placeholder='Enter custom award title'
                    onBlur={handleTypeInputBlur}
                    className='text-sm font-medium text-gray-900 w-full px-0 py-1 border-b border-gray-100 focus:border-gray-200 bg-transparent focus:outline-none transition-colors'
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <div className='flex items-center'>
                    <div
                      ref={
                        openTypeDropdownIndex === index ? categoryTypeRef : null
                      }
                      className='flex items-center gap-1 cursor-pointer'
                      onClick={() => {
                        setOpenTypeDropdownIndex(
                          openTypeDropdownIndex === index ? null : index
                        );
                      }}
                    >
                      <span className='text-sm font-medium text-gray-900 break-words border-b border-transparent py-1'>
                        {award.isCustom
                          ? award.customTitle
                            ? award.customTitle
                            : 'Custom'
                          : award.category}
                      </span>
                      <ChevronDown
                        className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${
                          openTypeDropdownIndex === index
                            ? 'transform rotate-180'
                            : ''
                        }`}
                      />
                    </div>
                    <button
                      onClick={(e) => handleEditClick(index, e)}
                      className='ml-1.5 text-gray-400 hover:text-gray-500 transition-colors cursor-pointer opacity-0 group-hover:opacity-100 duration-300'
                      title='Edit award type'
                    >
                      <PencilLine className='w-3.5 h-3.5' />
                    </button>
                  </div>
                )}

                {openTypeDropdownIndex === index && (
                  <div
                    ref={typeDropdownRef}
                    className='absolute left-0 top-full mt-1 w-full bg-gray-50 rounded-md shadow-lg border border-gray-200 z-30'
                  >
                    <div className='py-1 max-h-80 overflow-auto'>
                      {AWARD_CATEGORIES.map((category) => (
                        <div
                          key={category}
                          className='px-4 py-2 text-xs text-gray-700 hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer'
                          onClick={() => handleCategoryChange(index, category)}
                        >
                          {category}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Winner Selection */}
              <div>
                <RoleTakerInput
                  value={award.winner}
                  onChange={(value) => handleWinnerChange(index, value)}
                  placeholder='Select or enter winner name'
                  required={true}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Add Award Button */}
      <div className='mt-6'>
        <button
          type='button'
          onClick={handleAddAward}
          className='flex items-center text-sm text-indigo-600 hover:text-indigo-800'
        >
          <PlusCircle className='w-4 h-4 mr-1' />
          Add Another Award
        </button>
      </div>

      {/* Submit Button */}
      <div className='mt-8 pt-6 border-t'>
        <button
          type='submit'
          disabled={isSubmitting}
          className='w-full flex items-center justify-center gap-2 py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50'
        >
          {isSubmitting ? (
            <>
              <span className='animate-spin mr-2'>
                <svg
                  className='w-4 h-4'
                  xmlns='http://www.w3.org/2000/svg'
                  fill='none'
                  viewBox='0 0 24 24'
                >
                  <circle
                    className='opacity-25'
                    cx='12'
                    cy='12'
                    r='10'
                    stroke='currentColor'
                    strokeWidth='4'
                  ></circle>
                  <path
                    className='opacity-75'
                    fill='currentColor'
                    d='M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z'
                  ></path>
                </svg>
              </span>
              Saving...
            </>
          ) : (
            <>
              <Save className='w-4 h-4 mr-2' />
              Save Awards
            </>
          )}
        </button>
      </div>
    </form>
  );
}
