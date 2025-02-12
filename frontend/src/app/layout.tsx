import type { Metadata } from 'next';
import './globals.css';
import Header from './Header';
import QueryProvider from './QueryProvider';
import { Provider } from 'jotai';
import { Toaster } from 'react-hot-toast';

export const metadata: Metadata = {
  title: 'SoarHigh Toastmasters Club',
  description: 'SoarHigh Toastmasters Club Website',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang='en'>
      <head>
        <link
          rel='preload'
          href='/fonts/brush-script-mt.ttf'
          as='font'
          type='font/ttf'
          crossOrigin='anonymous'
        />
        <link
          rel='preload'
          href='https://soarhigh.oss-cn-shenzhen.aliyuncs.com/public/images/web/publicspeaking.jpeg?x-oss-process=image/quality,q_75/format,webp'
          as='image'
        />
      </head>
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
