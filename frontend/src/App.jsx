import React, { useState, useEffect } from "react";
import { AppHeader } from "./components/AppHeader";
import { DashboardPage } from "./pages/DashboardPage";
import { UploadPage } from "./pages/UploadPage";
import { AuditPage } from "./pages/AuditPage";
import { EventsPage } from "./pages/EventsPage";
import { RecommendationsPage } from "./pages/RecommendationsPage";
import { api } from "./lib/api";

export default function App() {
  const [page, setPage]   = useState('dashboard');
  const [apiOk, setApiOk] = useState(false);
  const [events, setEvents] = useState([]);
  const [boms, setBoms]     = useState([]);
  const [targetRec, setTargetRec] = useState(null);

  useEffect(()=>{
    api('GET','/health').then(()=>setApiOk(true)).catch(()=>setApiOk(false));
    api('GET','/events').then(d=>setEvents(d.events||[])).catch(()=>{});
    api('GET','/boms').then(setBoms).catch(()=>{});

    const t = setInterval(()=>{
      api('GET','/health').then(()=>setApiOk(true)).catch(()=>setApiOk(false));
    }, 5000);
    return ()=>clearInterval(t);
  }, []);

  async function seedDemo() {
    try { 
      await api('POST','/demo/seed'); 
      api('GET','/boms').then(setBoms); 
      api('GET','/events').then(d=>setEvents(d.events||[])); 
    } catch(e) { 
      alert(e.message); 
    }
  }

  const navigate = (p) => setPage(p);

  return (
    <div className={page === 'dashboard' ? 'layout-grid' : ''} style={page !== 'dashboard' ? {minHeight:'100vh', display:'flex', flexDirection:'column'} : {}}>
      <AppHeader page={page} setPage={setPage} apiOk={apiOk} onSeed={seedDemo} />
      
      {page === 'dashboard' && <DashboardPage boms={boms} events={events} />}
      
      {page !== 'dashboard' && (
        <main style={{padding:'40px', flex:1, margin:'0 auto', width:'100%', maxWidth:'1200px', overflowY:'auto'}}>
          {page === 'company' && <UploadPage />}
          {page === 'report' && <AuditPage />}
          {page === 'events' && <EventsPage setPage={navigate} setTargetRec={setTargetRec} />}
          {page === 'scenarios' && <RecommendationsPage targetRec={targetRec} setTargetRec={setTargetRec} setPage={navigate} />}
        </main>
      )}
    </div>
  );
}
