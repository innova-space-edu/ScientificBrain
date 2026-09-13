(() => {
  const q = s => document.querySelector(s);
  const h = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es,en) => lang()==='en' ? en : es;
  const folder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text,bad=false) => typeof toast === 'function' ? toast(text,bad) : console[bad?'error':'log'](text);
  let busy = false;

  function style(){
    if(q('#v16-quality-style')) return;
    const s=document.createElement('style'); s.id='v16-quality-style';
    s.textContent=`
      .v16-panel{margin:12px 0;padding:13px;border:1px solid #d0d5dd;border-radius:12px;background:#fff;display:grid;gap:10px}
      .v16-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap}.v16-head h3{margin:0;font-size:12px}.v16-head p{margin:4px 0 0;font-size:10px;color:#667085;max-width:720px}
      .v16-metrics{display:grid;grid-template-columns:repeat(5,minmax(100px,1fr));gap:7px}.v16-metric{padding:8px;border:1px solid #eaecf0;border-radius:9px;background:#f9fafb}.v16-metric span{display:block;font-size:9px;color:#667085}.v16-metric strong{font-size:13px}
      .v16-good{color:#067647}.v16-warn{color:#b54708}.v16-bad{color:#b42318}.v16-actions{display:flex;gap:7px;flex-wrap:wrap}.v16-note{font-size:9px;color:#667085;line-height:1.45}
      @media(max-width:900px){.v16-metrics{grid-template-columns:repeat(2,minmax(100px,1fr))}}
    `; document.head.appendChild(s);
  }

  function pct(v){ return Number.isFinite(Number(v)) ? `${(Number(v)*100).toFixed(1)}%` : '—'; }
  function money(v){ return v==null ? '—' : `$${Number(v).toFixed(6)}`; }

  async function getWorkspace(){
    const f=folder(); if(!f?.folder_id) return null;
    return api(`/api/collaboration?op=research_workspace&folder_id=${encodeURIComponent(f.folder_id)}`);
  }
  async function getObs(){
    const f=folder(); if(!f?.folder_id) return null;
    return api(`/api/corpus?op=observability&folder_id=${encodeURIComponent(f.folder_id)}&days=7`);
  }

  function ensure(){
    const view=q('#view-collab'); if(!view) return;
    style();
    if(!q('#v16-quality-panel')){
      const p=document.createElement('div'); p.id='v16-quality-panel'; p.className='v16-panel';
      p.innerHTML=`<div class="v16-head"><div><h3>${h(tr('Calidad científica v0.16','Scientific quality v0.16'))}</h3><p>${h(tr('Entailment contra evidencia full-text, riesgo de sobreafirmación y telemetría real de uso. Las reparaciones nunca modifican secciones marcadas como editadas por el usuario.','Entailment against full-text evidence, overclaim risk and real usage telemetry. Repairs never modify sections marked as user-edited.'))}</p></div></div><div id="v16-metrics" class="v16-metrics"></div><div class="v16-actions"><button id="v16-benchmark" class="secondary">${h(tr('Ejecutar benchmark científico','Run scientific benchmark'))}</button><button id="v16-repair" class="ghost">${h(tr('Reparar solo secciones IA con fallas','Repair failing AI-only sections'))}</button><button id="v16-refresh" class="ghost">${h(tr('Actualizar métricas','Refresh metrics'))}</button></div><div id="v16-note" class="v16-note"></div>`;
      const banner=q('#v15-audit-banner');
      if(banner?.parentNode) banner.parentNode.insertBefore(p,banner.nextSibling); else view.prepend(p);
      q('#v16-benchmark').onclick=benchmark;
      q('#v16-repair').onclick=repair;
      q('#v16-refresh').onclick=refresh;
    }
  }

  function render(ws,obs){
    ensure(); const root=q('#v16-metrics'); if(!root) return;
    const b=ws?.document?.evidence_manifest?.scientific_benchmark || {};
    const m=b.metrics || {};
    const usage=obs?.usage || {};
    const score=b.score;
    const risk=m.hallucination_risk_index;
    root.innerHTML=`
      <div class="v16-metric"><span>${h(tr('Benchmark','Benchmark'))}</span><strong class="${b.passed?'v16-good':score==null?'':'v16-warn'}">${score==null?'—':h(score)+'/100'}</strong></div>
      <div class="v16-metric"><span>${h(tr('Entailment','Entailment'))}</span><strong>${h(pct(m.entailment_rate))}</strong></div>
      <div class="v16-metric"><span>${h(tr('Riesgo (índice, no prob.)','Risk index, not probability'))}</span><strong class="${Number(risk)>0.35?'v16-bad':Number(risk)>0.15?'v16-warn':'v16-good'}">${h(pct(risk))}</strong></div>
      <div class="v16-metric"><span>${h(tr('Tokens 7 días','Tokens 7 days'))}</span><strong>${h(usage.total_tokens_recorded ?? '—')}</strong></div>
      <div class="v16-metric"><span>${h(tr('Costo conocido 7 días','Known cost 7 days'))}</span><strong>${h(money(usage.known_cost_usd))}</strong></div>`;
    const note=q('#v16-note');
    if(note){
      const exact=usage.exact_usage_coverage;
      const blocked=(b.high_risk_claims||[]).length;
      note.textContent=tr(`Cobertura de uso exacto: ${pct(exact)}. Claims de alto riesgo: ${blocked}. El costo solo se registra cuando el proveedor lo informa o existe una tarifa configurada.`,`Exact usage coverage: ${pct(exact)}. High-risk claims: ${blocked}. Cost is recorded only when reported by the provider or a configured rate exists.`);
    }
  }

  async function refresh(){
    const f=folder(); if(!f?.folder_id) return;
    try{ const [ws,obs]=await Promise.all([getWorkspace(),getObs()]); render(ws,obs); }
    catch(e){ console.warn('v0.16 metrics',e); }
  }

  async function benchmark(){
    const f=folder(); if(!f?.folder_id||busy) return; busy=true;
    const b=q('#v16-benchmark'); if(b)b.disabled=true;
    try{
      const r=await api('/api/collaboration?op=benchmark_document',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,language:lang(),use_model:true})});
      const score=r?.benchmark?.score;
      notify(tr(`Benchmark científico completado: ${score ?? '—'}/100.`,`Scientific benchmark completed: ${score ?? '—'}/100.`));
      await refresh();
    }catch(e){notify(e.message,true)}finally{busy=false;if(b)b.disabled=false}
  }

  async function repair(){
    const f=folder(); if(!f?.folder_id||busy) return; busy=true;
    const b=q('#v16-repair'); if(b)b.disabled=true;
    try{
      const r=await api('/api/collaboration?op=repair_failed_sections',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,language:lang(),max_sections:4})});
      const repaired=(r.repaired_sections||[]).length, blocked=(r.blocked_human_sections||[]).length;
      notify(tr(`Reparación terminada: ${repaired} sección(es) IA corregidas; ${blocked} sección(es) humanas preservadas.`,`Repair completed: ${repaired} AI section(s) repaired; ${blocked} human section(s) preserved.`));
      q('#v11-refresh')?.click();
      await refresh();
    }catch(e){notify(e.message,true)}finally{busy=false;if(b)b.disabled=false}
  }

  function boot(){
    ensure();
    document.addEventListener('click',e=>{
      if(e.target?.closest?.('[data-view="collab"]')) setTimeout(refresh,350);
      if(e.target?.closest?.('#v11-generate,#v15-verify,#v11-refresh')) setTimeout(refresh,1400);
    });
    if(q('#view-collab')?.classList.contains('active')) setTimeout(refresh,500);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot); else boot();
})();
