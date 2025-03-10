import React from 'react';

export const metadata = {
  title: 'Posts - SoarHigh Toastmasters Club',
  description: 'Read and share knowledge with the SoarHigh community',
};

export default function PostsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
