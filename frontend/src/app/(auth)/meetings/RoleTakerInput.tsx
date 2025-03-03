import { useState, useRef, useEffect } from 'react';
import { Users } from 'lucide-react';
import { AttendeeIF, UserIF } from '@/interfaces';
import { useMembers } from '@/hooks/useMember';

interface RoleTakerInputProps {
  value: AttendeeIF | undefined;
  onChange: (value: AttendeeIF) => void;
  placeholder?: string;
  className?: string;
}

export const RoleTakerInput = ({
  value,
  onChange,
  placeholder = 'Select a role taker',
  className = '',
}: RoleTakerInputProps) => {
  const membersQuery = useMembers();
  const members = membersQuery.data || [];
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value?.name || '');
  const [isFocused, setIsFocused] = useState(false);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Initialize display value based on existing value
  useEffect(() => {
    if (value?.name) {
      setInputValue(value.name);
    }
  }, [value?.name]);

  // Handle clicking outside the dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleIconClick = () => {
    setIsDropdownOpen(!isDropdownOpen);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setInputValue(newValue);

    // When typing manually, we're creating a guest
    onChange({
      name: newValue,
      member_id: '',
    });
  };

  const handleInputFocus = () => {
    setIsFocused(true);
  };

  const handleInputBlur = () => {
    setIsFocused(false);
  };

  const handleMemberSelect = (member: UserIF) => {
    const selectedAttendee: AttendeeIF = {
      name: member.full_name,
      member_id: member.uid,
    };

    setInputValue(member.full_name);
    onChange(selectedAttendee);
    setIsDropdownOpen(false);
  };

  // Determine the display parts for main text and suffix
  const getDisplayParts = () => {
    // When focused, just show what they're typing without suffix
    if (isFocused) {
      return { mainText: inputValue, suffix: '' };
    }
    // For members, show the name with member suffix
    else if (value?.member_id) {
      return { mainText: value.name, suffix: '• member' };
    }
    // For guests, show the name with guest suffix
    else if (value?.name) {
      return { mainText: value.name, suffix: '• guest' };
    }

    return { mainText: '', suffix: '' };
  };

  const { mainText, suffix } = getDisplayParts();

  return (
    <div className={`relative ${className}`}>
      {/* The input or display div */}
      {isFocused ? (
        <div className='relative'>
          <input
            ref={inputRef}
            type='text'
            value={inputValue}
            onChange={handleInputChange}
            onFocus={handleInputFocus}
            onBlur={handleInputBlur}
            placeholder={placeholder}
            className='w-full pl-8 pr-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500'
          />
          <div
            className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 cursor-pointer'
            onClick={handleIconClick}
          >
            <Users />
          </div>
        </div>
      ) : (
        <div className='relative'>
          <div
            className='w-full pl-8 pr-3 py-2 border border-gray-300 rounded-md cursor-text'
            onClick={() => inputRef.current?.focus()}
          >
            {mainText}
            {suffix && (
              <span className='ml-1 italic text-gray-400'>{suffix}</span>
            )}
          </div>
          <div
            className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 cursor-pointer'
            onClick={handleIconClick}
          >
            <Users />
          </div>
          {/* Hidden input for focus management */}
          <input
            ref={inputRef}
            type='text'
            value={inputValue}
            onChange={handleInputChange}
            onFocus={handleInputFocus}
            className='absolute top-0 left-0 w-full h-full opacity-0 cursor-text'
          />
        </div>
      )}

      {/* Dropdown menu */}
      {isDropdownOpen && (
        <div
          ref={dropdownRef}
          className='absolute z-10 w-full mt-1 left-0 right-0 max-h-60 overflow-auto bg-white border border-gray-300 rounded-md shadow-lg'
          style={{ top: '100%' }}
        >
          {members && members.length > 0 ? (
            members.map((member) => (
              <div
                key={member.uid}
                className='px-4 py-2 text-sm hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer'
                onClick={() => handleMemberSelect(member)}
              >
                {member.full_name}
              </div>
            ))
          ) : (
            <div className='px-4 py-2 text-sm text-gray-500'>
              No members found
            </div>
          )}
        </div>
      )}
    </div>
  );
};
