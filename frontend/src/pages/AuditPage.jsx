import React, { useState, useEffect } from "react";
import { Glass } from "../components/ui/Glass";
import { api } from "../lib/api";

export function AuditPage() {
  const [runs, setRuns] = useState([]);

  useEffect(()=>{ 
    api('GET','/audit').then(d => setRuns(d || [])).catch(()=>{}); 
  }, []);

  return (
    <div style={{maxWidth:900, margin:'0 auto'}}>
      <div className="h4" style={{marginBottom:20}}>Agent Audit Log</div>
      {runs.length === 0
        ? <div className="body-sm">No agent runs recorded yet.</div>
        : <Glass>
            <table style={{fontSize:13}}>
              <thead><tr style={{color:'var(--fg-3)'}}>
                <th style={{textAlign:'left',padding:'6px 12px'}}>Agent</th>
                <th style={{textAlign:'left',padding:'6px 12px'}}>Model</th>
                <th style={{textAlign:'left',padding:'6px 12px'}}>Started</th>
                <th style={{textAlign:'left',padding:'6px 12px'}}>Latency</th>
              </tr></thead>
              <tbody>{runs.map((r,i)=>(
                <tr key={i} style={{borderTop:'1px solid var(--border-1)'}}>
                  <td style={{padding:'8px 12px'}}>{r.agent_name}</td>
                  <td style={{padding:'8px 12px', fontFamily:'var(--font-mono)', fontSize:12}}>{r.model}</td>
                  <td style={{padding:'8px 12px', fontFamily:'var(--font-mono)', fontSize:12}}>{r.started_at?.slice(0,19)}</td>
                  <td style={{padding:'8px 12px'}}>{r.latency_ms != null ? `${r.latency_ms}ms` : '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          </Glass>
      }
    </div>
  );
}
