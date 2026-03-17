// web/app/layout.tsx

import React from 'react';
import './globals.css';

export const metadata = {
  title: 'HuntApp',
  description: 'HuntApp web',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, background: '#f3f4f6' }}>{children}</body>
    </html>
  );
}
