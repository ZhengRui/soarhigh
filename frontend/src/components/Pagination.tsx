import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange,
  className = '',
}) => {
  // Don't render pagination if there's only one page
  if (totalPages <= 1) {
    return null;
  }

  const handlePrevious = () => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNext = () => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1);
    }
  };

  // Generate page numbers to display
  const getPageNumbers = () => {
    const pageNumbers: (number | string)[] = [];

    // Always show first page
    pageNumbers.push(1);

    // Calculate range to show around current page
    const startPage = Math.max(2, currentPage - 1);
    const endPage = Math.min(totalPages - 1, currentPage + 1);

    // Add ellipsis if there's a gap after page 1
    if (startPage > 2) {
      pageNumbers.push('...');
    }

    // Add pages in range
    for (let i = startPage; i <= endPage; i++) {
      pageNumbers.push(i);
    }

    // Add ellipsis if there's a gap before last page
    if (endPage < totalPages - 1) {
      pageNumbers.push('...');
    }

    // Always show last page if it's not the only page
    if (totalPages > 1) {
      pageNumbers.push(totalPages);
    }

    return pageNumbers;
  };

  return (
    <div
      className={`flex items-center justify-center space-x-2 my-8 ${className}`}
    >
      {/* Previous button */}
      <button
        onClick={handlePrevious}
        disabled={currentPage === 1}
        className={`p-2 rounded-md flex items-center justify-center transition-all duration-200
          ${
            currentPage === 1
              ? 'text-gray-400 cursor-not-allowed bg-gray-100'
              : 'text-gray-700 hover:bg-gray-100'
          }`}
        aria-label='Previous page'
      >
        <ChevronLeft className='w-5 h-5' />
      </button>

      {/* Page numbers */}
      <div className='flex items-center space-x-1'>
        {getPageNumbers().map((page, index) =>
          typeof page === 'number' ? (
            <button
              key={index}
              onClick={() => onPageChange(page)}
              className={`w-9 h-9 flex items-center justify-center rounded-md transition-all duration-200
                ${
                  currentPage === page
                    ? 'text-blue-600 font-medium relative after:absolute after:bottom-1 after:left-2 after:right-2 after:h-0.5 after:bg-gradient-to-r after:from-blue-600 after:to-purple-600'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
            >
              {page}
            </button>
          ) : (
            <span key={index} className='px-1 text-gray-500'>
              {page}
            </span>
          )
        )}
      </div>

      {/* Next button */}
      <button
        onClick={handleNext}
        disabled={currentPage === totalPages}
        className={`p-2 rounded-md flex items-center justify-center transition-all duration-200
          ${
            currentPage === totalPages
              ? 'text-gray-400 cursor-not-allowed bg-gray-100'
              : 'text-gray-700 hover:bg-gray-100'
          }`}
        aria-label='Next page'
      >
        <ChevronRight className='w-5 h-5' />
      </button>
    </div>
  );
};
