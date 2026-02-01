'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { UserCheck, RotateCcw, Loader2 } from 'lucide-react';
import { CheckinIF } from '@/interfaces';

interface CheckinIndicatorProps {
  checkin: CheckinIF;
  isTimerSegment?: boolean;
  onReset?: () => void;
  isResetting?: boolean;
}

interface TooltipPosition {
  top: number;
  left: number;
}

export function CheckinIndicator({
  checkin,
  isTimerSegment = false,
  onReset,
  isResetting = false,
}: CheckinIndicatorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState<TooltipPosition>({
    top: 0,
    left: 0,
  });
  const [mounted, setMounted] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const closeTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Ensure we only render portal on client
  useEffect(() => {
    setMounted(true);
  }, []);

  // Detect mobile device
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.matchMedia('(max-width: 768px)').matches);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Calculate tooltip position when opening
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const tooltipWidth = tooltipRef.current?.offsetWidth || 150;

      // Position: right-aligned with button, below it
      setTooltipPosition({
        top: rect.bottom + 6 + window.scrollY,
        left: Math.max(8, rect.right - tooltipWidth + window.scrollX),
      });
    }
  }, [isOpen]);

  // Handle clicking outside the tooltip (for mobile click mode)
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        tooltipRef.current &&
        !tooltipRef.current.contains(event.target as Node) &&
        !buttonRef.current?.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setShowConfirm(false);
      }
    };

    if (isOpen && isMobile) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, isMobile]);

  // Close tooltip on scroll (for portal positioning)
  useEffect(() => {
    const handleScroll = () => {
      if (isOpen) {
        setIsOpen(false);
        setShowConfirm(false);
      }
    };

    if (isOpen) {
      window.addEventListener('scroll', handleScroll, true);
    }

    return () => {
      window.removeEventListener('scroll', handleScroll, true);
    };
  }, [isOpen]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) {
        clearTimeout(closeTimeoutRef.current);
      }
    };
  }, []);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isMobile) {
      setIsOpen(!isOpen);
      if (isOpen) setShowConfirm(false);
    }
  };

  const cancelClose = useCallback(() => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    cancelClose();
    closeTimeoutRef.current = setTimeout(() => {
      setIsOpen(false);
      setShowConfirm(false);
    }, 150); // 150ms delay to allow mouse to travel to tooltip
  }, [cancelClose]);

  const handleMouseEnter = () => {
    if (!isMobile) {
      cancelClose();
      setIsOpen(true);
    }
  };

  const handleMouseLeave = () => {
    if (!isMobile) {
      scheduleClose();
    }
  };

  const handleResetClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!showConfirm) {
      setShowConfirm(true);
    }
  };

  const handleConfirmReset = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onReset && !isResetting) {
      onReset();
      setIsOpen(false);
      setShowConfirm(false);
    }
  };

  const handleCancelReset = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowConfirm(false);
  };

  const displayName = checkin.name || 'Unknown';

  const tooltipContent = (
    <div
      ref={tooltipRef}
      style={{
        position: 'absolute',
        top: tooltipPosition.top,
        left: tooltipPosition.left,
        backgroundColor: '#fef3c7',
        zIndex: 9999,
      }}
      className='rounded-md shadow-md border border-amber-300 px-2 py-1 whitespace-nowrap'
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {showConfirm ? (
        <div className='flex items-center gap-2 text-xs'>
          <span className='text-gray-600'>Reset?</span>
          <button
            type='button'
            onClick={handleConfirmReset}
            disabled={isResetting}
            className='px-1.5 py-0.5 rounded bg-red-500 hover:bg-red-600 text-white text-[10px] font-medium transition-colors disabled:opacity-50'
          >
            {isResetting ? <Loader2 className='w-3 h-3 animate-spin' /> : 'Yes'}
          </button>
          <button
            type='button'
            onClick={handleCancelReset}
            className='px-1.5 py-0.5 rounded bg-gray-200 hover:bg-gray-300 text-gray-600 text-[10px] font-medium transition-colors'
          >
            No
          </button>
        </div>
      ) : (
        <div className='flex items-center gap-1.5 text-xs'>
          <span className='font-medium text-gray-800'>{displayName}</span>
          <span className='text-gray-400'>·</span>
          <span
            className={
              checkin.is_member ? 'text-indigo-600' : 'text-emerald-600'
            }
          >
            {checkin.is_member ? 'Member' : 'Guest'}
          </span>
          {isTimerSegment && onReset && (
            <button
              type='button'
              onClick={handleResetClick}
              disabled={isResetting}
              className='ml-1 p-0.5 rounded hover:bg-amber-200 text-gray-500 hover:text-red-500 transition-colors disabled:opacity-50'
            >
              {isResetting ? (
                <Loader2 className='w-3 h-3 animate-spin' />
              ) : (
                <RotateCcw className='w-3 h-3' />
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div
      className='relative inline-flex items-center'
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        ref={buttonRef}
        type='button'
        onClick={handleClick}
        className='p-1 rounded-full bg-amber-100 hover:bg-amber-200 transition-colors cursor-pointer'
      >
        <UserCheck className='w-3.5 h-3.5 text-amber-600' />
      </button>

      {mounted && isOpen && createPortal(tooltipContent, document.body)}
    </div>
  );
}
