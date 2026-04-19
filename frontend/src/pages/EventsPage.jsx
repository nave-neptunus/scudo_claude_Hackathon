import React, { useState, useEffect } from "react";
import { Glass } from "../components/ui/Glass";
import { Btn } from "../components/ui/Btn";
import { Chip, StatusChip } from "../components/ui/Chip";
import { api } from "../lib/api";

export function EventsPage({ setPage, setTargetRec }) {
  const [events, setEvents] = useState([]);
  const [boms, setBoms] = useState([]);

  useEffect(()=>{
    api('GET','/events').then(d=>setEvents(d.events||[])).catch(()=>{});
    api('GET','/boms').then(setBoms).catch(()=>{});
  }, []);

  async function analyze(ev) {
    if (!boms.length) { alert('Upload a BOM first (Company tab).'); return; }
    const r = await api('POST', `/events/${ev.id}/analyze`, { bom_id: boms[0].id });
    setTargetRec(r.recommendation_id);
    setPage('scenarios');
  }

  return (
    <div style={{maxWidth:900, margin:'0 auto'}}>
      <div className="h4" style={{marginBottom:20}}>Tariff Events</div>
      {events.length === 0
        ? <div className="body-sm">No events yet. Run the signal monitor poll.</div>
        : <Glass>
            <table style={{fontSize:13}}>
              <thead><tr style={{color:'var(--fg-3)'}}>
                <th style={{textAlign:'left',padding:'6px 12px'}}>Title</th>
                <th style={{textAlign:'left',padding:'6px 12px'}}>Source</th>
                <th style={{textAlign:'left',padding:'6px 12px'}}>HS Codes</th>
                <th style={{padding:'6px 12px'}}></th>
              </tr></thead>
              <tbody>{events.map((ev,i)=>(
                <tr key={i} style={{borderTop:'1px solid var(--border-1)'}}>
                  <td style={{padding:'8px 12px', maxWidth:340, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>{ev.title}</td>
                  <td style={{padding:'8px 12px'}}><Chip bg="var(--grey-100)" fg="var(--fg-3)">{ev.source}</Chip></td>
                  <td style={{padding:'8px 12px', fontFamily:'var(--font-mono)', fontSize:12}}>{(ev.hs_codes||[]).slice(0,3).join(', ')}</td>
                  <td style={{padding:'8px 12px'}}><Btn small onClick={()=>analyze(ev)}>Analyze</Btn></td>
                </tr>
              ))}</tbody>
            </table>
          </Glass>
      }
    </div>
  );
}
