'use client';

import { useEffect } from 'react';
import { initOtel } from '../lib/otel';

export default function OtelInit() {
  useEffect(() => { initOtel(); }, []);
  return null;
}
