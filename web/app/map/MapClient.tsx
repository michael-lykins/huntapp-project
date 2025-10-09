'use client';

import { useState, useCallback } from 'react';
import Map, { Marker, NavigationControl } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import PinFormModal from '../../components/PinFormModal';
import type { MapMouseEvent } from 'maplibre-gl';

export default function MapClient() {
  const [viewState, setViewState] = useState({
    longitude: -96.7,
    latitude: 40.8,
    zoom: 8,
  });

  const [selected, setSelected] = useState<{ lat: number; lon: number } | null>(null);

  const handleClick = useCallback((evt: MapMouseEvent) => {
    const { lngLat } = evt;
    setSelected({ lat: lngLat.lat, lon: lngLat.lng });
  }, []);

  return (
    <>
      <Map
        initialViewState={viewState}
        onMove={(evt) => setViewState(evt.viewState)}
        onClick={handleClick}
        mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
        style={{ width: '100%', height: '100vh' }}
      >
        <NavigationControl position="top-left" />
        {selected && (
          <Marker longitude={selected.lon} latitude={selected.lat}>
            📍
          </Marker>
        )}
      </Map>

      <PinFormModal
        visible={!!selected}
        lat={selected?.lat}
        lon={selected?.lon}
        onClose={() => setSelected(null)}
        onSave={() => {
          // TODO: call your API to create the pin, then close
          setSelected(null);
        }}
      />
    </>
  );
}
