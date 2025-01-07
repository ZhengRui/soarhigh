export const LoadingSpinner = ({ children }: { children: React.ReactNode }) => {
  return (
    <div className='flex items-center'>
      <div className='w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2' />
      {children}
    </div>
  );
};
