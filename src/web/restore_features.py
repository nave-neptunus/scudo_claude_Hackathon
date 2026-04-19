from __future__ import annotations
import re
import subprocess

# Get the original index.html from git before we overwrote it
old_html = subprocess.check_output(['git', 'show', 'HEAD:tariffpilot/web/index.html']).decode('utf-8')

# Read our new index.html
with open('/Users/evanarumbaka/scudo_claude_Hackathon/tariffpilot/web/index.html', 'r') as f:
    new_html = f.read()

# We need to extract UploadPage, EventsPage, RecommendationsPage, HitlGate, AuditPage, etc from old_html
# and append them to new_html before the App component.

# We can find these blocks in the old HTML.
pages_to_extract = ['UploadPage', 'EventsPage', 'RecommendationsPage', 'RecDetail', 'BomSummary', 'ScenarioCard', 'HitlGate', 'EmailDisplay', 'HitlPage', 'AuditPage']

extracted_code = "\n/* --- RESTORED COMPONENTS --- */\n"
for page in pages_to_extract:
    # Regex to find `function PageName(...) { ... }` up to the next `function ` or `/* ---` or EOF
    match = re.search(r'(function ' + page + r'\b.*?\n)(?=function |/\* ─|ReactDOM|$)', old_html, re.DOTALL)
    if match:
        extracted_code += match.group(1) + "\n"

# Now we want to replace LegacyPagePlaceholder with the actual pages in the App component.
# Let's read the current App component in new_html and modify it.
app_regex = r'function App\(\) \{.*?\n\}'
match_app = re.search(app_regex, new_html, re.DOTALL)

if match_app:
    new_app = """function App() {
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

  // Quick action helpers
  async function seedDemo() {
    try { await api('POST','/demo/seed'); api('GET','/boms').then(setBoms); api('GET','/events').then(d=>setEvents(d.events||[])); }
    catch(e) { alert(e.message); }
  }

  const navigate = (p) => setPage(p);

  return (
    <div className={page === 'dashboard' ? 'layout-grid' : ''} style={page !== 'dashboard' ? {minHeight:'100vh', display:'flex', flexDirection:'column'} : {}}>
      <AppHeader page={page} setPage={setPage} apiOk={apiOk} onSeed={seedDemo} />
      
      {page === 'dashboard' && <MapDashboard boms={boms} events={events} />}
      
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
"""
    
    # Let's also update the Tabs in AppHeader so they click through
    header_regex = r'function AppHeader\(\{ page, setPage, apiOk \}\) \{.*?\n\}'
    new_header = """function AppHeader({ page, setPage, apiOk, onSeed }) {
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
        <img src="./assets/espada-mark.svg" width="32" height="32" alt=""/>
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
"""
    
    # We replace App and LegacyPagePlaceholder and AppHeader
    new_html = new_html.replace(match_app.group(0), new_app)
    new_html = re.sub(header_regex, new_header, new_html, flags=re.DOTALL)
    
    # Eliminate LegacyPagePlaceholder completely
    new_html = re.sub(r'function LegacyPagePlaceholder.*?\n\}\n', '', new_html, flags=re.DOTALL)

    # Insert Extracted components back right before App
    new_html = new_html.replace('function App() {', extracted_code + '\nfunction App() {')

    with open('/Users/evanarumbaka/scudo_claude_Hackathon/tariffpilot/web/index.html', 'w') as f:
        f.write(new_html)
    print("Features perfectly restored.")

