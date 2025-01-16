import React, { useState } from 'react';
import { UserPlus, Users } from 'lucide-react';
import { UserIF } from '@/interfaces';

export type AwardCategory =
  | 'Best Prepared Speaker'
  | 'Best Host'
  | 'Best Table Topic Speaker'
  | 'Best Facilitator'
  | 'Best Evaluator'
  | 'Best Supporter'
  | 'Custom Award';

const AWARD_CATEGORIES: AwardCategory[] = [
  'Best Prepared Speaker',
  'Best Host',
  'Best Table Topic Speaker',
  'Best Facilitator',
  'Best Evaluator',
  'Best Supporter',
];

export interface AwardSelection {
  category: AwardCategory;
  memberId: string;
  date: string;
  customTitle?: string;
}

const AwardSelect = ({
  label,
  value,
  members,
  onChange,
  isCustom,
  onCustomTitleChange,
}: {
  label: string;
  value: string;
  members: UserIF[];
  onChange: (value: string) => void;
  isCustom?: boolean;
  onCustomTitleChange?: (title: string) => void;
}) => {
  const [isEditMode, setIsEditMode] = useState(false);
  const [customName, setCustomName] = useState('');
  const [customTitle, setCustomTitle] = useState('');

  const handleEditToggle = () => {
    setCustomName(''); // clear the custom name
    onChange(''); // clear the selection
    setIsEditMode(!isEditMode);
  };

  const handleCustomNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newName = e.target.value;
    setCustomName(newName);
    // Update the value immediately as user types
    onChange(newName);
  };

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setCustomName('');
    onChange(e.target.value);
  };

  return (
    <div>
      <div className='flex items-center gap-2'>
        {isCustom ? (
          <input
            type='text'
            value={customTitle}
            onChange={(e) => {
              setCustomTitle(e.target.value);
              onCustomTitleChange?.(e.target.value);
            }}
            className='block w-full border-0 border-b border-gray-300 focus:border-blue-500 focus:ring-0 focus:outline-none text-sm font-medium text-gray-700 bg-transparent'
            placeholder='Enter custom award title...'
          />
        ) : (
          <label
            htmlFor={label}
            className='block text-sm font-medium text-gray-700'
          >
            {label}
          </label>
        )}
      </div>
      <div className='mt-1 flex items-center gap-2'>
        {isEditMode ? (
          <input
            id={label}
            type='text'
            value={customName}
            onChange={handleCustomNameChange}
            className='block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'
            placeholder='Enter name...'
          />
        ) : (
          <select
            id={label}
            value={value}
            onChange={handleSelectChange}
            className='block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'
          >
            <option value=''>Select a member</option>
            {members.map((member) => (
              <option key={member.uid} value={member.uid}>
                {member.full_name}
              </option>
            ))}
          </select>
        )}
        <button
          type='button'
          onClick={handleEditToggle}
          className='p-2 text-gray-500 hover:text-blue-500 rounded-md hover:bg-gray-50 flex items-center gap-1'
          title={isEditMode ? 'Switch to member selection' : 'Add non-member'}
        >
          {isEditMode ? (
            <>
              <Users size={18} />
              <span className='sr-only'>Switch to member selection</span>
            </>
          ) : (
            <>
              <UserPlus size={18} />
              <span className='sr-only'>Add non-member</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export const AwardForm = ({
  members,
  onSubmit,
}: {
  members: UserIF[];
  onSubmit: (selections: AwardSelection[]) => void;
}) => {
  const today = new Date().toISOString().split('T')[0];
  const [selectedDate, setSelectedDate] = useState(today);
  const [selections, setSelections] = useState<AwardSelection[]>([
    ...AWARD_CATEGORIES.map((category) => ({
      category,
      memberId: '',
      date: today,
    })),
    {
      category: 'Custom Award',
      memberId: '',
      date: today,
    },
  ]);

  const handleSelectionChange = (category: AwardCategory, value: string) => {
    setSelections((prev) =>
      prev.map((sel) =>
        sel.category === category ? { ...sel, memberId: value } : sel
      )
    );
  };

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setSelectedDate(newDate);
    setSelections((prev) => prev.map((sel) => ({ ...sel, date: newDate })));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(selections.filter((sel) => sel.memberId));
  };

  return (
    <form onSubmit={handleSubmit} className='space-y-6'>
      <div>
        <label
          htmlFor='awardDate'
          className='block text-sm font-medium text-gray-700'
        >
          Award Date
        </label>
        <input
          type='date'
          id='awardDate'
          value={selectedDate}
          onChange={handleDateChange}
          className='mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500'
        />
      </div>

      {AWARD_CATEGORIES.map((category) => (
        <AwardSelect
          key={category}
          label={category}
          value={
            selections.find((s) => s.category === category)?.memberId || ''
          }
          members={members}
          onChange={(value) => handleSelectionChange(category, value)}
        />
      ))}

      <AwardSelect
        key='custom'
        label='Custom Award'
        value={
          selections.find((s) => s.category === 'Custom Award')?.memberId || ''
        }
        members={members}
        onChange={(value) => handleSelectionChange('Custom Award', value)}
        isCustom={true}
        onCustomTitleChange={(title) =>
          setSelections((prev) =>
            prev.map((sel) =>
              sel.category === 'Custom Award'
                ? { ...sel, customTitle: title }
                : sel
            )
          )
        }
      />

      <button
        type='submit'
        className='w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2'
      >
        Generate Awards
      </button>
    </form>
  );
};
