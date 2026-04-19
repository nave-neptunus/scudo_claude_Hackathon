import React, { useState, useEffect } from "react";
import { Glass } from "../components/ui/Glass";
import { Btn } from "../components/ui/Btn";
import { StatusChip } from "../components/ui/Chip";
import { api } from "../lib/api";

export function RecommendationsPage({ targetRec, setTargetRec, setPage }) {
  const [rec, setRec] = useState(null);
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);

  useEffect(()=>{
    if (!targetRec) return;
    setLoading(true);
    const poll = setInterval(()=>{
      api('GET', `/recommendations/${targetRec}`).then(r=>{
        setRec(r);
        if (r.status !== 'running') { clearInterval(poll); setLoading(false); }
      }).catch(()=>{ clearInterval(poll); setLoading(false); });
    }, 2000);
    return ()=>clearInterval(poll);
  }, [targetRec]);

  async function approve() {
    setApproving(true);
    try { await api('POST', `/recommendations/${targetRec}/approve`); api('GET', `/recommendations/${targetRec}`).then(setRec); }
    catch(e) { alert(e.message); }
    finally { setApproving(false); }
  }

  async function reject() {
    await api('POST', `/recommendations/${targetRec}/reject`);
    api('GET', `/recommendations/${targetRec}`).then(setRec);
  }

  if (!targetRec) return (
    <div style={{maxWidth:700, margin:'0 auto'}}>
      <div className="h4" style={{marginBottom:12}}>Recommendations</div>
      <div className="body-sm">Select an event from the Events tab and click Analyze.</div>
    </div>
  );

  if (loading && !rec) return (
    <div style={{maxWidth:700, margin:'0 auto'}}>
      <div className="h4" style={{marginBottom:20}}>Running Pipeline…</div>
      <Glass><div className="body-sm" style={{padding:8}}>Agents running. This may take 20–60 seconds.</div></Glass>
    </div>
  );

  if (!rec) return <div className="body-sm">No recommendation found.</div>;

  const ranked = rec.ranked_scenarios || [];
  const email  = rec.draft_email || {};

  return (
    <div style={{maxWidth:860, margin:'0 auto'}}>
      <div style={{display:'flex', alignItems:'center', gap:12, marginBottom:20}}>
        <div className="h4">Recommendation</div>
        <StatusChip status={rec.status} />
      </div>

      {ranked.length > 0 && (
        <Glass style={{marginBottom:20}}>
          <div className="eyebrow" style={{marginBottom:12}}>Ranked Scenarios</div>
          {ranked.map((s,i)=>(
            <div key={i} style={{padding:'12px 0', borderTop: i?'1px solid var(--border-1)':undefined}}>
              <div style={{display:'flex', alignItems:'center', gap:10, marginBottom:4}}>
                <span style={{fontWeight:700, color:'var(--accent)', width:24}}>#{s.rank||i+1}</span>
                <span style={{fontWeight:600, textTransform:'capitalize'}}>{(s.strategy||s.scenario_type||'').replace('_',' ')}</span>
                <span className="body-sm">{s.recommendation_rationale}</span>
              </div>
              <div style={{paddingLeft:34, fontSize:12, color:'var(--fg-3)', fontFamily:'var(--font-mono)'}}>
                Δcost ${(s.annual_cost_delta_usd||0).toLocaleString()} · lead_time {s.lead_time_months||'?'}mo · coverage {s.supplier_coverage_pct||'?'}%
              </div>
            </div>
          ))}
        </Glass>
      )}

      {email.subject && (
        <Glass style={{marginBottom:20}}>
          <div className="eyebrow" style={{marginBottom:12}}>Draft Email</div>
          <div style={{marginBottom:6, fontWeight:600}}>{email.subject}</div>
          <div style={{fontFamily:'var(--font-mono)', fontSize:12, whiteSpace:'pre-wrap', color:'var(--fg-2)', maxHeight:220, overflowY:'auto'}}>{email.body}</div>
        </Glass>
      )}

      {rec.status === 'awaiting_approval' && (
        <div style={{display:'flex', gap:12}}>
          <Btn onClick={approve} disabled={approving}>{approving ? 'Approving…' : 'Approve & Send'}</Btn>
          <Btn variant="ghost" onClick={reject}>Reject</Btn>
        </div>
      )}
    </div>
  );
}
