import React from "react";
import { LIcon } from "./ui/LIcon";
import { Btn } from "./ui/Btn";

export function AppHeader({ page, setPage, apiOk, onSeed }) {
  const tabs = [
    {id:'dashboard', label:'Global Map', icon:'radar'},
    {id:'company', label:'Upload BOM', icon:'package'},
    {id:'events', label:'Tariff Signals', icon:'zap'},
    {id:'scenarios', label:'HITL & Scenarios', icon:'shield-check'},
    {id:'report', label:'Audit Log', icon:'file-clock'},
  ];
  return (
    <div className="header-area" style={{display:'flex',alignItems:'center',justifyContent:'space-between',
      padding:'0 32px', borderBottom:'1px solid var(--glass-border-lo)',
      background:'rgba(255,255,255,.45)', backdropFilter:'blur(18px)', minHeight:70}}>
      
      <div style={{display:'flex',alignItems:'center',gap:12}}>
        <img src="/assets/espada-mark.svg" width="32" height="32" alt=""/>
        <span style={{fontWeight:600,fontSize:20,letterSpacing:'-.02em'}}>espada</span>
      </div>

      <div style={{display:'flex',gap:8}}>
        {tabs.map(t=>(
          <button key={t.id} onClick={()=>setPage(t.id)} title={t.label} style={{
            background: page===t.id ? 'rgba(255,255,255,0.7)' : 'transparent',
            border:'none', padding:'8px 16px', borderRadius:'100px',
            fontSize:14, fontWeight:page===t.id?500:400, color:page===t.id?'var(--fg-1)':'var(--fg-2)',
            display:'flex', alignItems:'center', gap:8, cursor:'pointer',
            transition:'all var(--motion-fast)',
            boxShadow: page===t.id ? 'var(--shadow-glass-1)' : 'none'
          }}>
            <LIcon name={t.icon} size={16}/>
            <span style={{display: page===t.id ? 'inline' : 'none'}}>{t.label}</span>
          </button>
        ))}
      </div>

      <div style={{display:'flex',alignItems:'center',gap:16}}>
        <Btn variant="ghost" small onClick={onSeed}>Load Demo</Btn>
        <div style={{display:'flex',alignItems:'center',gap:8,padding:'6px 12px',borderRadius:999,
          background:apiOk?'rgba(79,143,90,.14)':'rgba(209,67,67,.1)',
          color:apiOk?'#35683F':'#D14343',
          fontFamily:'var(--font-mono)',fontSize:11,fontWeight:500,letterSpacing:'.06em'}}>
          <span style={{width:6,height:6,borderRadius:999,
            background:apiOk?'#4F8F5A':'#D14343',
            boxShadow:apiOk?'0 0 8px #4F8F5A':'none',display:'inline-block'}}/>
          {apiOk ? 'API LIVE' : 'API OFFLINE'}
        </div>
      </div>
    </div>
  );
}
