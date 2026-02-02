'use client';

import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  Clock,
  MapPin,
  Trophy,
  PencilLine,
  Eye,
  EyeOff,
  Loader2,
  Table2,
  ImageIcon,
  ClipboardList,
  Timer,
  Bell,
} from 'lucide-react';
import { MeetingIF, TimingIF } from '@/interfaces';
import Link from 'next/link';
import Image from 'next/image';
import { updateMeetingStatus } from '@/utils/meeting';
import toast from 'react-hot-toast';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { listMeetingMedia, MediaFile } from '@/utils/alicloud';
import { TimerTab } from '@/app/(auth)/meetings/TimerTab';
import {
  getTimings,
  getTimingsForSegment,
  getTimingTooltip,
  dotColors,
} from '@/utils/timing';

type MeetingCardProps = {
  meeting: MeetingIF;
  isAuthenticated: boolean;
};

export const MeetingCard: React.FC<MeetingCardProps> = ({
  meeting,
  isAuthenticated,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'agenda' | 'photos' | 'timer'>(
    'agenda'
  );
  const [mediaFiles, setMediaFiles] = useState<MediaFile[]>([]);
  const [isMediaLoading, setIsMediaLoading] = useState(false);
  const [mediaFetched, setMediaFetched] = useState(false);
  const [timings, setTimings] = useState<TimingIF[]>([]);
  const [timingsFetched, setTimingsFetched] = useState(false);
  const [selectedImageIndex, setSelectedImageIndex] = useState<number | null>(
    null
  );
  // Timing popover state
  const [popoverTiming, setPopoverTiming] = useState<TimingIF | null>(null);
  const [popoverPosition, setPopoverPosition] = useState({ top: 0, left: 0 });
  const popoverRef = useRef<HTMLDivElement>(null);

  const queryClient = useQueryClient();

  // Destructure the meeting object
  const {
    id,
    type,
    no,
    theme,
    manager,
    date,
    start_time,
    end_time,
    location,
    introduction,
    segments,
    status,
    awards,
  } = meeting;

  // Check if the meeting date has passed
  // const hasPassed = new Date(date) < new Date();
  const hasPassed = true;

  // Fetch media files when the Photos tab is selected for the first time
  useEffect(() => {
    const fetchMediaFiles = async () => {
      // Only fetch if we're on the photos tab, the card is expanded, and we haven't fetched before
      if (isExpanded && activeTab === 'photos' && id && !mediaFetched) {
        setIsMediaLoading(true);
        try {
          const response = await listMeetingMedia(id);
          setMediaFiles(response.items);
          setMediaFetched(true); // Mark that we've fetched the data
        } catch (error) {
          console.error('Error fetching media files:', error);
          toast.error('Failed to load meeting images');
        } finally {
          setIsMediaLoading(false);
        }
      }
    };

    fetchMediaFiles();
  }, [isExpanded, activeTab, id, mediaFetched]);

  // Fetch timings when the card is expanded (for Agenda view dots)
  useEffect(() => {
    if (!isExpanded || !id || timingsFetched) return;

    const fetchTimings = async () => {
      try {
        const response = await getTimings(id);
        setTimings(response.timings);
        setTimingsFetched(true);
      } catch (error) {
        console.error('Error fetching timings:', error);
      }
    };

    fetchTimings();
  }, [isExpanded, id, timingsFetched]);

  // Close timing popover when clicking outside or scrolling
  useEffect(() => {
    if (!popoverTiming) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        setPopoverTiming(null);
      }
    };

    const handleScroll = () => {
      setPopoverTiming(null);
    };

    document.addEventListener('mousedown', handleClickOutside);
    window.addEventListener('scroll', handleScroll, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('scroll', handleScroll, true);
    };
  }, [popoverTiming]);

  // Close popover when card collapses
  useEffect(() => {
    if (!isExpanded) {
      setPopoverTiming(null);
    }
  }, [isExpanded]);

  // Use mutation for toggling status
  const statusMutation = useMutation({
    mutationFn: (newStatus: string) => updateMeetingStatus(id, newStatus),
    onSuccess: () => {
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['meetings'] });

      const newStatus = status === 'published' ? 'draft' : 'published';
      meeting.status = newStatus;
      toast.success(
        newStatus === 'published'
          ? 'Meeting published successfully!'
          : 'Meeting unpublished successfully!'
      );
    },
    onError: (err) => {
      console.error('Error toggling meeting status:', err);
      toast.error(
        err instanceof Error ? err.message : 'Failed to update meeting status'
      );
    },
  });

  const handlePublishToggle = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!id || !isAuthenticated || statusMutation.isPending) return;

    const newStatus = status === 'published' ? 'draft' : 'published';
    statusMutation.mutate(newStatus);
  };

  return (
    <div className='bg-white rounded-xl shadow-lg overflow-hidden transition-all duration-200 ease-in-out hover:shadow-xl border border-[#e5e7eb]'>
      <div
        className='p-6 cursor-pointer group relative'
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className='flex justify-between items-start mb-4'>
          <div>
            <div className='flex items-center gap-2'>
              <span className='px-4 py-1 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-full text-sm font-medium'>
                {type}
              </span>

              <span className='text-xs font-medium text-fuchsia-500 hover:text-fuchsia-600 bg-fuchsia-50 hover:bg-fuchsia-100 hover:shadow-md px-2 py-1.5 rounded-full transition'>
                #{no}
              </span>

              {isAuthenticated && id && (
                <>
                  <button
                    onClick={handlePublishToggle}
                    disabled={statusMutation.isPending}
                    className={`rounded-full p-1.5 transition hover:shadow-md ${
                      status === 'published'
                        ? 'bg-emerald-50 text-emerald-500 hover:bg-emerald-100 hover:text-emerald-600'
                        : 'bg-red-50 text-red-500 hover:bg-red-100 hover:text-red-600'
                    }`}
                    title={
                      status === 'published'
                        ? 'Unpublish meeting'
                        : 'Publish meeting'
                    }
                  >
                    {statusMutation.isPending ? (
                      <Loader2 className='w-4 h-4 animate-spin' />
                    ) : status === 'published' ? (
                      <Eye className='w-4 h-4' />
                    ) : (
                      <EyeOff className='w-4 h-4' />
                    )}
                  </button>

                  <Link
                    href={`/meetings/edit/${id}`}
                    className='rounded-full p-1.5 bg-indigo-50 hover:bg-indigo-100 transition hover:shadow-md'
                    onClick={(e) => e.stopPropagation()}
                    title='Edit meeting'
                  >
                    <PencilLine className='w-4 h-4 text-indigo-500 hover:text-indigo-600' />
                  </Link>
                </>
              )}
            </div>

            <h2 className='text-2xl font-bold mt-3 text-gray-800'>{theme}</h2>
            <p className='text-gray-500 mt-1 text-sm'>
              Managed by {manager?.name}
            </p>
          </div>

          {isExpanded ? (
            <ChevronUp className='w-5 h-5 text-gray-400' />
          ) : (
            <ChevronDown className='w-5 h-5 text-gray-400' />
          )}
        </div>

        <div className='flex flex-col gap-2 text-gray-500 text-sm'>
          <p className='flex items-center gap-2'>
            <Clock className='min-w-4 min-h-4 w-4 h-4' />
            {date} | {start_time} - {end_time}
          </p>
          <p className='flex items-center gap-2'>
            <MapPin className='min-w-4 min-h-4 w-4 h-4' />
            {location}
          </p>
        </div>

        <p className='mt-4 text-sm text-gray-500 leading-relaxed'>
          {introduction}
        </p>

        {hasPassed && awards && awards.length > 0 && (
          <div className='mt-6 pt-6 border-t border-dashed border-gray-300'>
            <div className='flex items-center gap-2 mb-3'>
              <Trophy className='w-4 h-4 text-indigo-600' />
              <h3 className='text-sm font-semibold text-gray-800'>Awards</h3>
            </div>
            <div className='grid grid-cols-2 md:grid-cols-3 gap-4'>
              {awards.map((award, index: number) => (
                <div key={index} className='text-sm'>
                  <p className='text-gray-500 font-medium'>{award.category}</p>
                  <p className='text-indigo-600'>{award.winner}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isExpanded ? 'max-h-[4000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className='p-6 border-t border-gray-300 bg-gradient-to-b from-white to-[#F9FAFB]'>
          {/* Hide scrollbar CSS */}
          <style>{`.hide-scrollbar::-webkit-scrollbar { display: none; }`}</style>
          {/* Tab buttons */}
          <div
            className='hide-scrollbar flex space-x-4 mb-6 min-w-0 overflow-x-auto'
            style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
          >
            <button
              onClick={() => setActiveTab('agenda')}
              className={`px-4 py-2 text-sm font-semibold text-gray-500 flex items-center gap-2 rounded-xl border border-dashed border-1 transition-all duration-300 min-w-40 ${
                activeTab === 'agenda'
                  ? 'text-gray-800 border-gray-400'
                  : 'border-transparent hover:text-gray-800 hover:border-gray-400'
              }`}
            >
              <ClipboardList className='w-4 h-4 text-indigo-600' />
              Agenda
              <Link
                href={`/meetings/workbook/${id}`}
                className='ml-1 text-xs font-medium text-fuchsia-500 hover:text-fuchsia-600 bg-fuchsia-50 hover:bg-fuchsia-100 hover:shadow-md px-2 py-1.5 rounded-full transition flex items-center gap-1'
                onClick={(e) => e.stopPropagation()}
                target='_blank'
                rel='noopener noreferrer'
              >
                <Table2 className='w-3 h-3' />
                <span>Table</span>
              </Link>
            </button>
            <button
              onClick={() => setActiveTab('photos')}
              className={`px-4 py-2 text-sm font-semibold text-gray-500 flex items-center gap-2 rounded-xl border border-dashed border-1 transition-all duration-300 ${
                activeTab === 'photos'
                  ? 'text-gray-800 border-gray-400'
                  : 'border-transparent hover:text-gray-800 hover:border-gray-400'
              }`}
            >
              <ImageIcon className='w-4 h-4 text-indigo-600' />
              Photos
            </button>
            {isAuthenticated && (
              <button
                onClick={() => setActiveTab('timer')}
                className={`px-4 py-2 text-sm font-semibold text-gray-500 flex items-center gap-2 rounded-xl border border-dashed border-1 transition-all duration-300 ${
                  activeTab === 'timer'
                    ? 'text-gray-800 border-gray-400'
                    : 'border-transparent hover:text-gray-800 hover:border-gray-400'
                }`}
              >
                <Timer className='w-4 h-4 text-indigo-600' />
                Timer
              </button>
            )}
          </div>

          {/* Agenda Tab Content */}
          <div className={`${activeTab === 'agenda' ? 'block' : 'hidden'}`}>
            <div className='space-y-6 sm:space-y-4'>
              {segments.map((segment) => {
                const segmentTimings = getTimingsForSegment(
                  timings,
                  segment.id
                );
                const latestTiming =
                  segmentTimings.length > 0
                    ? segmentTimings[segmentTimings.length - 1]
                    : null;

                return (
                  <div
                    key={segment.id}
                    className='flex flex-col sm:flex-row gap-1 sm:gap-4 relative mb-4'
                  >
                    <div className='w-full sm:pt-1 sm:w-24 flex-shrink-0 flex sm:flex-col items-center sm:items-start justify-between'>
                      <div className='flex sm:flex-col items-center sm:items-start gap-2 sm:gap-0'>
                        <span className='text-sm font-medium text-indigo-600'>
                          {segment.start_time}
                        </span>
                        <span className='text-xs text-gray-500 flex items-center gap-1'>
                          {segment.duration}min
                          {latestTiming && (
                            <button
                              type='button'
                              className='inline-flex items-center justify-center w-4 h-4'
                              title={getTimingTooltip(latestTiming)}
                              onClick={(e) => {
                                e.stopPropagation();
                                if (popoverTiming?.id === latestTiming.id) {
                                  setPopoverTiming(null);
                                } else {
                                  const rect =
                                    e.currentTarget.getBoundingClientRect();
                                  setPopoverPosition({
                                    top: rect.bottom + 4,
                                    left: rect.left,
                                  });
                                  setPopoverTiming(latestTiming);
                                }
                              }}
                            >
                              {latestTiming.dot_color === 'bell' ? (
                                <Bell className='w-3 h-3 text-red-600 fill-red-600' />
                              ) : (
                                <span
                                  className={`w-2 h-2 rounded-full ${dotColors[latestTiming.dot_color]}`}
                                />
                              )}
                            </button>
                          )}
                        </span>
                      </div>
                    </div>
                    <div className='flex-grow'>
                      <div className='flex flex-col'>
                        <h4 className='font-medium text-gray-800'>
                          {segment.type}
                        </h4>
                        <p className='text-sm text-gray-500'>
                          {segment.role_taker?.name ||
                            (segment.type.toLowerCase() ===
                              'table topic session' ||
                            segment.type.toLowerCase().includes('tea break') ||
                            segment.type.toLowerCase().includes('registration')
                              ? 'All'
                              : '')}
                          {segment.type.toLowerCase() === 'table topic session'
                            ? segment.content && ` - ${segment.content}`
                            : segment.title && ` - ${segment.title}`}
                        </p>
                      </div>
                    </div>
                    <div className='hidden sm:block absolute left-24 top-0 bottom-0 w-0.5 bg-gradient-to-b from-indigo-600 to-purple-600 -z-10' />
                  </div>
                );
              })}
            </div>
          </div>

          {/* Photos Tab Content */}
          <div className={`${activeTab === 'photos' ? 'block' : 'hidden'}`}>
            {isMediaLoading ? (
              <div className='bg-gray-50 border border-dashed border-gray-300 rounded-lg p-8 flex items-center justify-center'>
                <div className='text-center text-gray-500'>
                  <Loader2 className='w-12 h-12 mx-auto mb-2 text-gray-300 animate-spin' />
                  <p>Loading meeting photos...</p>
                </div>
              </div>
            ) : mediaFiles.length === 0 ? (
              <div className='bg-gray-50 border border-dashed border-gray-300 rounded-lg p-8 flex items-center justify-center'>
                <div className='text-center text-gray-500'>
                  <ImageIcon className='w-12 h-12 mx-auto mb-2 text-gray-300' />
                  <p>No photos for this meeting</p>
                </div>
              </div>
            ) : (
              <div className='grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4'>
                {mediaFiles.map((image, index) => (
                  <div
                    key={index}
                    className='relative aspect-square rounded-lg overflow-hidden border border-gray-200 group shadow-sm hover:shadow-md transition-all duration-300 cursor-pointer'
                    onClick={() => setSelectedImageIndex(index)}
                  >
                    <Image
                      src={image.url}
                      alt={image.filename}
                      fill
                      className='object-cover'
                      sizes='(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw'
                    />
                    <div className='absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-40 transition-all duration-300 flex items-end'>
                      <div className='p-2 w-full text-white text-xs truncate opacity-0 group-hover:opacity-100 transition-opacity duration-300'>
                        {image.filename}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Timer Tab Content */}
          {isAuthenticated && id && activeTab === 'timer' && (
            <TimerTab meetingId={id} segments={segments} />
          )}
        </div>
      </div>

      {/* Timing Popover - rendered via portal */}
      {popoverTiming &&
        typeof window !== 'undefined' &&
        createPortal(
          <div
            ref={popoverRef}
            className='fixed z-[9999] bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2'
            style={{
              top: popoverPosition.top,
              left: popoverPosition.left,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className='text-xs text-gray-700 whitespace-nowrap'>
              {getTimingTooltip(popoverTiming)}
            </div>
          </div>,
          document.body
        )}

      {/* Lightbox Modal */}
      {selectedImageIndex !== null && mediaFiles.length > 0 && (
        <div
          className='fixed inset-0 bg-black bg-opacity-90 z-50 flex items-center justify-center'
          onClick={() => setSelectedImageIndex(null)}
        >
          <div className='relative max-w-full max-h-[100vh] w-full flex items-center justify-center'>
            {/* Image container */}
            <div
              className='relative'
              style={{ maxHeight: '90vh', maxWidth: '90vw' }}
            >
              <Image
                src={mediaFiles[selectedImageIndex].url}
                alt={mediaFiles[selectedImageIndex].filename}
                width={1200}
                height={800}
                className='object-contain max-h-[90vh]'
                sizes='90vw'
                style={{ maxHeight: '90vh', maxWidth: '90vw' }}
              />

              {/* Info overlay at bottom */}
              <div className='absolute bottom-0 left-0 right-0 bg-black bg-opacity-60 text-white p-3'>
                <p className='text-sm font-medium truncate'>
                  {mediaFiles[selectedImageIndex].filename}
                </p>
                <p className='text-xs opacity-75'>
                  {new Date(
                    mediaFiles[selectedImageIndex].uploadedAt
                  ).toLocaleString()}
                </p>
              </div>
            </div>

            {/* Navigation buttons */}
            {mediaFiles.length > 1 && (
              <>
                {/* Previous button */}
                <button
                  className='absolute left-4 p-3 text-white bg-black bg-opacity-50 rounded-full hover:bg-opacity-70 transition-all'
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedImageIndex((prev) =>
                      prev !== null
                        ? prev === 0
                          ? mediaFiles.length - 1
                          : prev - 1
                        : 0
                    );
                  }}
                >
                  <ChevronLeft className='w-6 h-6' />
                </button>

                {/* Next button */}
                <button
                  className='absolute right-4 p-3 text-white bg-black bg-opacity-50 rounded-full hover:bg-opacity-70 transition-all'
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedImageIndex((prev) =>
                      prev !== null
                        ? prev === mediaFiles.length - 1
                          ? 0
                          : prev + 1
                        : 0
                    );
                  }}
                >
                  <ChevronRight className='w-6 h-6' />
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
