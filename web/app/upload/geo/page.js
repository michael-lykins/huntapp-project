'use client'
import { useState } from 'react'
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
export default function Page(){
  const [resp,setResp]=useState(null); const [loading,setLoading]=useState(false)
  async function onSubmit(e){ e.preventDefault(); setLoading(true); const form=new FormData(e.currentTarget);
    try{ const r=await fetch(`${API_BASE}/upload/geo`,{method:'POST',body:form}); const j=await r.json(); setResp(j); }catch(err){ setResp({ok:false,error:String(err)}) } finally{ setLoading(false) } }
  return (<div><h2>Upload GPX/KML</h2><form onSubmit={onSubmit}><div><label>File: <input name='file' type='file' accept='.gpx,.kml' required/></label></div><button type='submit' disabled={loading}>{loading?'Uploading...':'Upload'}</button></form>{resp&&<pre style={{marginTop:16,padding:12,background:'#111',color:'#0f0'}}>{JSON.stringify(resp,null,2)}</pre>}</div>) }
