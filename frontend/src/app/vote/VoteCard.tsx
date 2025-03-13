import React from 'react';
import { CategoryCandidatesIF } from '@/interfaces';

interface VoteCardProps {
  category: CategoryCandidatesIF;
  selectedCandidate: string;
  onSelectCandidate: (candidateName: string) => void;
  disabled?: boolean;
}

export function VoteCard({
  category,
  selectedCandidate,
  onSelectCandidate,
  disabled = false,
}: VoteCardProps) {
  // Filter out candidates with no name
  const validCandidates = category.candidates.filter((c) => c.name);

  // Don't render if no valid candidates
  if (validCandidates.length === 0) {
    return null;
  }

  return (
    <div className='bg-white shadow-md rounded-lg overflow-hidden border border-gray-200'>
      <div className='bg-gradient-to-r from-indigo-600 to-purple-600 px-4 py-3 text-white'>
        <h3 className='font-semibold'>{category.category}</h3>
      </div>

      <div className='p-4'>
        <div className='space-y-2'>
          {validCandidates.map((candidate, index) => (
            <label
              key={index}
              className={`flex items-center p-3 rounded-md cursor-pointer transition-colors ${
                selectedCandidate === candidate.name
                  ? 'bg-indigo-50 border border-indigo-200'
                  : 'hover:bg-gray-50 border border-transparent'
              } ${disabled ? 'opacity-70 cursor-not-allowed' : ''}`}
            >
              <input
                type='radio'
                name={`category-${category.category}`}
                value={candidate.name}
                checked={selectedCandidate === candidate.name}
                onChange={() => onSelectCandidate(candidate.name)}
                disabled={disabled}
                required
                className='h-4 w-4 text-indigo-600 border-gray-300 focus:ring-indigo-500 disabled:opacity-50'
              />
              <div className='ml-3 flex-grow'>
                <span className='block text-sm font-medium text-gray-800'>
                  {candidate.name}
                </span>
                {candidate.segment && (
                  <span className='block text-xs text-gray-500 mt-0.5'>
                    {candidate.segment}
                  </span>
                )}
              </div>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
