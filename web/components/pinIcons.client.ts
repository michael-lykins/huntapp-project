// web/components/pinIcons.client.ts
'use client';

import { makeIcon } from './makeIcon.client';

export function getColoredIcon(color?: string, glyph?: string) {
    return makeIcon(color || '#3388ff', glyph || '');
}

// Example usage for specific event types (customize as needed)
const eventTypeColors: { [key: string]: string } = {
    sighting: '#28a745', // green
    capture: '#dc3545',  // red
    release: '#ffc107',  // yellow
    // Add more event types and their colors as needed
};

export function getEventIcon(eventType: string) {
    const color = eventTypeColors[eventType] || '#3388ff'; // default to blue
    return getColoredIcon(color);
}

export function getDraftIcon() {
    return getColoredIcon('#6c757d', '✚'); // gray with plus sign
}