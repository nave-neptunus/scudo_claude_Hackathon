import React from "react";
import { Glass } from "../components/ui/Glass";
import { Btn } from "../components/ui/Btn";
import { Chip } from "../components/ui/Chip";
import { LIcon } from "../components/ui/LIcon";
import { D3WorldMap } from "../components/D3WorldMap";

function ProductsPanel({ boms }) {
  const [expanded, setExpanded] = React.useState({});
  
  const products = boms.length > 0 ? boms.map(b => ({id: b.id, name: b.name || 'Unnamed Product', rows: b.rows || []})) : [
    {id:'p1', name:'Demo Mode: No Products', rows:[]}
  ];

  const toggle = (id) => setExpanded(prev => ({...prev, [id]: !prev[id]}));

  return (
    <div className="left-area" style={{display:'flex', flexDirection:'column', gap:16, overflowY:'auto'}}>
      <div className="eyebrow" style={{marginBottom:4, marginLeft:4}}>Products Matrix</div>
      {products.map(p => (
        <Glass key={p.id} padding={0} style={{transition:'all var(--motion-fast)'}}>
          <div onClick={() => toggle(p.id)} style={{display:'flex', alignItems:'center', gap:12, padding:16, cursor:'pointer'}}
               onMouseOver={e=>e.currentTarget.style.background='rgba(255,255,255,0.03)'}
               onMouseOut={e=>e.currentTarget.style.background='transparent'}>
            <div style={{width:40,height:40,borderRadius:10,background:'rgba(76,111,174,0.1)',display:'flex',alignItems:'center',justifyContent:'center'}}>
              <LIcon name="box" size={20} color="#4C6FAE"/>
            </div>
            <div style={{flex:1}}>
              <div style={{fontWeight:600, fontSize:15}}>{p.name}</div>
              <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--fg-3)',marginTop:2}}>
                 {p.rows.length} Part{p.rows.length !== 1 ? 's' : ''}
              </div>
            </div>
          </div>
          
          {expanded[p.id] && p.rows.length > 0 && (
            <div style={{borderTop:'1px solid var(--border-1)', padding:'12px 16px', background:'rgba(0,0,0,0.1)'}}>
              <table style={{width:'100%', fontSize:11, borderCollapse:'collapse'}}>
                <thead>
                  <tr style={{textAlign:'left', color:'var(--fg-3)', borderBottom:'1px solid var(--border-1)'}}>
                     <th style={{paddingBottom:6, fontWeight:500}}>SKU</th>
                     <th style={{paddingBottom:6, fontWeight:500}}>Origin</th>
                     <th style={{paddingBottom:6, fontWeight:500, textAlign:'right'}}>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {p.rows.map((r, idx) => (
                    <tr key={idx}>
                      <td style={{padding:'6px 0', color:'var(--fg-1)', fontFamily:'var(--font-mono)'}}>{r.sku_code || r.sku}</td>
                      <td style={{padding:'6px 0', color:'var(--fg-2)'}}>{r.supplier_country}</td>
                      <td style={{padding:'6px 0', color:'var(--fg-2)', textAlign:'right'}}>${r.unit_cost_usd?.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Glass>
      ))}
      <Btn variant="ghost" style={{marginTop:'auto'}}>+ Create Product</Btn>
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
