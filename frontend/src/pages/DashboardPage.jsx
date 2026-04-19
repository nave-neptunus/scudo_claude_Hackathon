import React from "react";
import { Glass } from "../components/ui/Glass";
import { Btn } from "../components/ui/Btn";
import { Chip } from "../components/ui/Chip";
import { LIcon } from "../components/ui/LIcon";
import { D3WorldMap } from "../components/D3WorldMap";

function ProductsPanel({ boms }) {
  const products = boms.length > 0 ? boms.map((b,i)=>({id:b.id, name:`Product ${i+1}`})) : [
    {id:'p1', name:'Product 1'},
    {id:'p2', name:'Product 2'},
    {id:'p3', name:'Product 3'},
  ];

  return (
    <div className="left-area" style={{display:'flex', flexDirection:'column', gap:16}}>
      <div className="eyebrow" style={{marginBottom:4, marginLeft:4}}>Products</div>
      {products.map(p => (
        <Glass key={p.id} padding={16} style={{cursor:'pointer', transition:'transform var(--motion-fast)'}} 
               onMouseOver={e=>e.currentTarget.style.transform='translateY(-2px)'}
               onMouseOut={e=>e.currentTarget.style.transform='none'}>
          <div style={{display:'flex', alignItems:'center', gap:12}}>
            <div style={{width:40,height:40,borderRadius:10,background:'rgba(76,111,174,0.1)',display:'flex',alignItems:'center',justifyContent:'center'}}>
              <LIcon name="box" size={20} color="#4C6FAE"/>
            </div>
            <div>
              <div style={{fontWeight:600, fontSize:15}}>{p.name}</div>
              <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--fg-3)',marginTop:2}}>
                 {boms.length>0 ? 'BOM Connected' : 'Demo Mode'}
              </div>
            </div>
          </div>
        </Glass>
      ))}
      <Btn variant="ghost" style={{marginTop:'auto'}}>+ Upload BOM</Btn>
    </div>
  );
}

function EventsPanel({ events }) {
  const displayEvents = events.slice(0, 3);
  
  return (
    <div className="right-area" style={{display:'flex', flexDirection:'column', gap:16}}>
      <div className="eyebrow" style={{marginBottom:4, marginLeft:4}}>Tariff Signals</div>
      {displayEvents.length === 0 ? (
        <Glass padding={20} style={{textAlign:'center'}}>
          <div className="body-sm">No active events.</div>
        </Glass>
      ) : displayEvents.map(ev => (
        <Glass key={ev.id} padding={16}>
          <div style={{display:'flex', alignItems:'center', gap:8, marginBottom:8}}>
            <Chip bg='rgba(209,67,67,.1)' fg='#D14343'>{ev.threat_level || 'EVENT'}</Chip>
            <div className="eyebrow">{ev.source||'manual'}</div>
          </div>
          <div style={{fontWeight:600,fontSize:14,marginBottom:6, lineHeight:'20px'}}>{ev.title}</div>
          <div style={{fontSize:12,color:'var(--fg-2)',marginBottom:12, display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical', overflow:'hidden'}}>
            {ev.description||ev.raw_excerpt}
          </div>
          
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',borderTop:'1px solid var(--border-1)',paddingTop:12}}>
            <div style={{fontFamily:'var(--font-mono)',fontSize:10,color:'#D14343'}}>
              {ev.rate_change_hint || 'Rate unknown'}
            </div>
            <Btn small variant="ghost">Map Impact</Btn>
          </div>
        </Glass>
      ))}
      
      <Glass thick dark padding={18} style={{marginTop:'auto'}}>
        <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:8,color:'var(--orange-300)'}}>
           <LIcon name="shield-check" size={16}/>
           <div style={{fontWeight:600, fontSize:13}}>HITL Gate Ready</div>
        </div>
        <div style={{fontSize:12, color:'var(--fg-4)', marginBottom:12}}>1 pending authorization</div>
        <Btn small style={{width:'100%'}}>Review Scenarios</Btn>
      </Glass>
    </div>
  );
}

function TimelinePanel() {
  const dates = [
    { label: "Yesterday", date: "Apr 17, 2026", active: false },
    { label: "Today", date: "Apr 18, 2026", active: true },
    { label: "Tomorrow", date: "Apr 19, 2026", active: false },
  ];

  return (
    <div className="bottom-area">
      <Glass padding="12px 24px" style={{display:'flex', alignItems:'center', gap:40, pointerEvents:'auto'}}>
        {dates.map((d, i) => (
          <div key={i} style={{display:'flex', flexDirection:'column', alignItems:'center', opacity: d.active ? 1 : 0.5}}>
            <div style={{width:2, height:12, background: d.active?'var(--accent)':'var(--fg-3)', marginBottom:8, borderRadius:2}}/>
            <div style={{fontFamily:'var(--font-mono)',fontSize:11,fontWeight:600,color:d.active?'var(--fg-1)':'var(--fg-3)',marginBottom:2}}>{d.date}</div>
            <div className="eyebrow">{d.label}</div>
          </div>
        ))}
      </Glass>
    </div>
  );
}

export function DashboardPage({ boms, events }) {
  return (
    <>
      <ProductsPanel boms={boms} />
      <div className="center-area">
         <D3WorldMap events={events} boms={boms} />
         
         <div style={{position:'absolute', top:30, left:40, pointerEvents:'none'}}>
            <div className="h4" style={{letterSpacing:'-0.02em'}}>Global Supply Matrix</div>
            <div className="body-sm" style={{marginTop:4, display:'flex', alignItems:'center', gap:8}}>
               <span style={{width:8, height:8, borderRadius:4, background:'var(--sev-critical)'}}/> High Risk Corridors
            </div>
         </div>
      </div>
      <TimelinePanel />
      <EventsPanel events={events} />
    </>
  );
}
