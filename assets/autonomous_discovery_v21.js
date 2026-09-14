(() => {
  if (window.__SB_V21_AUTONOMOUS_DISCOVERY__) return;
  window.__SB_V21_AUTONOMOUS_DISCOVERY__ = true;

  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const folder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad ? 'error' : 'log'](text);
  const safe = value => { try { const u = new URL(String(value || '')); return /^https?:$/.test(u.protocol) ? u.href : ''; } catch (_) { return ''; } };

  let snapshot = null;
  let busy = false;
  let currentFolder = null;
  let baseSelectFolder = null;

  function styles() {
    if (q('#v21-style')) return;
    const style = document.createElement('style');
    style.id = 'v21-style';
    style.textContent = `
      .v21-card{border:1px solid #e4e7ec;border-radius:13px;padding:14px;background:#fff;margin-top:14px}.v21-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}.v21-controls{display:grid;grid-template-columns:minmax(240px,1fr) 120px 115px auto;gap:8px;align-items:end;margin-top:12px}.v21-controls label{font-size:10px;color:#475467}.v21-controls input,.v21-controls select{width:100%;margin-top:4px}.v21-note{padding:9px 11px;border:1px solid #b2ccff;background:#f5f8ff;border-radius:9px;color:#344054;font-size:10px;line-height:1.45;margin-top:10px}.v21-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.v21-badge{font-size:9px;padding:4px 7px;border-radius:999px;background:#f2f4f7;color:#344054}.v21-badge.ok{background:#ecfdf3;color:#067647}.v21-badge.warn{background:#fffaeb;color:#93370d}.v21-badge.bad{background:#fef3f2;color:#b42318}.v21-plan{margin-top:10px;border:1px solid #e4e7ec;border-radius:10px;background:#f9fafb;padding:10px}.v21-plan details+details{margin-top:6px}.v21-query{font-size:10px;line-height:1.45;border-top:1px solid #eaecf0;padding:7px 0}.v21-query:first-child{border-top:0}.v21-list-head{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-top:12px;flex-wrap:wrap}.v21-candidates{display:grid;gap:10px;margin-top:10px}.v21-candidate{border:1px solid #e4e7ec;border-radius:11px;padding:12px}.v21-candidate.included{border-color:#abefc6;background:#f6fef9}.v21-candidate.excluded{opacity:.72;background:#fcfcfd}.v21-candidate-top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.v21-candidate h3{font-size:12px;margin:0;line-height:1.4}.v21-score{min-width:58px;text-align:center;border-radius:9px;background:#f2f4f7;padding:7px 6px;font-size:9px}.v21-score strong{display:block;font-size:16px}.v21-meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:7px;font-size:9px;color:#667085}.v21-reason{font-size:10px;line-height:1.5;color:#344054;margin-top:8px}.v21-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px}.v21-sub{border:1px solid #eaecf0;border-radius:8px;padding:8px;font-size:9px;line-height:1.4}.v21-sub strong{display:block;margin-bottom:4px}.v21-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}.v21-actions button,.v21-actions a{font-size:9px}.v21-empty{padding:15px;text-align:center;color:#667085;font-size:11px}.v21-risk{display:inline-flex;padding:3px 6px;border-radius:999px;background:#fff4e5;color:#b54708;margin:2px 3px 2px 0}.v21-filter{min-width:170px}.v21-statusline{font-size:10px;color:#667085;margin-top:8px}
      @media(max-width:900px){.v21-controls{grid-template-columns:1fr 1fr}.v21-grid{grid-template-columns:1fr}}@media(max-width:620px){.v21-controls{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function ensureCard() {
    const view = q('#view-workspace');
    if (!view || q('#v21-discovery-card')) return;
    const card = document.createElement('article');
    card.id = 'v21-discovery-card';
    card.className = 'v21-card';
    card.innerHTML = `
      <div class="v21-head"><div><h2>${esc(tr('Descubrimiento autónomo y screening','Autonomous discovery and screening'))}</h2><p class="muted">${esc(tr('ScientificBrain convierte preguntas, brechas, contradicciones e hipótesis del corpus en búsquedas dirigidas. Los candidatos siguen siendo material de descubrimiento: no se convierten en evidencia hasta agregarlos y revisar el texto completo.','ScientificBrain converts corpus questions, gaps, contradictions and hypotheses into targeted searches. Candidates remain discovery material: they do not become evidence until added and full-text reviewed.'))}</p></div><button id="v21-refresh" class="ghost">${esc(tr('Actualizar','Refresh'))}</button></div>
      <div class="v21-controls">
        <label>${esc(tr('Foco opcional','Optional focus'))}<input id="v21-focus" placeholder="${esc(tr('Ej.: medición directa de impulse bit y errores metrológicos','e.g. direct impulse-bit measurement and metrology errors'))}"></label>
        <label>${esc(tr('Desde año','From year'))}<input id="v21-year" type="number" min="1900" max="2100" value="1900"></label>
        <label>${esc(tr('Búsquedas','Queries'))}<select id="v21-max-queries"><option>2</option><option>3</option><option selected>4</option><option>5</option><option>6</option></select></label>
        <button id="v21-run" class="primary">${esc(tr('Buscar brechas automáticamente','Autonomous gap search'))}</button>
      </div>
      <div class="v21-note">${esc(tr('El ranking usa metadatos/abstract y acceso para priorizar screening. Relevancia alta no significa que el paper sostenga una afirmación; eso se decide únicamente después del análisis full-text.','Ranking uses metadata/abstract and access to prioritize screening. High relevance does not mean the paper supports a claim; that is decided only after full-text review.'))}</div>
      <div id="v21-status" class="v21-statusline"></div>
      <div id="v21-counts" class="v21-badges"></div>
      <div id="v21-plan"></div>
      <div class="v21-list-head"><strong>${esc(tr('Candidatos priorizados','Prioritized candidates'))}</strong><select id="v21-filter" class="v21-filter"><option value="pending">${esc(tr('Pendientes','Pending'))}</option><option value="later">${esc(tr('Revisar después','Review later'))}</option><option value="included">${esc(tr('Agregados','Included'))}</option><option value="excluded">${esc(tr('Excluidos','Excluded'))}</option><option value="all">${esc(tr('Todos','All'))}</option></select></div>
      <div id="v21-candidates" class="v21-candidates"><div class="v21-empty">${esc(tr('Aún no hay screening autónomo para esta carpeta.','No autonomous screening has been run for this folder yet.'))}</div></div>
    `;
    const discovery = q('#v18-discovery');
    if (discovery?.parentNode === view) view.insertBefore(card, discovery); else view.appendChild(card);
    q('#v21-run').onclick = runDiscovery;
    q('#v21-refresh').onclick = () => loadScreening(true);
    q('#v21-filter').onchange = renderCandidates;
  }

  function renderCounts() {
    const box = q('#v21-counts'); if (!box) return;
    const counts = snapshot?.counts || {};
    const total = Object.values(counts).reduce((a,b)=>a+Number(b||0),0);
    box.innerHTML = [
      [total,tr('candidatos','candidates'),''],
      [counts.pending||0,tr('pendientes','pending'),'warn'],
      [counts.included||0,tr('agregados','included'),'ok'],
      [counts.later||0,tr('para después','later'),''],
      [counts.excluded||0,tr('excluidos','excluded'),'bad'],
    ].map(([n,label,cls])=>`<span class="v21-badge ${cls}">${esc(n)} ${esc(label)}</span>`).join('');
  }

  function renderPlan(run=null) {
    const box=q('#v21-plan'); if(!box)return;
    run = run || snapshot?.runs?.[0];
    if(!run){box.innerHTML='';return;}
    const plan=run.plan||{}; const queries=plan.queries||run.queries||[];
    box.innerHTML=`<div class="v21-plan"><details open><summary><strong>${esc(tr('Plan de búsqueda','Search plan'))}</strong> · ${esc(run.status||'')}</summary>${queries.map(item=>`<div class="v21-query"><strong>${esc(item.query||'')}</strong><br>${esc(item.purpose||'')}${item.target_gap?`<br><span class="v21-mini">${esc(tr('Brecha objetivo','Target gap'))}: ${esc(item.target_gap)}</span>`:''}${item.target_hypothesis?`<br><span class="v21-mini">${esc(tr('Hipótesis objetivo','Target hypothesis'))}: ${esc(item.target_hypothesis)}</span>`:''}</div>`).join('')||'—'}</details><details><summary>${esc(tr('Criterios de inclusión/exclusión','Inclusion/exclusion criteria'))}</summary><div class="v21-grid"><div class="v21-sub"><strong>${esc(tr('Incluir si','Include if'))}</strong>${(plan.inclusion_criteria||run.criteria?.inclusion||[]).map(x=>`<div>• ${esc(x)}</div>`).join('')||'—'}</div><div class="v21-sub"><strong>${esc(tr('Excluir si','Exclude if'))}</strong>${(plan.exclusion_criteria||run.criteria?.exclusion||[]).map(x=>`<div>• ${esc(x)}</div>`).join('')||'—'}</div></div></details></div>`;
  }

  function relationText(item) {
    if (!item) return '';
    const relation = String(item.relation || '').replaceAll('_',' ');
    return `${item.hypothesis || ''}${relation ? ` · ${relation}` : ''}`;
  }

  function candidateHtml(row) {
    const score=Math.round(Number(row.relevance_score||0)*100);
    const status=row.decision||'pending';
    const url=safe(row.pdf_url||row.source_url);
    const gaps=(row.target_gaps||[]).slice(0,5);
    const hypotheses=(row.target_hypotheses||[]).slice(0,5);
    const risks=(row.risks||[]).slice(0,6);
    const origins=(row.query_origins||[]).slice(0,4);
    const canAdd=status!=='included';
    return `<div class="v21-candidate ${esc(status)}" data-candidate="${esc(row.candidate_id)}"><div class="v21-candidate-top"><div><h3>${esc(row.title||'Untitled')}</h3><div class="v21-meta"><span>${esc(row.publication_date||'')}</span><span>${esc(row.journal||row.source||'')}</span>${row.doi?`<span>DOI ${esc(row.doi)}</span>`:''}<span>${esc(row.access_label||row.access_kind||'')}</span><span>${esc(tr('estado','status'))}: ${esc(status)}</span></div></div><div class="v21-score"><strong>${esc(score)}%</strong>${esc(tr('prioridad','priority'))}</div></div><div class="v21-reason">${esc(row.screening_reason||'')}</div><div class="v21-grid"><div class="v21-sub"><strong>${esc(tr('Brecha que podría cubrir','Gap it could address'))}</strong>${gaps.map(x=>`<div>• ${esc(x)}</div>`).join('')||'—'}</div><div class="v21-sub"><strong>${esc(tr('Relación hipotética','Hypothesis relation'))}</strong>${hypotheses.map(x=>`<div>• ${esc(relationText(x))}</div>`).join('')||'—'}</div><div class="v21-sub"><strong>${esc(tr('Contribución esperada del full-text','Expected full-text contribution'))}</strong>${esc(row.expected_contribution||'—')}</div><div class="v21-sub"><strong>${esc(tr('Riesgos de screening','Screening risks'))}</strong>${risks.map(x=>`<span class="v21-risk">${esc(x)}</span>`).join('')||'—'}</div></div>${origins.length?`<details style="margin-top:8px"><summary class="v21-mini">${esc(tr('Por qué apareció en la búsqueda','Why it appeared in search'))}</summary>${origins.map(x=>`<div class="v21-query"><strong>${esc(x.query||'')}</strong><br>${esc(x.purpose||'')}</div>`).join('')}</details>`:''}${row.decision_reason?`<div class="v21-statusline">${esc(tr('Decisión','Decision'))}: ${esc(row.decision_reason)}</div>`:''}<div class="v21-actions">${url?`<a class="secondary linklike" target="_blank" rel="noopener" href="${esc(url)}">${esc(row.pdf_url?tr('Abrir PDF','Open PDF'):tr('Abrir fuente','Open source'))}</a>`:''}${canAdd?`<button class="primary v21-add" data-id="${esc(row.candidate_id)}">${esc(tr('Agregar al corpus','Add to corpus'))}</button>`:'<span class="v21-badge ok">'+esc(tr('Ya agregado','Already added'))+'</span>'}${status!=='excluded'?`<button class="ghost v21-exclude" data-id="${esc(row.candidate_id)}">${esc(tr('Excluir','Exclude'))}</button>`:''}${status!=='later'&&status!=='included'?`<button class="ghost v21-later" data-id="${esc(row.candidate_id)}">${esc(tr('Revisar después','Review later'))}</button>`:''}${status!=='pending'&&status!=='included'?`<button class="ghost v21-pending" data-id="${esc(row.candidate_id)}">${esc(tr('Volver a pendiente','Back to pending'))}</button>`:''}</div></div>`;
  }

  function renderCandidates() {
    const box=q('#v21-candidates'); if(!box)return;
    renderCounts(); renderPlan();
    const filter=q('#v21-filter')?.value||'pending';
    const rows=(snapshot?.candidates||[]).filter(row=>filter==='all'||row.decision===filter);
    if(!rows.length){box.innerHTML=`<div class="v21-empty">${esc(tr('No hay candidatos en este estado.','No candidates in this state.'))}</div>`;return;}
    box.innerHTML=rows.map(candidateHtml).join('');
    qa('.v21-add').forEach(button=>button.onclick=()=>addCandidate(button.dataset.id,button));
    qa('.v21-exclude').forEach(button=>button.onclick=()=>excludeCandidate(button.dataset.id));
    qa('.v21-later').forEach(button=>button.onclick=()=>setDecision(button.dataset.id,'later',tr('Marcado para revisión posterior','Marked for later review')));
    qa('.v21-pending').forEach(button=>button.onclick=()=>setDecision(button.dataset.id,'pending',''));
  }

  async function loadScreening(force=false) {
    const f=folder(); if(!f?.folder_id)return null;
    if(!force&&currentFolder===f.folder_id&&snapshot)return snapshot;
    currentFolder=f.folder_id;
    const status=q('#v21-status'); if(status) status.textContent=tr('Cargando screening persistente…','Loading persistent screening…');
    try {
      snapshot=await api(`/api/research?op=screening&folder_id=${encodeURIComponent(f.folder_id)}&limit=300`);
      renderCandidates();
      if(status) status.textContent=snapshot?.runs?.length?tr('Screening persistente cargado.','Persistent screening loaded.'):tr('Sin ejecuciones previas.','No previous runs.');
      return snapshot;
    } catch(error){
      if(status)status.textContent=error.message||String(error);
      return null;
    }
  }

  async function runDiscovery() {
    const f=folder(); if(!f?.folder_id||busy)return;
    const button=q('#v21-run'); const status=q('#v21-status');
    busy=true; button.disabled=true;
    status.textContent=tr('Planificando búsquedas, consultando literatura y priorizando candidatos…','Planning searches, querying literature and prioritizing candidates…');
    try {
      const result=await api('/api/research?op=autonomous_discovery',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,focus:q('#v21-focus')?.value?.trim()||'',from_year:Number(q('#v21-year')?.value||1900),max_queries:Number(q('#v21-max-queries')?.value||4),per_query:12,language:lang()})});
      notify(tr(`Descubrimiento completado: ${result.candidates?.length||0} candidatos priorizados.`,`Discovery completed: ${result.candidates?.length||0} prioritized candidates.`));
      await loadScreening(true);
      renderPlan({status:result.status,plan:result.plan,criteria:{inclusion:result.plan?.inclusion_criteria||[],exclusion:result.plan?.exclusion_criteria||[]}});
      status.textContent=result.errors?.length?tr(`Completado con ${result.errors.length} advertencia(s) de fuente.`,`Completed with ${result.errors.length} source warning(s).`):tr('Descubrimiento autónomo completado.','Autonomous discovery completed.');
    } catch(error){
      status.textContent=error.message||String(error); notify(`${tr('Descubrimiento falló','Discovery failed')}: ${error.message}`,true);
    } finally {busy=false;button.disabled=false;}
  }

  async function setDecision(id,decision,reason='') {
    const f=folder(); if(!f?.folder_id)return;
    try {
      await api('/api/research?op=screen_decision',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,candidate_id:id,decision,reason})});
      await loadScreening(true);
    } catch(error){notify(error.message,true);}
  }

  async function excludeCandidate(id) {
    const reason=window.prompt(tr('Razón de exclusión (queda registrada para trazabilidad):','Exclusion reason (stored for traceability):'),tr('No prioritario para la pregunta actual','Not a priority for the current question'));
    if(reason===null)return;
    await setDecision(id,'excluded',reason);
  }

  async function addCandidate(id,button) {
    const f=folder(); if(!f?.folder_id)return;
    button.disabled=true; button.textContent=tr('Agregando…','Adding…');
    try {
      const result=await api('/api/research?op=add_candidate',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,candidate_id:id})});
      notify(result.review_job?tr('Paper agregado. El análisis full-text quedó en cola automática.','Paper added. Full-text review was queued automatically.'):tr('Paper agregado al corpus.','Paper added to corpus.'));
      if(typeof loadLibrary==='function') await loadLibrary();
      await loadScreening(true);
    } catch(error){notify(error.message,true);button.disabled=false;button.textContent=tr('Agregar al corpus','Add to corpus');}
  }

  function installFolderHook() {
    if(typeof selectFolder!=='function'||window.__SB_V21_FOLDER_HOOK__)return;
    window.__SB_V21_FOLDER_HOOK__=true;
    baseSelectFolder=selectFolder;
    selectFolder=async function(...args){const result=await baseSelectFolder.apply(this,args);currentFolder=null;snapshot=null;await loadScreening(true);return result;};
  }

  function boot() {
    styles(); ensureCard(); installFolderHook(); loadScreening(false);
  }

  if(document.readyState==='loading')window.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();
})();