'use client';

import { useMapEvents } from 'react-leaflet';

export default function MapClickCatcher({
    onClickLatLng,
}: {
    onClickLatLng: (lat: number, lng: number) => void;
}) {
    useMapEvents({
        click(e) {
            onClickLatLng(e.latlng.lat, e.latlng.lng);
        },
    });
    return null;
}   