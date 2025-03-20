import { AttendeeIF, MeetingIF } from '@/interfaces';
import { createMeeting, updateMeeting, deleteMeeting } from '@/utils/meeting';
import {
  BaseSegment,
  CustomSegment,
  SEGMENT_TYPE_MAP,
  SegmentParams,
} from '@/utils/defaultSegments';
import { useState } from 'react';
import { timeStringToMinutes } from './SegmentsEditor';
import { v4 as uuidv4 } from 'uuid';
import {
  Users,
  Calendar,
  Clock,
  MapPin,
  Save,
  PlusCircle,
  Loader2,
  Trash2,
  FileText,
  PenSquare,
  Table2,
} from 'lucide-react';
import { SegmentsEditor } from './SegmentsEditor';
import { useRouter } from 'next/navigation';
import toast from 'react-hot-toast';
import { useMembers } from '@/hooks/useMember';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/hooks/useAuth';
import { useIsAdmin } from '@/hooks/useIsAdmin';

const MEETING_TYPES = ['Regular', 'Workshop', 'Custom'] as const;

// Helper function to clean segment data for API submission
const transformSegmentsForAPI = (segments: BaseSegment[]) => {
  return segments.map((segment) => {
    // Extract only the properties needed by the API
    const {
      id,
      type,
      start_time,
      duration,
      end_time,
      role_taker,
      title,
      content,
      related_segment_ids,
    } = segment;

    // Return a clean object with only API-required fields e.g. *_config
    return {
      id,
      type,
      start_time,
      duration,
      end_time,
      role_taker,
      title,
      content,
      related_segment_ids,
    };
  });
};

type MeetingTemplateType = Omit<MeetingIF, 'segments'> & {
  segments: BaseSegment[];
};

type MeetingFormProps = {
  initFormData: MeetingTemplateType;
  mode?: 'create' | 'edit';
  meetingId?: string;
};

