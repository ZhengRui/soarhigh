import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'SoarHigh Toastmaster Club',
  description: 'SoarHigh Toastmaster Club Website',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang='en'>
      <body>
        <main className='pt-16'>{children}</main>
      </body>
    </html>
  );
}
