// web/app/map/MapClient.tsx
'use client';

import { useState, useCallback } from 'react';
import Map, { Marker, NavigationControl } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import PinFormModal from '../../components/PinFormModal';

type ViewState = {
  longitude: number;
  latitude: number;
  zoom: number;
};

export default function MapClient() {
  const [viewState, setViewState] = useState<ViewState>({
    longitude: -96.7,
    latitude: 40.8,
    zoom: 8,
  });

  const [selected, setSelected] = useState<{ lat: number; lon: number } | null>(null);

  const handleClick = useCallback((event: maplibregl.MapMouseEvent & maplibregl.EventData) => {
    const { lngLat } = event;
    setSelected({ lat: lngLat.lat, lon: lngLat.lng });
  }, []);

  return (
    <>
      <Map
        mapLib={import('maplibre-gl')}
        initialViewState={viewState}
        onMove={evt => setViewState(evt.viewState as ViewState)}
        onClick={handleClick}
        style={{ width: '100%', height: '100vh' }}
        mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
      >
        <NavigationControl position="top-left" />

        {selected && (
          <Marker longitude={selected.lon} latitude={selected.lat} anchor="bottom">
            <span role="img" aria-label="marker">📍</span>
          </Marker>
        )}
      </Map>

      <PinFormModal lat={selected?.lat} lon={selected?.lon} />
    </>
  );
}
