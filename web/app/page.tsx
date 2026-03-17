import Link from 'next/link'
export default function Page() {
  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: 32, maxWidth: 480 }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Ridgeline</h1>
      <p style={{ color: '#6b7280', marginBottom: 24 }}>Hyper-local hunting intelligence</p>
      <ul style={{ listStyle: 'none', padding: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <li>
          <Link href="/map" style={{
            display: 'block', background: '#111827', color: '#f9fafb',
            borderRadius: 10, padding: '12px 18px', textDecoration: 'none',
            fontWeight: 600,
          }}>Map &amp; Trail Cameras</Link>
        </li>
        <li>
          <Link href="/pages/gallery" style={{
            display: 'block', background: '#f3f4f6', color: '#111827',
            borderRadius: 10, padding: '12px 18px', textDecoration: 'none',
          }}>Photo Gallery</Link>
        </li>
        <li>
          <Link href="/upload/image" style={{
            display: 'block', background: '#f3f4f6', color: '#111827',
            borderRadius: 10, padding: '12px 18px', textDecoration: 'none',
          }}>Upload Image</Link>
        </li>
      </ul>
    </div>
  )
}
