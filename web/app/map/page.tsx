import dynamic from 'next/dynamic';

const MapClient = dynamic(() => import('./MapClient'), { ssr: false });

export const metadata = {
  title: 'Map – HuntApp',
};

export default function Page() {
  return <MapClient />;
}
