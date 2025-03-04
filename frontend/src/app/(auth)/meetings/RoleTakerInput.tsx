import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Users } from 'lucide-react';
import { AttendeeIF, UserIF } from '@/interfaces';
import { useMembers } from '@/hooks/useMember';

interface RoleTakerInputProps {
  value: AttendeeIF | undefined;
  onChange: (value: AttendeeIF) => void;
  placeholder?: string;
  className?: string;
  required?: boolean;
  disableMemberLookup?: boolean;
}

export const RoleTakerInput = ({
  value,
  onChange,
  placeholder = 'Select a role taker',
  className = '',
  required = false,
  disableMemberLookup = false,
}: RoleTakerInputProps) => {
  const membersQuery = useMembers();
  const members = membersQuery.data || [];
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value?.name || '');
  const [roleTaker, setRoleTaker] = useState<AttendeeIF | undefined>(value);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const iconRef = useRef<HTMLDivElement>(null);

  // Handle clicking outside the dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        !iconRef.current?.contains(event.target as Node)
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

    const roleTaker: AttendeeIF = {
      name: newValue,
      member_id: '',
    };

    setRoleTaker(roleTaker);
    onChange(roleTaker);
  };

  const handleMemberSelect = (member: UserIF) => {
    const selectedMember: AttendeeIF = {
      name: member.full_name,
      member_id: member.uid,
    };

    setInputValue(member.full_name);
    setRoleTaker(selectedMember);
    onChange(selectedMember);
    setIsDropdownOpen(false);
  };

  const inputWithIconClasses =
    'block w-full pl-14 pr-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';

  return (
    <div className='relative'>
      <div className={`relative ${className}`}>
        <input
          type='text'
          value={inputValue}
          onChange={handleInputChange}
          placeholder={placeholder}
          className={inputWithIconClasses}
          required={required}
        />
        <div
          className='absolute left-0 top-1/2 -translate-y-1/2 text-gray-400 cursor-pointer h-full pl-2.5 pr-2 flex items-center gap-.5 bg-gray-100 rounded-l-md scale-95'
          onClick={handleIconClick}
          ref={iconRef}
        >
          <Users className='w-4 h-4' />
          <ChevronDown
            className={`w-3 h-3 translate-y-1 transition-transform duration-200 ${
              isDropdownOpen ? 'transform rotate-180' : ''
            }`}
          />
        </div>

        {!disableMemberLookup &&
          roleTaker?.name &&
          (roleTaker?.member_id ? (
            <span className='absolute right-2 top-1/2 -translate-y-1/2 bg-indigo-50 rounded-xl px-4 py-1 text-xs text-indigo-600'>
              Member
            </span>
          ) : (
            <span className='absolute right-2 top-1/2 -translate-y-1/2 bg-emerald-50 rounded-xl px-4 py-1 text-xs text-emerald-600'>
              Guest
            </span>
          ))}
      </div>

      {isDropdownOpen && (
        <div
          ref={dropdownRef}
          className={`absolute left-0 top-full mt-1 w-full bg-gray-50 rounded-md shadow-lg border border-gray-200 z-30 ${className}`}
        >
          <div className='py-1 max-h-48 overflow-auto'>
            {members && members.length > 0 ? (
              members.map((member) => (
                <div
                  key={member.uid}
                  className='px-4 py-2 text-xs text-gray-700 hover:bg-indigo-50 hover:text-indigo-600 cursor-pointer'
                  onClick={() => handleMemberSelect(member)}
                >
                  {member.full_name}
                </div>
              ))
            ) : (
              <div className='px-4 py-2 text-xs text-gray-700'>
                No members found
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
