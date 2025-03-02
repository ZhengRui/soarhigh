'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Menu, X, LogOut, ChevronDown } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useQueryClient } from '@tanstack/react-query';

const NavLink = ({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) => {
  const path = usePathname();
  const isActive = path === href;

  return (
    <Link
      href={href}
      className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 block
          ${
            isActive
              ? 'bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-md'
              : 'text-gray-700 hover:bg-gray-50 hover:shadow-sm hover:scale-105'
          }`}
    >
      {children}
    </Link>
  );
};

const MobileMenu = ({
  isOpen,
  onToggle,
  onSignOut,
}: {
  isOpen: boolean;
  onToggle: () => void;
  onSignOut: () => void;
}) => {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        onToggle();
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onToggle]);

  const { data: user } = useAuth();
  return (
    <div className='md:hidden' ref={menuRef}>
      <button
        onClick={onToggle}
        className='p-2 rounded-md text-gray-700 hover:bg-gray-100'
      >
        {isOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      {isOpen && (
        <div className='absolute top-16 left-0 right-0 bg-white shadow-lg border-b border-gray-100'>
          <div className='max-w-7xl mx-auto py-2 px-4 sm:px-6 lg:px-8 flex flex-col space-y-2'>
            <NavLink href='/'>Introduction</NavLink>
            <NavLink href='/meetings'>Meetings</NavLink>
            {user ? (
              <>
                <div className='pl-4 space-y-2'>
                  <div className='text-sm font-medium text-gray-500'>
                    Operations
                  </div>
                  <NavLink href='/growth'>Growth</NavLink>
                  <NavLink href='/awards'>Awards</NavLink>
                </div>
                <button
                  onClick={onSignOut}
                  className='flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 rounded-full'
                >
                  <LogOut size={18} />
                  <span>Sign Out</span>
                </button>
              </>
            ) : (
              <NavLink href='/signin'>Sign In</NavLink>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

const Header = () => {
  const [isOpen, setIsOpen] = useState(false);

  const { data: user } = useAuth();

  const queryClient = useQueryClient();

  const signout = () => {
    localStorage.removeItem('token');
    queryClient.invalidateQueries({ queryKey: ['whoami'] });
    queryClient.invalidateQueries({ queryKey: ['isAdmin'] });
  };

  return (
    <nav className='bg-white/80 backdrop-blur-sm shadow-lg border-b border-gray-100 sticky top-0 z-50'>
      <div className='max-w-7xl mx-auto px-4 sm:px-6 lg:px-8'>
        <div className='flex justify-between h-16 sm:h-20 items-center'>
          <Link href='/'>
            <div className='flex flex-col justify-center group cursor-pointer'>
              <span className='text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent font-serif transform transition-transform group-hover:scale-105'>
                SoarHigh
              </span>
              <span className='text-xs sm:text-sm font-medium tracking-widest uppercase bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent transform transition-all group-hover:tracking-[0.2em]'>
                Toast Masters Club
              </span>
            </div>
          </Link>

          <div className='hidden md:flex items-center space-x-2 lg:space-x-6'>
            <NavLink href='/'>Introduction</NavLink>
            <NavLink href='/meetings'>Meetings</NavLink>
            {user ? (
              <>
                <div className='relative group'>
                  <div className='flex items-center gap-1 px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900 cursor-pointer'>
                    Operations
                    <ChevronDown
                      size={16}
                      className={`transform transition-transform group-hover:rotate-180`}
                    />
                  </div>
                  <div className='absolute top-full right-0 mt-1 w-48 bg-white rounded-xl shadow-lg px-4 py-2 flex flex-col space-y-2 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200'>
                    <NavLink href='/growth'>Growth</NavLink>
                    <NavLink href='/awards'>Awards</NavLink>
                  </div>
                </div>
                <button
                  onClick={signout}
                  className='flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900'
                >
                  <LogOut size={18} />
                  <span>Sign Out</span>
                </button>
              </>
            ) : (
              <NavLink href='/signin'>Sign In</NavLink>
            )}
          </div>

          <MobileMenu
            isOpen={isOpen}
            onToggle={() => setIsOpen(!isOpen)}
            onSignOut={signout}
          />
        </div>
      </div>
    </nav>
  );
};

export default Header;
