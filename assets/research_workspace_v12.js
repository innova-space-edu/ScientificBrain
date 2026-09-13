(() => {
  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const h = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const folder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad?'error':'log'](text);
  const selected = new Set();
  let observer = null;
  let busy = false;

  function styles() {
    if (q('#v12-style')) return;
    const s = document.createElement('style');
    s.id = 'v12-style';
    s.textContent = `
      .v12-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 12px;padding:10px;border:1px solid #e4e7ec;border-radius:12px;background:#f9fafb}.v12-toolbar .v12-count{font-size:11px;color:#475467;margin-right:auto}.v12-select{display:flex;align-items:center;justify-content:center;margin-right:8px}.v12-select input{width:16px;height:16px}.v12-mini-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}.v12-mini-actions button{font-size:10px;padding:5px 8px}.v12-panel{border:1px solid #e4e7ec;border-radius:13px;padding:14px;background:#fff;margin-top:14px}.v12-panel-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.v12-panel-actions{display:flex;gap:7px;flex-wrap:wrap}.v12-stale{display:none;margin-top:10px;padding:9px 11px;border:1px solid #fedf89;background:#fffaeb;color:#93370d;border-radius:10px;font-size:11px}.v12-stale.show{display:block}.v12-modal{position:fixed;inset:0;z-index:12000;background:rgba(16,24,40,.58);display:flex;align-items:center;justify-content:center;padding:18px}.v12-modal.hidden{display:none}.v12-dialog{width:min(1040px,97vw);max-height:92vh;overflow:auto;background:#fff;border-radius:16px;padding:16px;box-shadow:0 28px 80px rgba(0,0,0,.28)}.v12-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.v12-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.v12-card{border:1px solid #e4e7ec;border-radius:11px;padding:11px}.v12-card h3{margin:0 0 8px}.v12-list{display:grid;gap:7px}.v12-item{padding:8px;border-bottom:1px solid #f2f4f7;font-size:11px;line-height:1.4}.v12-item:last-child{border-bottom:0}.v12-output{white-space:pre-wrap;font-size:11px;line-height:1.5;background:#f8fafc;border:1px solid #e4e7ec;border-radius:10px;padding:11px;max-height:52vh;overflow:auto}.v12-table{width:100%;border-collapse:collapse;font-size:10px}.v12-table th,.v12-table td{border:1px solid #e4e7ec;padding:7px;vertical-align:top;text-align:left}.v12-version{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px;border-bottom:1px solid #f2f4f7}.v12-version:last-child{border-bottom:0}.v12-badge{display:inline-flex;padding:3px 7px;border-radius:999px;font-size:9px;background:#f2f4f7;color:#344054}.v12-badge.ok{background:#ecfdf3;color:#067647}.v12-visual-controls{display:grid;grid-template-columns:110px 1fr;gap:8px}.v12-visual-controls textarea{grid-column:1/-1;min-height:80px}.v12-progress{font-size:10px;color:#667085;margin-top:6px}@media(max-width:800px){.v12-grid{grid-template-columns:1fr}.v12-visual-controls{grid-template-columns:1fr}}
    `;
    document.head.appendChild(s);
  }

  function ensureModal() {
    if (q('#v12-modal')) return;
    const el = document.createElement('div');
    el.id = 'v12-modal'; el.className = 'v12-modal hidden';
    el.innerHTML = `<div class="v12-dialog"><div class="v12-head"><div><h2 id="v12-title">ScientificBrain v0.12</h2><p id="v12-subtitle" class="muted"></p></div><button id="v12-close" class="ghost">×</button></div><div id="v12-body" style="margin-top:12px"></div></div>`;
    document.body.appendChild(el);
    q('#v12-close').onclick = () => el.classList.add('hidden');
    el.addEventListener('click', e => { if (e.target === el) el.classList.add('hidden'); });
  }

  function openModal(title, subtitle='') {
    ensureModal();
    q('#v12-title').textContent = title;
    q('#v12-subtitle').textContent = subtitle;
    q('#v12-body').innerHTML = '';
    q('#v12-modal').classList.remove('hidden');
  }

  function selectedPapers() {
    return [...selected].map(id => (state.library || []).find(p => p.canonical_id === id)).filter(Boolean);
  }

  function updateSelectionUI() {
    const count = selected.size;
    const el = q('#v12-selection-count');
    if (el) el.textContent = `${count} ${tr('seleccionado(s)','selected')}`;
    const button = q('#v12-compare');
    if (button) button.disabled = count < 2 || count > 10 || busy;
    qa('.v12-paper-select').forEach(input => { input.checked = selected.has(input.dataset.paperId); });
  }

  function installLibraryToolbar() {
    const list = q('#paper-list');
    if (!list) return;
    const card = list.closest('.card');
    if (!card || q('#v12-library-toolbar')) return;
    const toolbar = document.createElement('div');
    toolbar.id = 'v12-library-toolbar'; toolbar.className = 'v12-toolbar';
    toolbar.innerHTML = `<strong>${h(tr('Comparador científico','Scientific comparator'))}</strong><span id="v12-selection-count" class="v12-count">0 ${h(tr('seleccionado(s)','selected'))}</span><button id="v12-compare" class="secondary" disabled>${h(tr('Comparar papers','Compare papers'))}</button><button id="v12-clear" class="ghost">${h(tr('Limpiar','Clear'))}</button>`;
    list.before(toolbar);
    q('#v12-compare').onclick = compareSelected;
    q('#v12-clear').onclick = () => { selected.clear(); updateSelectionUI(); };
  }

  function enhanceRows() {
    installLibraryToolbar();
    qa('#paper-list .paper-row').forEach(row => {
      const itemId = row.querySelector('.delete-paper')?.dataset.item;
      const paper = (state.library || []).find(p => p.item_id === itemId);
      if (!paper || !paper.canonical_id) return;
      if (!row.querySelector('.v12-select')) {
        const wrap = document.createElement('label'); wrap.className = 'v12-select'; wrap.title = tr('Seleccionar para comparar','Select to compare');
        const input = document.createElement('input'); input.type = 'checkbox'; input.className = 'v12-paper-select'; input.dataset.paperId = paper.canonical_id;
        input.checked = selected.has(paper.canonical_id);
        input.onchange = () => { input.checked ? selected.add(paper.canonical_id) : selected.delete(paper.canonical_id); updateSelectionUI(); };
        wrap.appendChild(input); row.prepend(wrap);
      }
      const actions = row.querySelector('.paper-actions') || row;
      if (!row.querySelector('.v12-structure')) {
        const b = document.createElement('button'); b.className = 'ghost v12-structure'; b.textContent = tr('Estructura','Structure'); b.onclick = () => showPaperIntelligence(paper); actions.prepend(b);
      }
    });
    updateSelectionUI();
  }

  function renderComparison(result) {
    const c = result.comparison || {};
    const sources = result.sources || [];
    const rows = c.matrix || [];
    const labels = sources.map(s => `[${s.number}]`);
    const table = rows.length ? `<table class="v12-table"><thead><tr><th>${h(tr('Dimensión','Dimension'))}</th>${labels.map(x=>`<th>${h(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${h(r.dimension||'')}</strong></td>${labels.map(label=>`<td>${h((r.papers||{})[label]||'—')}</td>`).join('')}</tr>`).join('')}</tbody></table>` : '';
    return `<div class="v12-card"><h3>${h(tr('Síntesis','Synthesis'))}</h3><div class="v12-output">${h(c.executive_synthesis||'')}</div></div>${table}<div class="v12-grid" style="margin-top:12px"><div class="v12-card"><h3>${h(tr('Acuerdos','Agreements'))}</h3><div class="v12-list">${(c.agreements||[]).map(x=>`<div class="v12-item">${h(x)}</div>`).join('')||'—'}</div></div><div class="v12-card"><h3>${h(tr('Contradicciones','Contradictions'))}</h3><div class="v12-list">${(c.contradictions||[]).map(x=>`<div class="v12-item"><strong>${h(x.issue||'')}</strong><br>${h((x.sources||[]).join(', '))}<br>${h((x.possible_explanations||[]).join(' · '))}</div>`).join('')||'—'}</div></div><div class="v12-card"><h3>${h(tr('Chequeo matemático','Mathematical checks'))}</h3><div class="v12-list">${(c.mathematical_checks||[]).map(x=>`<div class="v12-item">${h(x)}</div>`).join('')||'—'}</div></div><div class="v12-card"><h3>${h(tr('Chequeo estadístico','Statistical checks'))}</h3><div class="v12-list">${(c.statistical_checks||[]).map(x=>`<div class="v12-item">${h(x)}</div>`).join('')||'—'}</div></div></div>`;
  }

  async function compareSelected() {
    const f = folder(); const papers = selectedPapers();
    if (!f || papers.length < 2) return;
    openModal(tr('Comparador científico de papers','Scientific paper comparator'), papers.map(p=>p.title).join(' · '));
    q('#v12-body').innerHTML = `<label>${h(tr('Foco específico de la comparación (opcional)','Specific comparison focus (optional)'))}<textarea id="v12-compare-focus" style="width:100%;min-height:75px"></textarea></label><div style="margin-top:9px"><button id="v12-run-compare" class="primary">${h(tr('Ejecutar comparación profunda','Run deep comparison'))}</button></div><div id="v12-compare-result" style="margin-top:12px"></div>`;
    q('#v12-run-compare').onclick = async () => {
      const button = q('#v12-run-compare'); busy = true; button.disabled = true; updateSelectionUI();
      const out = q('#v12-compare-result'); out.innerHTML = `<div class="v12-progress">${h(tr('Comparando modelos, variables, métodos, resultados, incertidumbre y reproducibilidad…','Comparing models, variables, methods, results, uncertainty and reproducibility…'))}</div>`;
      try {
        const r = await api('/api/paper?op=compare', {method:'POST', body:JSON.stringify({folder_id:f.folder_id,paper_ids:papers.map(p=>p.canonical_id),focus:q('#v12-compare-focus').value.trim(),language:lang()})});
        out.innerHTML = renderComparison(r);
      } catch (e) { out.textContent = e.message; notify(e.message, true); }
      finally { busy = false; button.disabled = false; updateSelectionUI(); }
    };
  }

  async function showPaperIntelligence(paper) {
    const f = folder(); if (!f) return;
    openModal(`${tr('Memoria estructural','Structural memory')} · ${paper.title||paper.canonical_id}`, tr('Páginas, secciones, figuras, tablas, ecuaciones y análisis visual bajo demanda.','Pages, sections, figures, tables, equations and on-demand visual analysis.'));
    const body = q('#v12-body'); body.innerHTML = `<div class="v12-progress">${h(tr('Cargando índice persistente…','Loading persistent index…'))}</div>`;
    try {
      const [structure, assets] = await Promise.all([
        api(`/api/paper?op=structure&folder_id=${encodeURIComponent(f.folder_id)}&paper_id=${encodeURIComponent(paper.canonical_id)}`),
        api(`/api/paper?op=assets&folder_id=${encodeURIComponent(f.folder_id)}&paper_id=${encodeURIComponent(paper.canonical_id)}`),
      ]);
      const headings = structure.structure?.headings || [];
      const assetRows = assets.assets || [];
      const summary = structure.asset_summary || {};
      const equations = assetRows.filter(a=>a.asset_type==='equation_candidate');
      const captions = assetRows.filter(a=>a.asset_type==='figure_caption'||a.asset_type==='table_caption');
      body.innerHTML = `<div class="v12-grid"><div class="v12-card"><h3>${h(tr('Estructura detectada','Detected structure'))}</h3><div class="v12-list">${headings.slice(0,80).map(x=>`<div class="v12-item"><span class="v12-badge">p.${h(x.page)}</span> ${h(x.title)}</div>`).join('')||h(tr('Sin encabezados detectados.','No headings detected.'))}</div></div><div class="v12-card"><h3>${h(tr('Inventario científico','Scientific inventory'))}</h3><div class="v12-list"><div class="v12-item">${h(tr('Fragmentos indexados','Indexed chunks'))}: <strong>${h(summary.chunks||0)}</strong></div><div class="v12-item">${h(tr('Captions de figuras','Figure captions'))}: <strong>${h(summary.figure_caption||0)}</strong></div><div class="v12-item">${h(tr('Captions de tablas','Table captions'))}: <strong>${h(summary.table_caption||0)}</strong></div><div class="v12-item">${h(tr('Ecuaciones candidatas','Equation candidates'))}: <strong>${h(summary.equation_candidate||0)}</strong></div><div class="v12-item">${h(tr('Páginas con contenido visual','Pages with visual content'))}: <strong>${h(summary.visual?.visual_pages||0)}</strong></div></div></div></div><div class="v12-grid" style="margin-top:12px"><div class="v12-card"><h3>${h(tr('Figuras y tablas','Figures and tables'))}</h3><div class="v12-list">${captions.slice(0,80).map(a=>`<div class="v12-item"><span class="v12-badge">p.${h(a.page)}</span> <strong>${h(a.label||a.asset_type)}</strong><br>${h(a.caption||a.text||'')}</div>`).join('')||'—'}</div></div><div class="v12-card"><h3>${h(tr('Ecuaciones detectadas','Detected equations'))}</h3><div class="v12-list">${equations.slice(0,80).map(a=>`<div class="v12-item"><span class="v12-badge">p.${h(a.page)}</span> ${h(a.text||'')}</div>`).join('')||'—'}</div></div></div><div class="v12-card" style="margin-top:12px"><h3>${h(tr('Analizar visualmente una página','Visually analyze a page'))}</h3><p class="muted">${h(tr('Úsalo cuando una conclusión dependa de un gráfico, tabla, ecuación renderizada o diagrama. El resultado queda cacheado.','Use this when a conclusion depends on a plot, table, rendered equation or diagram. The result is cached.'))}</p><div class="v12-visual-controls"><label>${h(tr('Página','Page'))}<input id="v12-visual-page" type="number" min="1" max="${h(structure.page_count||999)}" value="1"></label><span></span><textarea id="v12-visual-question" placeholder="${h(tr('Ej.: analiza la Fig. 4, identifica ejes, unidades, tendencia y qué afirmación puede sostener realmente.','e.g. analyze Fig. 4: identify axes, units, trend and what claim it actually supports.'))}"></textarea></div><button id="v12-run-visual" class="secondary" style="margin-top:8px">${h(tr('Analizar página','Analyze page'))}</button><div id="v12-visual-output" class="v12-output" style="display:none;margin-top:10px"></div></div>`;
      q('#v12-run-visual').onclick = () => analyzeVisualPage(paper);
    } catch (e) { body.textContent = e.message; notify(e.message, true); }
  }

  async function analyzeVisualPage(paper) {
    const f = folder(); if (!f) return;
    const page = Number(q('#v12-visual-page')?.value || 0);
    const question = q('#v12-visual-question')?.value?.trim() || '';
    const out = q('#v12-visual-output'); const b = q('#v12-run-visual');
    if (!page) return notify(tr('Indica una página válida.','Enter a valid page.'), true);
    b.disabled = true; out.style.display = 'block'; out.textContent = tr('Analizando imagen científica…','Analyzing scientific image…');
    try {
      const r = await api('/api/paper?op=visual',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,paper_id:paper.canonical_id,page,question,language:lang()})});
      out.textContent = `${r.answer||''}\n\n${r.cached?tr('Resultado recuperado de memoria visual.','Result retrieved from visual memory.'):tr('Nuevo análisis visual guardado en memoria.','New visual analysis saved to memory.')}`;
    } catch(e) { out.textContent = e.message; notify(e.message,true); }
    finally { b.disabled = false; }
  }

  function installResearchPanel() {
    const view = q('#view-collab'); if (!view || q('#v12-research-tools')) return;
    const panel = document.createElement('article'); panel.id='v12-research-tools'; panel.className='v12-panel';
    panel.innerHTML = `<div class="v12-panel-head"><div><h2>${h(tr('Control científico y versiones','Scientific control and versions'))}</h2><p class="muted">${h(tr('Historial recuperable y exportación reproducible del documento.','Recoverable history and reproducible document export.'))}</p></div><div class="v12-panel-actions"><button id="v12-versions" class="ghost">${h(tr('Versiones','Versions'))}</button><button class="ghost v12-export" data-format="markdown">Markdown</button><button class="ghost v12-export" data-format="latex">LaTeX</button><button class="ghost v12-export" data-format="bibtex">BibTeX</button><button class="ghost v12-export" data-format="json">JSON</button></div></div><div id="v12-stale" class="v12-stale"></div>`;
    view.appendChild(panel);
    q('#v12-versions').onclick = showVersions;
    qa('.v12-export').forEach(b=>b.onclick=()=>exportResearch(b.dataset.format));
    refreshResearchStatus().catch(()=>{});
  }

  async function refreshResearchStatus() {
    const f=folder(), box=q('#v12-stale'); if(!f||!box)return;
    try {
      const r=await api(`/api/collaboration?op=research_workspace&folder_id=${encodeURIComponent(f.folder_id)}`);
      const doc=r.document||{};
      const stale=doc.status==='stale_evidence'||!!doc.stale_reason;
      box.classList.toggle('show',stale);
      box.textContent=stale?`${tr('Nueva evidencia disponible. Las secciones editadas por ti se conservarán; las secciones de IA pueden regenerarse con la nueva evidencia.','New evidence is available. Your manually edited sections will be preserved; AI-owned sections can be regenerated with the new evidence.')} ${doc.stale_reason||''}`:'';
    } catch {}
  }

  async function showVersions() {
    const f=folder(); if(!f)return;
    openModal(tr('Versiones de la investigación','Research versions'),tr('Cada revisión conserva el estado anterior antes de cambios importantes.','Each revision preserves the prior state before important changes.'));
    const body=q('#v12-body');body.innerHTML=`<div class="v12-progress">${h(tr('Cargando historial…','Loading history…'))}</div>`;
    try{
      const r=await api(`/api/collaboration?op=versions&folder_id=${encodeURIComponent(f.folder_id)}`);
      const versions=r.versions||[];
      body.innerHTML=versions.length?versions.map(v=>`<div class="v12-version"><div><strong>r${h(v.revision)}</strong> · ${h(v.reason||'update')}<br><small>${h(v.created_at||'')}</small></div><button class="ghost v12-restore" data-id="${h(v.version_id)}">${h(tr('Restaurar','Restore'))}</button></div>`).join(''):`<p class="muted">${h(tr('Todavía no hay versiones anteriores.','No previous versions yet.'))}</p>`;
      qa('.v12-restore').forEach(b=>b.onclick=()=>restoreVersion(b.dataset.id,b));
    }catch(e){body.textContent=e.message;}
  }

  async function restoreVersion(versionId, button){
    const f=folder();if(!f||!versionId)return;
    if(!confirm(tr('¿Restaurar esta versión? El estado actual se conservará en el historial.','Restore this version? The current state will remain in history.')))return;
    button.disabled=true;
    try{await api('/api/collaboration?op=restore_version',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,version_id:versionId})});notify(tr('Versión restaurada.','Version restored.'));q('#v12-modal').classList.add('hidden');window.location.reload();}catch(e){notify(e.message,true);button.disabled=false;}
  }

  async function exportResearch(format){
    const f=folder();if(!f)return;
    try{
      const r=await api(`/api/collaboration?op=export&folder_id=${encodeURIComponent(f.folder_id)}&format=${encodeURIComponent(format)}`);
      const blob=new Blob([r.content||''],{type:r.mime||'text/plain'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=r.filename||`scientificbrain.${format}`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);notify(tr('Exportación preparada.','Export prepared.'));
    }catch(e){notify(e.message,true);}
  }

  function installObserver(){
    if(observer)return;
    observer=new MutationObserver(()=>{enhanceRows();installResearchPanel();});
    observer.observe(document.body,{childList:true,subtree:true});
  }

  function init(){styles();ensureModal();enhanceRows();installResearchPanel();installObserver();setInterval(()=>{enhanceRows();installResearchPanel();if(q('#view-collab')?.classList.contains('active'))refreshResearchStatus().catch(()=>{});},5000);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
