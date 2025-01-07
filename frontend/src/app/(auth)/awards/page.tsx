'use client';

import React, { useState } from 'react';
import { AwardResult, AwardPreview } from './AwardPreview';
import { AwardSelection, AwardForm } from './AwardForm';
import { useMembers } from '@/hooks/useMember';

export default function AwardsPage() {
  const [awards, setAwards] = useState<AwardResult[]>([]);
  const { data: members } = useMembers();

  const handleSubmit = (selections: AwardSelection[]) => {
    const results = selections.map((selection) => {
      // Check if the selection is a member ID
      const member = members?.find((m) => m.uid === selection.memberId);

      if (member) {
        // If it's a member ID, use the member's data
        return {
          category: selection.category,
          member: member,
        };
      } else {
        // If it's not a member ID, treat the memberId as a custom name
        return {
          category: selection.category,
          member: {
            uid: selection.memberId,
            username: selection.memberId,
            full_name: selection.memberId,
          },
        };
      }
    });
    setAwards(results);
  };

  return (
    <div className='min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8'>
      <div className='max-w-7xl mx-auto'>
        <div className='text-center mb-12'>
          <h1 className='text-3xl font-bold text-gray-900'>SoarHigh Awards</h1>
          <p className='mt-2 text-gray-600'>
            Recognize outstanding speakers and celebrate excellence
          </p>
        </div>

        <div className='grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12'>
          <div className='bg-white p-6 rounded-lg shadow-sm'>
            <h2 className='text-xl font-semibold mb-6'>Generate Awards</h2>
            <AwardForm members={members || []} onSubmit={handleSubmit} />
          </div>

          <div className='space-y-8'>
            {awards.length > 0 && (
              <div className='bg-white p-6 rounded-lg shadow-sm'>
                <h2 className='text-xl font-semibold mb-6'>Award Previews</h2>
                <div className='space-y-8'>
                  {awards.map((award) => (
                    <AwardPreview key={award.category} award={award} />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
