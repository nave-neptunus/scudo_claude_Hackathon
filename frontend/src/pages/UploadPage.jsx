import React, { useState } from "react";
import { Glass } from "../components/ui/Glass";
import { Btn } from "../components/ui/Btn";
import { api } from "../lib/api";

export function UploadPage() {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);

  const [userId] = useState(() => 'user-' + Math.random().toString(36).slice(2, 10));
  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('');
  const [products, setProducts] = useState('');
  const [countries, setCountries] = useState('');
  const [importUsd, setImportUsd] = useState('');
  const [relationships, setRelationships] = useState('');
  const [tariffConcern, setTariffConcern] = useState('');
  const [tone, setTone] = useState('formal');

  const [bomFile, setBomFile] = useState(null);
  const [pdfFiles, setPdfFiles] = useState([]);
  
  const [productName, setProductName] = useState('');
  const [parts, setParts] = useState([{ sku_code: '', description: '', supplier_country: '', unit_cost_usd: '' }]);

  const steps = ['Business Info', 'Supply Chain', 'Product Parts'];

  const fieldStyle = {
    width:'100%', padding:'10px 12px', borderRadius:8,
    border:'1px solid var(--border-1)', background:'var(--grey-025)',
    fontSize:14, color:'var(--fg-1)', outline:'none',
    fontFamily:'var(--font-sans)',
  };
  const labelStyle = { display:'block', marginBottom:6, fontWeight:500, color:'var(--fg-2)', fontSize:13 };
  const fieldGroup = { marginBottom:20 };

  async function submit() {
    setSaving(true); setError(null);
    try {
      const fd = new FormData();
      fd.append('user_id', userId);
      fd.append('company_name', companyName);
      fd.append('industry', industry);
      fd.append('products', products);
      fd.append('supplier_countries', JSON.stringify(
        countries.split(',').map(c => c.trim()).filter(Boolean)
      ));
      fd.append('monthly_import_usd', importUsd || '0');
      fd.append('supplier_relationships', relationships);
      fd.append('tariff_concern', tariffConcern);
      fd.append('tone_preference', tone);
      
      if (parts.length > 0 && parts[0].sku_code) {
        // Convert visual parts builder to CSV Blob
        const headers = ['sku_code', 'description', 'supplier_country', 'unit_cost_usd'];
        const csvRows = [headers.join(',')];
        parts.forEach(p => {
            const row = [p.sku_code, p.description, p.supplier_country, p.unit_cost_usd].map(v => `"${v}"`).join(',');
            csvRows.push(row);
        });
        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
        fd.append('bom_csv', blob, (productName || 'New_Product') + '.csv');
      } else if (bomFile) {
        fd.append('bom_csv', bomFile);
      }
      
      for (const f of pdfFiles) fd.append('pdfs', f);

      // Using raw fetch since we need FormData, not JSON
      const r = await fetch("/api/v1/onboarding", { method: 'POST', body: fd });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setDone(data);
    } catch(e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (done) return (
    <Glass style={{maxWidth:560, margin:'60px auto'}}>
      <div style={{textAlign:'center', padding:'16px 0'}}>
        <div style={{fontSize:40, marginBottom:16}}>✓</div>
        <div className="h5" style={{marginBottom:8}}>Setup Complete</div>
        <div className="body-sm" style={{marginBottom:20}}>
          Profile saved. {done.bom_id ? `BOM uploaded (id: ${done.bom_id.slice(0,8)}…).` : 'No BOM uploaded.'}
        </div>
        <Btn onClick={()=>setDone(null)}>Start Over</Btn>
      </div>
    </Glass>
  );

  return (
    <div style={{maxWidth:640, margin:'0 auto'}}>
      <div className="h4" style={{marginBottom:4}}>Business Onboarding</div>
      <div className="body-sm" style={{marginBottom:28}}>
        Tell us about your business so TariffShield can personalise alerts and recommendations.
      </div>

      <div style={{display:'flex', gap:8, marginBottom:28}}>
        {steps.map((s, i) => (
          <button key={i} onClick={()=>setStep(i)} style={{
            padding:'6px 18px', borderRadius:999, border:'1px solid var(--border-1)',
            background: step===i ? 'var(--accent)' : 'var(--grey-025)',
            color: step===i ? '#fff' : 'var(--fg-2)',
            fontWeight: step===i ? 600 : 400, cursor:'pointer', fontSize:13,
          }}>{i+1}. {s}</button>
        ))}
      </div>

      <Glass>
        {step === 0 && (
          <div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Company name *</label>
              <input style={fieldStyle} value={companyName} onChange={e=>setCompanyName(e.target.value)} placeholder="Acme Imports LLC" />
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Industry *</label>
              <input style={fieldStyle} value={industry} onChange={e=>setIndustry(e.target.value)} placeholder="e.g. Consumer Electronics, Auto Parts" />
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Products / SKUs you import</label>
              <textarea style={{...fieldStyle, minHeight:80, resize:'vertical'}}
                value={products} onChange={e=>setProducts(e.target.value)}
                placeholder="e.g. BLDC motors, lithium battery packs, PCBs" />
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Preferred email tone</label>
              <select style={fieldStyle} value={tone} onChange={e=>setTone(e.target.value)}>
                <option value="formal">Formal</option>
                <option value="casual">Casual</option>
                <option value="assertive">Assertive</option>
              </select>
            </div>
            <Btn onClick={()=>setStep(1)} disabled={!companyName || !industry}>Next →</Btn>
          </div>
        )}

        {step === 1 && (
          <div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Supplier countries (comma-separated ISO codes)</label>
              <input style={fieldStyle} value={countries} onChange={e=>setCountries(e.target.value)} placeholder="CN, TW, MX, VN" />
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Monthly import volume (USD)</label>
              <input style={fieldStyle} type="number" value={importUsd} onChange={e=>setImportUsd(e.target.value)} placeholder="500000" />
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Existing supplier relationships</label>
              <textarea style={{...fieldStyle, minHeight:72, resize:'vertical'}}
                value={relationships} onChange={e=>setRelationships(e.target.value)}
                placeholder="e.g. 5-year contract with Bafang, spot buyer at CATL" />
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Biggest tariff concern</label>
              <input style={fieldStyle} value={tariffConcern} onChange={e=>setTariffConcern(e.target.value)} placeholder="e.g. Section 301 China tariffs on HTS 8501" />
            </div>
            <div style={{display:'flex', gap:10}}>
              <Btn variant="ghost" onClick={()=>setStep(0)}>← Back</Btn>
              <Btn onClick={()=>setStep(2)}>Next →</Btn>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Product Name</label>
              <input style={fieldStyle} value={productName} onChange={e=>setProductName(e.target.value)} placeholder="e.g. Precision Coffee Grinder" />
            </div>

            <div style={{marginBottom: 20}}>
              <label style={labelStyle}>Bill of Materials (Parts list)</label>
              <div style={{background:'rgba(0,0,0,0.15)', borderRadius:8, border:'1px solid var(--border-1)', overflow:'hidden'}}>
                <table style={{width:'100%', borderCollapse:'collapse', fontSize:13}}>
                  <thead>
                    <tr style={{background:'rgba(255,255,255,0.02)', textAlign:'left', color:'var(--fg-2)', borderBottom:'1px solid var(--border-1)'}}>
                      <th style={{padding:'8px 12px', fontWeight:500}}>SKU</th>
                      <th style={{padding:'8px 12px', fontWeight:500}}>Description</th>
                      <th style={{padding:'8px 12px', fontWeight:500}}>Country</th>
                      <th style={{padding:'8px 12px', fontWeight:500}}>Cost ($)</th>
                      <th style={{padding:'8px 12px'}}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {parts.map((p, idx) => (
                      <tr key={idx} style={{borderBottom:'1px solid var(--border-1)'}}>
                        <td style={{padding:0}}><input style={{...fieldStyle, border:'none', background:'transparent', borderRadius:0}} placeholder="SKU-123" value={p.sku_code} onChange={e=>{const n=[...parts]; n[idx].sku_code=e.target.value; setParts(n)}} /></td>
                        <td style={{padding:0}}><input style={{...fieldStyle, border:'none', background:'transparent', borderRadius:0}} placeholder="Motor" value={p.description} onChange={e=>{const n=[...parts]; n[idx].description=e.target.value; setParts(n)}} /></td>
                        <td style={{padding:0}}><input style={{...fieldStyle, border:'none', background:'transparent', borderRadius:0}} placeholder="CN" value={p.supplier_country} onChange={e=>{const n=[...parts]; n[idx].supplier_country=e.target.value; setParts(n)}} /></td>
                        <td style={{padding:0}}><input style={{...fieldStyle, border:'none', background:'transparent', borderRadius:0}} type="number" placeholder="25" value={p.unit_cost_usd} onChange={e=>{const n=[...parts]; n[idx].unit_cost_usd=e.target.value; setParts(n)}} /></td>
                        <td style={{padding:'0 12px', textAlign:'right'}}>
                          <button onClick={()=>setParts(parts.filter((_,i)=>i!==idx))} style={{background:'transparent', border:'none', color:'var(--sev-critical)', cursor:'pointer', fontSize:14}}>&times;</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{padding:'8px 12px', background:'rgba(255,255,255,0.02)'}}>
                  <button onClick={()=>setParts([...parts, {sku_code:'', description:'', supplier_country:'', unit_cost_usd:''}])} style={{background:'transparent', border:'none', color:'var(--accent)', cursor:'pointer', fontSize:13, fontWeight:500}}>+ Add Part</button>
                </div>
              </div>
            </div>

            <div style={{display:'flex', alignItems:'center', gap:12, marginBottom: 20}}>
               <div style={{flex:1, height:1, background:'var(--border-1)'}}></div>
               <div style={{fontSize:11, color:'var(--fg-3)', textTransform:'uppercase'}}>Or Upload CSV</div>
               <div style={{flex:1, height:1, background:'var(--border-1)'}}></div>
            </div>

            <div style={fieldGroup}>
              <div style={{...fieldStyle, padding:'8px 12px', cursor:'pointer', color:'var(--fg-3)'}}>
                <input type="file" accept=".csv,.tsv" style={{width:'100%'}}
                  onChange={e=>setBomFile(e.target.files?.[0]||null)} />
              </div>
              {bomFile && <div style={{marginTop:6, color:'var(--sev-low)', fontSize:13}}>✓ {bomFile.name}</div>}
            </div>
            
            <div style={fieldGroup}>
              <label style={labelStyle}>Supporting PDFs (optional — supplier contracts)</label>
              <input type="file" accept=".pdf" multiple style={{...fieldStyle, padding:'8px 12px'}}
                onChange={e=>setPdfFiles(Array.from(e.target.files||[]))} />
              {pdfFiles.length > 0 && (
                <div style={{marginTop:6, color:'var(--sev-low)', fontSize:13}}>
                  ✓ {pdfFiles.map(f=>f.name).join(', ')}
                </div>
              )}
            </div>
            {error && (
              <div style={{background:'var(--orange-050)', border:'1px solid var(--orange-300)',
                borderRadius:8, padding:'10px 14px', marginBottom:16, color:'var(--sev-critical)', fontSize:13}}>
                {error}
              </div>
            )}
            <div style={{display:'flex', gap:10}}>
              <Btn variant="ghost" onClick={()=>setStep(1)}>← Back</Btn>
              <Btn onClick={submit} disabled={saving}>{saving ? 'Saving…' : 'Submit Product'}</Btn>
            </div>
          </div>
        )}
      </Glass>
    </div>
  );
}
