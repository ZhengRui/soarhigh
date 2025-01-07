import type { Metadata } from 'next';
import './globals.css';
import Header from './Header';
import QueryProvider from './QueryProvider';
import { Provider } from 'jotai';
import { Toaster } from 'react-hot-toast';

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
        <QueryProvider>
          <Provider>
            <main>
              <Header />
              {children}
              <Toaster position='bottom-right' />
            </main>
          </Provider>
        </QueryProvider>
      </body>
    </html>
  );
}
