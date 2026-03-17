// web/app/layout.tsx

import React from 'react';
import './globals.css';
import OtelInit from './OtelInit';

export const metadata = {
  title: 'Ridgeline',
  description: 'Ridgeline – Hyper-local hunting intelligence',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, background: '#f3f4f6' }}>
        <OtelInit />
        {children}
      </body>
    </html>
  );
}
