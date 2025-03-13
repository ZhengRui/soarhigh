'use client';

import React, { useState } from 'react';
import { useVoteForm } from '@/hooks/votes/useVoteForm';
import { useVoteStatus } from '@/hooks/votes/useVoteStatus';
import { useLatestMeeting } from '@/hooks/useLatestMeeting';
import { useSubmitVote } from '@/hooks/votes/useSubmitVote';
import { CategoryCandidatesIF, VoteRecordIF } from '@/interfaces';
import { Loader2, Vote as VoteIcon, AlertCircle } from 'lucide-react';
import { VoteCard } from './VoteCard';
import toast from 'react-hot-toast';

export function VotingPage() {
  // State for selected votes
  const [selectedVotes, setSelectedVotes] = useState<Record<string, string>>(
    {}
  );

  // Fetch the latest meeting
  const { data: latestMeeting, isLoading: isLoadingMeeting } =
    useLatestMeeting();

  // Fetch vote form and status based on the latest meeting
  const { data: voteForm, isLoading: isLoadingVoteForm } = useVoteForm(
    latestMeeting?.id || '',
    true
  );

  const { data: voteStatus, isLoading: isLoadingVoteStatus } = useVoteStatus(
    latestMeeting?.id || ''
  );

  // Mutation for submitting votes
  const { mutateAsync: submitVote, isPending: isSubmitting } = useSubmitVote();

  // Handle selection of a candidate for a category
  const handleSelectCandidate = (category: string, candidateName: string) => {
    setSelectedVotes((prev) => ({
      ...prev,
      [category]: candidateName,
    }));
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!latestMeeting?.id) {
      toast.error('No active meeting found');
      return;
    }

    if (!voteStatus?.open) {
      toast.error('Voting is currently closed');
      return;
    }

    try {
      // Convert selected votes to array of vote records
      const voteRecords: VoteRecordIF[] = Object.entries(selectedVotes).map(
        ([category, name]) => ({
          category,
          name,
        })
      );

      // Don't submit if no votes are selected
      if (voteRecords.length === 0) {
        toast.error('Please select at least one vote');
        return;
      }

      // Submit votes
      await submitVote({
        meetingId: latestMeeting.id,
        votes: voteRecords,
      });

      // Show success message
      toast.success('Your votes have been submitted!');

      // Reset form
      // setSelectedVotes({});
    } catch (error) {
      console.error('Error submitting votes:', error);
      toast.error('Failed to submit votes. Please try again.');
    }
  };

  const isLoading =
    isLoadingMeeting || isLoadingVoteForm || isLoadingVoteStatus;

  if (isLoading) {
    return (
      <div className='flex justify-center items-center min-h-[80vh]'>
        <Loader2 className='w-8 h-8 animate-spin text-indigo-600' />
      </div>
    );
  }

  if (!latestMeeting) {
    return (
      <div className='max-w-3xl mx-auto px-4 py-12'>
        <div className='bg-yellow-50 border border-yellow-200 rounded-lg p-6 flex items-start gap-3'>
          <AlertCircle className='w-5 h-5 text-yellow-500 mt-0.5 flex-shrink-0' />
          <div>
            <h2 className='text-lg font-semibold text-yellow-800 mb-2'>
              No Meeting Available
            </h2>
            <p className='text-yellow-700'>
              There are no active meetings to vote on at this time. Please check
              back later.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!voteForm || voteForm.length === 0) {
    return (
      <div className='max-w-3xl mx-auto px-4 py-12'>
        <div className='bg-yellow-50 border border-yellow-200 rounded-lg p-6 flex items-start gap-3'>
          <AlertCircle className='w-5 h-5 text-yellow-500 mt-0.5 flex-shrink-0' />
          <div>
            <h2 className='text-lg font-semibold text-yellow-800 mb-2'>
              No Voting Categories
            </h2>
            <p className='text-yellow-700'>
              The voting categories haven&apos;t been set up for this meeting
              yet. Please check back later.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className='max-w-3xl mx-auto px-4 py-8 md:py-12'>
      <div className='mb-6 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between'>
        <div>
          <h1 className='text-2xl md:text-3xl font-bold text-gray-800 flex items-center gap-2'>
            <VoteIcon className='w-6 h-6 text-indigo-600' />
            Cast Your Votes
          </h1>
          <p className='text-gray-600 mt-1'>
            Meeting #{latestMeeting.no}: {latestMeeting.theme}
          </p>
        </div>
        <div className='bg-indigo-50 py-1.5 px-3 rounded-md'>
          <p className='text-sm font-medium text-indigo-700'>
            Voting is {voteStatus?.open ? 'Open' : 'Closed'}
          </p>
        </div>
      </div>

      {!voteStatus?.open && (
        <div className='mb-6 p-4 bg-red-50 border border-red-100 rounded-md'>
          <p className='text-sm text-red-600'>
            Voting is currently closed. You can review the categories, but votes
            cannot be submitted.
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className='grid grid-cols-1 gap-6'>
          {voteForm.map((category: CategoryCandidatesIF) => (
            <VoteCard
              key={category.category}
              category={category}
              selectedCandidate={selectedVotes[category.category] || ''}
              onSelectCandidate={(candidateName: string) =>
                handleSelectCandidate(category.category, candidateName)
              }
              disabled={!voteStatus?.open}
            />
          ))}
        </div>

        <div className='mt-12'>
          <button
            type='submit'
            disabled={isSubmitting || !voteStatus?.open}
            className='w-full flex items-center justify-center gap-2 py-3 px-4 bg-indigo-600 text-white rounded-md font-medium hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors'
          >
            {isSubmitting ? (
              <Loader2 className='w-5 h-5 animate-spin' />
            ) : (
              <VoteIcon className='w-5 h-5' />
            )}
            {voteStatus?.open ? 'Submit Votes' : 'Voting is Closed'}
          </button>
        </div>
      </form>
    </div>
  );
}