export function MeetingForm({
  initFormData,
  mode = 'create',
  meetingId,
}: MeetingFormProps) {
  const router = useRouter();
  const { data: members = [], isLoading: membersLoading } = useMembers();
  const { data: user } = useAuth();
  const { data: isAdmin = false } = useIsAdmin();
  const [formData, setFormData] = useState<MeetingTemplateType>(() => ({
    ...initFormData,
    // Clone the segments to avoid mutating the original array
    segments: initFormData.segments.map((segment) => ({ ...segment })),
  }));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const queryClient = useQueryClient();

  const canDeleteMeeting =
    isAdmin || user?.uid === initFormData.manager?.member_id;

  const handleInputChange = (
    field: keyof MeetingTemplateType,
    value: string | AttendeeIF | undefined
  ) => {
    // Special handling for the 'no' field to ensure it's stored as a number
    if (field === 'no' && typeof value === 'string') {
      // Remove non-digit characters and convert to number
      const numericValue =
        value === '' ? undefined : parseInt(value.replace(/\D/g, ''), 10);
      setFormData((prev) => ({ ...prev, [field]: numericValue }));
    } else {
      setFormData((prev) => ({ ...prev, [field]: value }));
    }
  };

  const handleSegmentChange = (
    index: number,
    field: keyof BaseSegment,
    value: string | AttendeeIF | undefined
  ) => {
    setFormData((prev) => {
      const newSegments = [...prev.segments];

      if (field === 'type') {
        if (typeof value === 'string' && value in SEGMENT_TYPE_MAP) {
          // Create new segment of the selected type
          const oldSegment = newSegments[index];
          const params = {
            id: oldSegment.id,
            start_time: oldSegment.start_time,
            duration: oldSegment.duration,
          };

          const SegmentClass =
            SEGMENT_TYPE_MAP[value as keyof typeof SEGMENT_TYPE_MAP];
          if (SegmentClass) {
            newSegments[index] = new (SegmentClass as new (
              params: SegmentParams
            ) => BaseSegment)(params);
          }
        } else {
          newSegments[index] = {
            ...newSegments[index],
            [field]: value as string,
          };
        }
      } else {
        // Handle other field changes while preserving the class instance
        const segment = newSegments[index];
        (segment[field] as any) = value;
      }

      return { ...prev, segments: newSegments };
    });
  };

  const handleSegmentsShift = (
    startIndex: number,
    endIndex: number,
    startTime: string,
    duration: string
  ) => {
    setFormData((prev) => {
      const newSegments = [...prev.segments];
      const firstSegment = newSegments[startIndex];

      // Calculate time shift
      const oldStartMinutes = timeStringToMinutes(firstSegment.start_time);
      const newStartMinutes = timeStringToMinutes(startTime);
      const startTimeShift = newStartMinutes - oldStartMinutes;

      // Update duration shift
      const durationShift =
        parseInt(duration) - parseInt(firstSegment.duration);

      // Update first segment directly
      firstSegment.start_time = startTime;
      firstSegment.duration = duration;

      // Shift subsequent segments
      for (let i = startIndex + 1; i <= endIndex; i++) {
        const segment = newSegments[i];
        const currentStartMinutes = timeStringToMinutes(segment.start_time);
        const newStartMinutes =
          currentStartMinutes + startTimeShift + durationShift;
        const hours = Math.floor(newStartMinutes / 60);
        const minutes = newStartMinutes % 60;

        segment.start_time = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
      }

      return { ...prev, segments: newSegments };
    });
  };

  const handleSegmentDelete = (index: number) => {
    setFormData((prev) => {
      const segmentToDelete = prev.segments[index];
      const newSegments = prev.segments.filter((_, i) => i !== index);

      // Update related_segment_ids in remaining segments
      newSegments.forEach((segment) => {
        if (segment.related_segment_ids) {
          segment.related_segment_ids = segment.related_segment_ids
            .split(',')
            .filter((id) => id !== segmentToDelete.id)
            .join(',');
        }
      });

      return { ...prev, segments: newSegments };
    });
  };

  const handleSegmentAdd = (index: number) => {
    setFormData((prev) => {
      const newSegments = [...prev.segments];
      const prevSegment = newSegments[index];

      // Calculate new start time based on previous segment
      let newStartTime = '';
      if (prevSegment?.start_time && prevSegment?.duration) {
        const [hours, minutes] = prevSegment.start_time.split(':');
        const date = new Date();
        date.setHours(parseInt(hours), parseInt(minutes));
        date.setMinutes(date.getMinutes() + parseInt(prevSegment.duration));
        newStartTime = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
      }

      // Create new custom segment
      const newSegment = new CustomSegment({
        id: uuidv4(),
        type: 'New segment',
        start_time: newStartTime,
        duration: '5',
      });
      newSegments.splice(index + 1, 0, newSegment);
      return { ...prev, segments: newSegments };
    });
  };

  const handleWorkbookPreview = async (e: React.FormEvent) => {
    e.preventDefault();

    const meetingData = {
      ...formData,
      segments: transformSegmentsForAPI(
        formData.segments.filter(
          (segment) =>
            segment.start_time &&
            segment.start_time.trim() !== '' &&
            segment.duration &&
            segment.duration.trim() !== ''
        )
      ),
    };

    try {
      localStorage.setItem('tempMeetingData', JSON.stringify(meetingData));
      window.open(
        '/meetings/workbook/preview',
        '_blank',
        'noopener,noreferrer'
      );
    } catch (error) {
      console.error('Error saving to localStorage:', error);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      // Validate that all segments have start_time and duration
      const invalidSegments = formData.segments.filter(
        (segment) =>
          !segment.start_time ||
          segment.start_time.trim() === '' ||
          !segment.duration ||
          segment.duration.trim() === ''
      );

      if (invalidSegments.length > 0) {
        toast.error(`${invalidSegments[0].type} has no start time or duration`);
        setIsSubmitting(false);
        return;
      }

      // Transform segments to remove UI-specific fields before sending to API
      const meetingData = {
        ...formData,
        segments: transformSegmentsForAPI(formData.segments),
      };

      if (mode === 'create') {
        meetingData.status = 'draft';

        // Create new meeting
        await createMeeting(meetingData);

        await queryClient.invalidateQueries({ queryKey: ['meetings'] });
        await queryClient.invalidateQueries({
          queryKey: ['meeting', meetingId],
        });
        await queryClient.invalidateQueries({ queryKey: ['latestMeeting'] });

        toast.success('Meeting created successfully!');

        // Redirect to meetings list after a short delay
        setTimeout(() => {
          router.push('/meetings');
        }, 1000);
      } else if (mode === 'edit' && meetingId) {
        // Update existing meeting
        await updateMeeting(meetingId, meetingData);

        await queryClient.invalidateQueries({ queryKey: ['meetings'] });
        await queryClient.invalidateQueries({
          queryKey: ['meeting', meetingId],
        });
        await queryClient.invalidateQueries({ queryKey: ['latestMeeting'] });

        toast.success('Meeting updated successfully!');
      }
    } catch (err) {
      console.error('Error saving meeting:', err);
      toast.error(
        err instanceof Error ? err.message : 'Failed to save meeting'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteClick = () => {
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = async () => {
    if (!meetingId) return;

    setIsDeleting(true);
    try {
      await deleteMeeting(meetingId);

      // Invalidate the meetings query to refresh the list
      await queryClient.invalidateQueries({ queryKey: ['meetings'] });
      await queryClient.invalidateQueries({ queryKey: ['latestMeeting'] });

      toast.success('Meeting deleted successfully!');

      // Redirect to meetings list after a short delay
      setTimeout(() => {
        router.push('/meetings');
      }, 1000);
    } catch (err) {
      console.error('Error deleting meeting:', err);
      toast.error(
        err instanceof Error ? err.message : 'Failed to delete meeting'
      );
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteConfirm(false);
  };

  const inputClasses =
    'block w-full px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';
  const inputWithIconClasses =
    'block w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';

  return (
    <form onSubmit={handleSubmit} className='px-8 pt-6 pb-14'>
      <div className='flex justify-between items-center'>
        <div>
          <h2 className='text-2xl font-semibold text-gray-900 flex items-center'>
            <PenSquare className='w-5 h-5 mr-2 text-indigo-500' />
            {mode === 'create' ? 'Create Meeting' : 'Edit Meeting'}
            <button
              type='button'
              onClick={handleWorkbookPreview}
              className='ml-4 text-xs font-medium text-fuchsia-500 hover:text-fuchsia-600 bg-fuchsia-50 hover:bg-fuchsia-100 hover:shadow-md px-2 py-1.5 rounded-full transition flex items-center gap-1'
            >
              <Table2 className='w-3 h-3' />
              <span>Table</span>
            </button>
          </h2>
          <p className='mt-1 text-sm text-gray-600'>
            {mode === 'create'
              ? 'Fill in the meeting details using our predefined template'
              : 'Update your meeting details'}
          </p>
        </div>

        {/* Delete button - only shown in edit mode AND when user can delete (admin or manager) */}
        {mode === 'edit' && meetingId && canDeleteMeeting && (
          <button
            type='button'
            disabled={isDeleting}
            onClick={handleDeleteClick}
            className='flex items-center justify-center gap-1.5 p-3 rounded-full sm:py-1.5 sm:px-3 sm:rounded-md text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed'
          >
            {isDeleting ? (
              <Loader2 className='w-4 h-4 animate-spin' />
            ) : (
              <Trash2 className='w-4 h-4' />
            )}
            <span className='hidden sm:block'>Delete Meeting</span>
          </button>
        )}
      </div>

      {/* Delete confirmation dialog */}
      {showDeleteConfirm && (
        <div className='fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50'>
          <div className='bg-white rounded-lg p-6 max-w-md mx-auto'>
            <h3 className='text-lg font-semibold text-gray-900 mb-2'>
              Confirm Delete
            </h3>
            <p className='text-gray-600 mb-4'>
              Are you sure you want to delete this meeting? This action cannot
              be undone.
            </p>
            <div className='flex justify-end gap-3'>
              <button
                type='button'
                onClick={handleDeleteCancel}
                className='px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200'
              >
                Cancel
              </button>
              <button
                type='button'
                onClick={handleDeleteConfirm}
                disabled={isDeleting}
                className='px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2'
              >
                {isDeleting && <Loader2 className='w-4 h-4 animate-spin' />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      <div className='mt-6 space-y-6'>
        {/* Basic Information */}
        <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
          {/* Meeting Type */}
          <div className='grid grid-cols-1 sm:grid-cols-2 gap-6'>
            <div>
              <label
                htmlFor='type'
                className='block text-sm font-medium text-gray-700 mb-1'
              >
                Meeting Type
              </label>
              <div className='relative'>
                <select
                  id='type'
                  value={formData.type}
                  onChange={(e) => handleInputChange('type', e.target.value)}
                  className={inputClasses}
                >
                  {MEETING_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label
                htmlFor='no'
                className='block text-sm font-medium text-gray-700 mb-1'
              >
                Meeting No.
              </label>
              <input
                type='number'
                id='no'
                value={formData.no || ''}
                onChange={(e) => handleInputChange('no', e.target.value)}
                placeholder='Enter meeting number'
                className={inputClasses}
                min='1'
                step='1'
                onKeyDown={(e) => {
                  // Prevent entering non-numeric characters
                  if (
                    !/[0-9]|\b/.test(e.key) &&
                    e.key !== 'Backspace' &&
                    e.key !== 'Delete' &&
                    e.key !== 'ArrowLeft' &&
                    e.key !== 'ArrowRight' &&
                    e.key !== 'Tab'
                  ) {
                    e.preventDefault();
                  }
                }}
                required
              />
            </div>
          </div>

          {/* Theme */}
          <div>
            <label
              htmlFor='theme'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Theme
            </label>
            <input
              type='text'
              id='theme'
              value={formData.theme}
              onChange={(e) => handleInputChange('theme', e.target.value)}
              placeholder='Enter meeting theme'
              className={inputClasses}
              required
            />
          </div>

          {/* Meeting Manager */}
          <div>
            <label
              htmlFor='manager'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Meeting Manager
            </label>
            <div className='relative'>
              <select
                id='manager'
                value={formData.manager?.member_id}
                onChange={(e) => {
                  if (e.target.value) {
                    const selectedMember = members.find(
                      (member) => member.uid === e.target.value
                    );
                    if (selectedMember) {
                      handleInputChange('manager', {
                        name: selectedMember.full_name,
                        member_id: selectedMember.uid,
                      });
                    }
                  } else {
                    handleInputChange('manager', undefined);
                  }
                }}
                className={inputWithIconClasses}
                disabled={membersLoading}
                required
              >
                <option value=''>Select a manager</option>
                {members.map((member) => (
                  <option key={member.uid} value={member.uid}>
                    {member.full_name}
                  </option>
                ))}
              </select>
              <Users className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* Date */}
          <div>
            <label
              htmlFor='date'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Date
            </label>
            <div className='relative'>
              <input
                type='date'
                id='date'
                value={formData.date}
                onChange={(e) => handleInputChange('date', e.target.value)}
                className={inputWithIconClasses}
              />
              <Calendar className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* Start Time */}
          <div>
            <label
              htmlFor='start_time'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Start Time
            </label>
            <div className='relative'>
              <input
                type='time'
                id='start_time'
                value={formData.start_time}
                onChange={(e) =>
                  handleInputChange('start_time', e.target.value)
                }
                className={inputWithIconClasses}
              />
              <Clock className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* End Time */}
          <div>
            <label
              htmlFor='end_time'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              End Time
            </label>
            <div className='relative'>
              <input
                type='time'
                id='end_time'
                value={formData.end_time}
                onChange={(e) => handleInputChange('end_time', e.target.value)}
                className={inputWithIconClasses}
              />
              <Clock className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* Location */}
          <div className='md:col-span-2'>
            <label
              htmlFor='location'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Location
            </label>
            <div className='relative'>
              <input
                type='text'
                id='location'
                value={formData.location}
                onChange={(e) => handleInputChange('location', e.target.value)}
                placeholder='Enter meeting location'
                className={inputWithIconClasses}
                required
              />
              <MapPin className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* Meeting Introduction */}
          <div className='md:col-span-2'>
            <label
              htmlFor='introduction'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Introduction
            </label>
            <div className='relative'>
              <textarea
                id='introduction'
                value={formData.introduction}
                onChange={(e) =>
                  handleInputChange('introduction', e.target.value)
                }
                placeholder='Enter meeting introduction'
                className='block w-full pl-10 pr-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200 min-h-[100px] resize-y'
              />
              <FileText className='absolute left-2.5 top-3 w-4 h-4 text-gray-400' />
            </div>
          </div>
        </div>

        {/* Segments Editor */}
        {formData.segments && formData.segments.length > 0 && (
          <div className='border-t pt-6 pb-16'>
            <h3 className='text-lg font-medium text-gray-900 mb-4'>
              Meeting Agenda
            </h3>
            <SegmentsEditor
              segments={formData.segments}
              onSegmentChange={handleSegmentChange}
              onSegmentDelete={handleSegmentDelete}
              onSegmentAdd={handleSegmentAdd}
              onSegmentsShift={handleSegmentsShift}
            />
          </div>
        )}

        {/* Single Submit Button */}
        <div className='pt-6 border-t'>
          <button
            type='submit'
            disabled={isSubmitting}
            className='w-full flex items-center justify-center gap-2 py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed'
          >
            {isSubmitting ? (
              <Loader2 className='w-4 h-4 animate-spin' />
            ) : mode === 'create' ? (
              <PlusCircle className='w-4 h-4' />
            ) : (
              <Save className='w-4 h-4' />
            )}
            {mode === 'create' ? 'Create Meeting' : 'Save Meeting'}
          </button>
        </div>
      </div>
    </form>
  );
}
