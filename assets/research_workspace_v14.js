(() => {
  const q = s => document.querySelector(s);
  const h = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const activeFolder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad?'error':'log'](text);
  let corpusThread = null;
  let lastFolderId = null;
  let busy = false;

  function styles() {
    if (q('#v14-style')) return;
    const el = document.createElement('style');
    el.id = 'v14-style';
    el.textContent = `
      .v14-shell{margin-top:14px;border:1px solid #d0d5dd;background:linear-gradient(180deg,#fff,#f8fafc)}
      .v14-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(320px,.65fr);gap:14px}
      .v14-pane{border:1px solid #e4e7ec;border-radius:12px;background:#fff;padding:13px}
      .v14-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap}
      .v14-badges{display:flex;gap:6px;flex-wrap:wrap}.v14-badge{font-size:9px;padding:4px 7px;border-radius:999px;background:#f2f4f7;color:#344054}.v14-badge.ok{background:#ecfdf3;color:#067647}.v14-badge.warn{background:#fffaeb;color:#93370d}.v14-badge.bad{background:#fef3f2;color:#b42318}
      .v14-question{width:100%;min-height:92px;resize:vertical}.v14-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px}
      .v14-output{white-space:pre-wrap;line-height:1.55;font-size:12px;padding:12px;border:1px solid #e4e7ec;border-radius:10px;background:#fcfcfd;margin-top:10px;max-height:48vh;overflow:auto}
      .v14-sources{display:grid;gap:7px;margin-top:10px}.v14-source{padding:8px 9px;border:1px solid #eaecf0;border-radius:9px;font-size:10px;line-height:1.4}
      .v14-watch-form{display:grid;grid-template-columns:1fr 92px;gap:7px}.v14-watch-form input:first-child{grid-column:1/-1}.v14-watch-list{display:grid;gap:8px;margin-top:10px}.v14-watch{border:1px solid #e4e7ec;border-radius:10px;padding:9px}.v14-watch-title{font-size:11px;font-weight:650;line-height:1.35}.v14-watch-meta{font-size:9px;color:#667085;margin-top:4px}.v14-watch-actions{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}.v14-watch-actions button{padding:4px 7px;font-size:9px}
      .v14-leads{display:grid;gap:7px;margin-top:9px}.v14-lead{padding:8px;border:1px solid #e4e7ec;border-radius:9px;font-size:10px}.v14-lead a{word-break:break-word}
      .v14-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:9px}.v14-metric{border:1px solid #e4e7ec;border-radius:9px;padding:9px}.v14-metric strong{display:block;font-size:18px}.v14-metric span{font-size:9px;color:#667085}.v14-errors{font-size:9px;white-space:pre-wrap;margin-top:8px;color:#b42318}
      .v14-note{font-size:10px;color:#667085;line-height:1.45;margin-top:7px}
      @media(max-width:900px){.v14-grid{grid-template-columns:1fr}.v14-metrics{grid-template-columns:1fr 1fr}}
    `;
    document.head.appendChild(el);
  }

  function safeUrl(value) {
    try {
      const u = new URL(String(value || ''), location.origin);
      if (u.protocol === 'http:' || u.protocol === 'https:') return u.href;
    } catch (_) {}
    return '';
  }

  function ensurePanel() {
    const view = q('#view-literature');
    if (!view || q('#v14-corpus-shell')) return;
    styles();
    const resultCard = q('#research-results')?.closest('article.card');
    const shell = document.createElement('article');
    shell.id = 'v14-corpus-shell';
    shell.className = 'card v14-shell';
    shell.innerHTML = `
      <div class="card-head"><div><h2>${h(tr('Inteligencia de corpus','Corpus Intelligence'))}</h2><p class="muted">${h(tr('Razonamiento cruzado sobre todos los papers indexados de la carpeta, vigilancia de nueva literatura y observabilidad del sistema.','Cross-paper reasoning over the whole indexed folder, new-literature watch, and system observability.'))}</p></div><div class="v14-badges"><span class="v14-badge">semantic + lexical</span><span class="v14-badge">citation gate</span><span class="v14-badge">Literature Watch</span></div></div>
      <div class="v14-grid">
        <section class="v14-pane">
          <div class="v14-head"><div><strong>${h(tr('Preguntar a toda la carpeta','Ask the whole folder'))}</strong><div class="v14-note">${h(tr('La respuesta usa fragmentos persistentes de múltiples papers y conserva referencias numéricas verificables.','The answer uses persistent chunks from multiple papers and keeps verifiable numbered references.'))}</div></div><button id="v14-new-thread" class="ghost">${h(tr('Nueva conversación','New conversation'))}</button></div>
          <textarea id="v14-question" class="v14-question" placeholder="${h(tr('Ej.: ¿Qué mecanismos explican las diferencias de impulso específico entre las arquitecturas estudiadas y qué evidencia las discrimina?','E.g. Which mechanisms explain differences in specific impulse across the studied architectures, and what evidence discriminates them?'))}"></textarea>
          <div class="v14-actions"><button id="v14-ask" class="primary">${h(tr('Analizar corpus','Analyze corpus'))}</button><button id="v14-semantic-status" class="ghost">${h(tr('Estado semántico','Semantic status'))}</button></div>
          <div id="v14-corpus-result"></div>
        </section>
        <section class="v14-pane">
          <div class="v14-head"><strong>Literature Watch</strong><button id="v14-refresh-watches" class="ghost">${h(tr('Actualizar','Refresh'))}</button></div>
          <div class="v14-watch-form" style="margin-top:8px"><input id="v14-watch-query" placeholder="${h(tr('Consulta que debe vigilarse','Query to watch'))}"/><input id="v14-watch-year" type="number" value="2020" min="1800" max="2100"/><input id="v14-watch-hours" type="number" value="24" min="1" max="720"/></div>
          <div class="v14-actions"><button id="v14-create-watch" class="secondary">${h(tr('Crear vigilancia','Create watch'))}</button><button id="v14-refresh-obs" class="ghost">${h(tr('Observabilidad','Observability'))}</button></div>
          <div class="v14-note">${h(tr('Las novedades son pistas de literatura, no evidencia validada, hasta que el paper se agregue y analice.','New items are literature leads, not validated evidence, until a paper is added and reviewed.'))}</div>
          <div id="v14-watch-list" class="v14-watch-list"></div>
          <div id="v14-observability"></div>
        </section>
      </div>`;
    if (resultCard) view.insertBefore(shell, resultCard); else view.appendChild(shell);

    q('#v14-new-thread').onclick = () => { corpusThread = null; q('#v14-corpus-result').innerHTML = ''; notify(tr('Nueva conversación de corpus.','New corpus conversation.')); };
    q('#v14-ask').onclick = askCorpus;
    q('#v14-semantic-status').onclick = showSemanticStatus;
    q('#v14-create-watch').onclick = createWatch;
    q('#v14-refresh-watches').onclick = refreshWatches;
    q('#v14-refresh-obs').onclick = refreshObservability;
  }

  function folderRequired() {
    const f = activeFolder();
    if (!f?.folder_id) {
      notify(tr('Selecciona una carpeta de investigación.','Select a research folder.'), true);
      return null;
    }
    return f;
  }

  async function askCorpus() {
    const f = folderRequired(); if (!f || busy) return;
    const question = q('#v14-question').value.trim();
    if (!question) return notify(tr('Escribe una pregunta científica.','Enter a scientific question.'), true);
    const out = q('#v14-corpus-result');
    busy = true; q('#v14-ask').disabled = true;
    out.innerHTML = `<div class="v14-note">${h(tr('Recuperando evidencia de múltiples papers, sintetizando y auditando citas…','Retrieving cross-paper evidence, synthesizing, and auditing citations…'))}</div>`;
    try {
      const result = await api('/api/corpus?op=ask', {method:'POST', body:JSON.stringify({folder_id:f.folder_id,question,thread_id:corpusThread,language:lang(),limit:24})});
      corpusThread = result.thread_id || corpusThread;
      const audit = result.citation_audit || {};
      const auditClass = audit.passed ? 'ok' : 'warn';
      const refs = (result.references || []).map(r => `<div class="v14-source"><strong>[${h(r.number)}]</strong> ${h(r.reference || r.title || r.paper_id)}</div>`).join('');
      const contradictions = (result.contradictions || []).map(x => `<div class="v14-source"><strong>${h(x.issue||'')}</strong><br>${h((x.possible_explanations||[]).join(' · '))}</div>`).join('');
      const gaps = (result.gaps || []).map(x => `<div class="v14-source"><strong>${h(x.gap||'')}</strong><br>${h(x.why_unresolved||'')}<br><em>${h(x.decisive_evidence||'')}</em></div>`).join('');
      const emb = result.retrieval?.embedding_stats || {};
      out.innerHTML = `<div class="v14-badges" style="margin-top:10px"><span class="v14-badge ${auditClass}">${h(audit.passed?tr('Citas verificadas','Citations verified'):tr('Revisar citas','Review citations'))}</span><span class="v14-badge">${h(result.references?.length||0)} ${h(tr('papers','papers'))}</span><span class="v14-badge">${h(result.evidence?.length||0)} chunks</span><span class="v14-badge">embedding ${h(Math.round((emb.coverage||0)*100))}%</span></div><div class="v14-output">${h(result.answer||'')}</div>${refs?`<h3 style="margin:12px 0 5px">${h(tr('Referencias utilizadas','References used'))}</h3><div class="v14-sources">${refs}</div>`:''}${contradictions?`<h3 style="margin:12px 0 5px">${h(tr('Contradicciones','Contradictions'))}</h3><div class="v14-sources">${contradictions}</div>`:''}${gaps?`<h3 style="margin:12px 0 5px">${h(tr('Brechas','Gaps'))}</h3><div class="v14-sources">${gaps}</div>`:''}`;
    } catch (e) {
      out.innerHTML = `<div class="v14-errors">${h(e.message)}</div>`; notify(e.message, true);
    } finally { busy = false; q('#v14-ask').disabled = false; }
  }

  async function showSemanticStatus() {
    const f = folderRequired(); if (!f) return;
    const out = q('#v14-corpus-result');
    try {
      const r = await api(`/api/corpus?op=status&folder_id=${encodeURIComponent(f.folder_id)}`);
      const e = r.embedding || {};
      out.innerHTML = `<div class="v14-metrics"><div class="v14-metric"><strong>${h(e.paper_count||0)}</strong><span>${h(tr('papers indexados','indexed papers'))}</span></div><div class="v14-metric"><strong>${h(e.embedded_chunks||0)}/${h(e.chunk_count||0)}</strong><span>${h(tr('chunks con embedding','embedded chunks'))}</span></div><div class="v14-metric"><strong>${h(Math.round((e.coverage||0)*100))}%</strong><span>${h(tr('cobertura semántica','semantic coverage'))}</span></div></div>`;
    } catch (e) { notify(e.message, true); }
  }

  async function createWatch() {
    const f = folderRequired(); if (!f) return;
    const query = q('#v14-watch-query').value.trim() || q('#research-query')?.value?.trim() || '';
    if (!query) return notify(tr('Escribe la consulta que deseas vigilar.','Enter the query you want to watch.'), true);
    try {
      await api('/api/corpus?op=create_watch', {method:'POST', body:JSON.stringify({folder_id:f.folder_id,query,from_year:Number(q('#v14-watch-year').value||1900),interval_hours:Number(q('#v14-watch-hours').value||24),max_results:30,include_web:true,enabled:true})});
      q('#v14-watch-query').value = '';
      await refreshWatches();
      notify(tr('Vigilancia creada.','Watch created.'));
    } catch (e) { notify(e.message, true); }
  }

  async function refreshWatches() {
    const f = activeFolder(); const list = q('#v14-watch-list');
    if (!list) return;
    if (!f?.folder_id) { list.innerHTML = `<div class="v14-note">${h(tr('Selecciona una carpeta.','Select a folder.'))}</div>`; return; }
    try {
      const r = await api(`/api/corpus?op=watches&folder_id=${encodeURIComponent(f.folder_id)}`);
      const watches = r.watches || [];
      if (!watches.length) { list.innerHTML = `<div class="v14-note">${h(tr('No hay vigilancias configuradas.','No watches configured.'))}</div>`; return; }
      list.innerHTML = watches.map(w => `<div class="v14-watch" data-watch="${h(w.watch_id)}"><div class="v14-watch-title">${h(w.query)}</div><div class="v14-watch-meta">${h(w.enabled?tr('Activa','Active'):tr('Pausada','Paused'))} · ${h(w.interval_hours)} h · ${h(tr('últimas novedades','latest new items'))}: ${h(w.last_new_count||0)}${w.last_error?` · ${h(tr('error','error'))}`:''}</div><div class="v14-watch-actions"><button class="ghost v14-run-watch" data-id="${h(w.watch_id)}">${h(tr('Buscar ahora','Run now'))}</button><button class="ghost v14-toggle-watch" data-id="${h(w.watch_id)}" data-enabled="${w.enabled?'1':'0'}">${h(w.enabled?tr('Pausar','Pause'):tr('Activar','Enable'))}</button></div><div class="v14-leads" id="v14-leads-${h(w.watch_id)}"></div></div>`).join('');
      list.querySelectorAll('.v14-run-watch').forEach(b => b.onclick = () => runWatch(b.dataset.id));
      list.querySelectorAll('.v14-toggle-watch').forEach(b => b.onclick = () => toggleWatch(b.dataset.id, b.dataset.enabled === '1'));
    } catch (e) { list.innerHTML = `<div class="v14-errors">${h(e.message)}</div>`; }
  }

  async function toggleWatch(id, enabled) {
    const f = folderRequired(); if (!f) return;
    try {
      await api('/api/corpus?op=update_watch', {method:'POST', body:JSON.stringify({folder_id:f.folder_id,watch_id:id,enabled:!enabled})});
      await refreshWatches();
    } catch (e) { notify(e.message, true); }
  }

  async function runWatch(id) {
    const f = folderRequired(); if (!f) return;
    const target = q(`#v14-leads-${CSS.escape(id)}`);
    if (target) target.innerHTML = `<div class="v14-note">${h(tr('Buscando novedades…','Searching for new items…'))}</div>`;
    try {
      const r = await api('/api/corpus?op=run_watch', {method:'POST', body:JSON.stringify({folder_id:f.folder_id,watch_id:id})});
      const rows = r.new_results || [];
      if (target) target.innerHTML = rows.length ? rows.map(x => {
        const u = safeUrl(x.public_url || x.pdf_url || x.url);
        return `<div class="v14-lead"><strong>${h(x.title||'')}</strong><br>${h((x.authors||[]).slice(0,4).join(', '))}${x.publication_date?` · ${h(x.publication_date)}`:''}${u?`<br><a href="${h(u)}" target="_blank" rel="noopener">${h(tr('Abrir fuente','Open source'))}</a>`:''}</div>`;
      }).join('') : `<div class="v14-note">${h(tr('No se detectaron nuevas fuentes respecto de la carpeta y ejecuciones anteriores.','No new sources were detected relative to the folder and previous runs.'))}</div>`;
      await refreshObservability();
    } catch (e) { if (target) target.innerHTML = `<div class="v14-errors">${h(e.message)}</div>`; notify(e.message, true); }
  }

  async function refreshObservability() {
    const f = folderRequired(); if (!f) return;
    const out = q('#v14-observability');
    if (!out) return;
    try {
      const r = await api(`/api/corpus?op=observability&folder_id=${encodeURIComponent(f.folder_id)}&days=7`);
      const c = r.corpus || {}, a = r.autonomy || {}, u = r.usage || {};
      const errors = (r.recent_errors || []).slice(0,4).map(x=>`${x.job_type||'job'}: ${x.error||''}`).join('\n');
      out.innerHTML = `<h3 style="margin:13px 0 6px">${h(tr('Observabilidad · 7 días','Observability · 7 days'))}</h3><div class="v14-metrics"><div class="v14-metric"><strong>${h(c.full_text_reviewed||0)}/${h(c.papers||0)}</strong><span>${h(tr('papers full-text','full-text papers'))}</span></div><div class="v14-metric"><strong>${h(Math.round((c.embedding_coverage||0)*100))}%</strong><span>embedding</span></div><div class="v14-metric"><strong>${h(a.retries_recorded||0)}</strong><span>${h(tr('reintentos','retries'))}</span></div><div class="v14-metric"><strong>${h((a.job_status||{}).failed||0)}</strong><span>${h(tr('jobs fallidos','failed jobs'))}</span></div><div class="v14-metric"><strong>${h(a.active_literature_watches||0)}</strong><span>watch</span></div><div class="v14-metric"><strong>${h(u.events||0)}</strong><span>${h(tr('eventos operativos','operational events'))}</span></div></div>${errors?`<div class="v14-errors">${h(errors)}</div>`:''}`;
    } catch (e) { out.innerHTML = `<div class="v14-errors">${h(e.message)}</div>`; }
  }

  function refreshForFolder() {
    const f = activeFolder();
    const id = f?.folder_id || null;
    if (id === lastFolderId) return;
    lastFolderId = id;
    corpusThread = null;
    if (q('#v14-corpus-result')) q('#v14-corpus-result').innerHTML = '';
    refreshWatches();
    if (id) refreshObservability();
  }

  function boot() {
    ensurePanel();
    refreshForFolder();
    document.addEventListener('click', e => {
      if (e.target?.closest?.('[data-view="literature"]')) setTimeout(() => { ensurePanel(); refreshForFolder(); }, 50);
    });
    setInterval(refreshForFolder, 1800);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
