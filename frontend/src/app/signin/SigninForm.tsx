'use client';

import React from 'react';
import { LoadingSpinner } from '@/components/Spinner';
import { useSigninMutation } from '@/hooks/useSignin';

export const SigninForm = () => {
  const { mutate, isPending: isLoading } = useSigninMutation();

  const handleSignin = async (e: React.FormEvent) => {
    e.preventDefault();
    const target = e.target as HTMLFormElement;
    mutate({
      username: target.username.value,
      password: target.password.value,
    });
  };

  return (
    <form className='space-y-6' onSubmit={handleSignin}>
      <div>
        <label
          htmlFor='username'
          className='block text-sm font-medium text-gray-700'
        >
          Username
        </label>
        <div className='mt-1'>
          <input
            id='username'
            name='username'
            type='text'
            autoComplete='username'
            required
            disabled={isLoading}
            className='appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm disabled:bg-gray-50 disabled:text-gray-500'
          />
        </div>
      </div>

      <div>
        <label
          htmlFor='password'
          className='block text-sm font-medium text-gray-700'
        >
          Password
        </label>
        <div className='mt-1'>
          <input
            id='password'
            name='password'
            type='password'
            autoComplete='current-password'
            required
            disabled={isLoading}
            className='appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm disabled:bg-gray-50 disabled:text-gray-500'
          />
        </div>
      </div>

      <div>
        <button
          type='submit'
          disabled={isLoading}
          className='w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed'
        >
          {isLoading ? (
            <LoadingSpinner>Signing in...</LoadingSpinner>
          ) : (
            'Sign in'
          )}
        </button>
      </div>
    </form>
  );
};
