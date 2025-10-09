'use client'
import { useState } from 'react'
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
export default function Page(){
  const [resp,setResp]=useState(null); const [loading,setLoading]=useState(false)
  async function onSubmit(e){ e.preventDefault(); setLoading(true); const form=new FormData(e.currentTarget);
    try{ const r=await fetch(`${API_BASE}/upload`,{method:'POST',body:form}); const j=await r.json(); setResp(j); }catch(err){ setResp({ok:false,error:String(err)}) } finally{ setLoading(false) } }
  return (<div><h2>Upload Image</h2><form onSubmit={onSubmit}><div><label>Camera ID: <input name='camera_id' required/></label></div><div><label>Latitude: <input name='lat' type='number' step='any'/></label></div><div><label>Longitude: <input name='lon' type='number' step='any'/></label></div><div><label>Heading (deg): <input name='heading_deg' type='number' step='any'/></label></div><div><label>Label: <input name='label' placeholder='Buck/Doe/Human/...'/></label></div><div><label>Image File: <input name='file' type='file' accept='image/*' required/></label></div><button type='submit' disabled={loading}>{loading?'Uploading...':'Upload'}</button></form>{resp&&<pre style={{marginTop:16,padding:12,background:'#111',color:'#0f0'}}>{JSON.stringify(resp,null,2)}</pre>}</div>) }
