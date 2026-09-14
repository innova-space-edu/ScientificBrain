(() => {
  if (window.__SB_V18_RESEARCH_FLOW__) return;
  window.__SB_V18_RESEARCH_FLOW__ = true;

  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const folder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad ? 'error' : 'log'](text);

  let researchSnapshot = null;
  let manuscriptSnapshot = null;
  let staleNoticeAt = 0;
  let analysisTimer = null;
  let analysisRunning = false;
  let baseSetView = null;
  let baseLoadLibrary = null;
  let baseSelectFolder = null;

  const sectionOrder = [
    ['abstract', 'Abstract'],
    ['state_of_art', tr('Estado del arte', 'State of the art')],
    ['research_question', tr('Pregunta de investigación', 'Research question')],
    ['objectives', tr('Objetivos', 'Objectives')],
    ['hypotheses', tr('Hipótesis y predicciones', 'Hypotheses and predictions')],
    ['development', tr('Desarrollo científico', 'Scientific development')],
    ['analysis', tr('Análisis de evidencia', 'Evidence analysis')],
    ['critical_analysis', tr('Análisis crítico', 'Critical analysis')],
    ['novelty', tr('Novedad y brecha', 'Novelty and gap')],
    ['future_work', tr('Trabajo futuro', 'Future work')],
    ['conclusion', tr('Conclusión', 'Conclusion')],
  ];

  function styles() {
    if (q('#v18-research-flow-style')) return;
    const style = document.createElement('style');
    style.id = 'v18-research-flow-style';
    style.textContent = `
      .v18-hidden{display:none!important}
      .v18-flow-banner{margin:0 0 14px;padding:16px 18px;border:1px solid #b2ccff;background:#f5f8ff;border-radius:14px}
      .v18-flow-banner h2{margin:0 0 4px}.v18-flow-banner p{margin:0;color:#475467;font-size:12px;line-height:1.55}
      .v18-flow-steps{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.v18-flow-steps span{padding:5px 9px;border-radius:999px;background:#fff;border:1px solid #d0d5dd;font-size:10px;color:#344054}
      .v18-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-top:12px}.v18-metric{padding:10px;border:1px solid #e4e7ec;border-radius:10px;background:#fff}.v18-metric strong{display:block;font-size:20px}.v18-metric span{font-size:10px;color:#667085}
      #v18-discovery{display:grid;gap:14px;margin-top:14px}#v18-discovery>.grid{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
      #v18-discovery #enqueue-reviews,#v18-discovery #process-next-review,#v18-discovery #process-review-queue,#v18-discovery #refresh-jobs{display:none!important}
      #v18-discovery #jobs-list{max-height:260px;overflow:auto}.v18-auto-note{padding:10px 12px;background:#ecfdf3;border:1px solid #abefc6;border-radius:10px;color:#067647;font-size:11px;line-height:1.45;margin-top:10px}
      .v18-state-grid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(280px,.6fr);gap:12px}.v18-state-text{white-space:pre-wrap;line-height:1.55;font-size:12px;max-height:420px;overflow:auto;background:#f8fafc;border:1px solid #e4e7ec;border-radius:10px;padding:12px}.v18-decision-grid{display:grid;gap:8px}.v18-decision{border:1px solid #e4e7ec;border-radius:10px;padding:10px}.v18-decision strong{font-size:11px}.v18-decision p{margin:5px 0 0;font-size:11px;color:#475467;white-space:pre-wrap;line-height:1.45}
      .v18-assistant{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:12px}.v18-assistant textarea{width:100%;min-height:115px}.v18-assistant-controls{display:grid;gap:8px;align-content:start}.v18-assistant-answer{white-space:pre-wrap;line-height:1.5;font-size:12px;padding:12px;border:1px solid #e4e7ec;background:#f9fafb;border-radius:10px;min-height:70px;margin-top:10px}.v18-checkbox{display:flex!important;align-items:flex-start;gap:8px;font-size:11px;color:#475467}.v18-checkbox input{width:auto;margin-top:2px}
      .v18-stale{padding:9px 11px;border-radius:10px;border:1px solid #fedf89;background:#fffaeb;color:#93370d;font-size:11px;margin-top:10px}.v18-cached{padding:7px 10px;border-radius:9px;background:#fffaeb;color:#93370d;font-size:10px;margin:8px 0}
      .v18-manuscript-toolbar{display:flex;gap:8px;flex-wrap:wrap}.v18-manuscript-grid{display:grid;gap:12px;margin-top:14px}.v18-manuscript-section{border:1px solid #e4e7ec;border-radius:12px;padding:14px;background:#fff}.v18-manuscript-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.v18-manuscript-section textarea{width:100%;min-height:210px;margin-top:10px;line-height:1.55;resize:vertical}.v18-section-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.v18-quality{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.v18-quality span{font-size:10px;padding:4px 8px;border:1px solid #e4e7ec;border-radius:999px}.v18-quality .ok{background:#ecfdf3;color:#067647;border-color:#abefc6}.v18-quality .warn{background:#fffaeb;color:#93370d;border-color:#fedf89}
      @media(max-width:980px){.v18-metrics{grid-template-columns:repeat(2,1fr)}.v18-state-grid,.v18-assistant{grid-template-columns:1fr}#v18-discovery>.grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function transientError(error) {
    return /(?:\b429\b|\b502\b|\b503\b|\b504\b|gateway|timeout|timed out|network error|failed to fetch|temporar)/i.test(String(error?.message || error || ''));
  }

  function cacheStorage(url) {
    return /research_workspace|versions|graph_|contradictions|hypotheses/i.test(url) ? sessionStorage : localStorage;
  }

  function cacheKey(url) {
    const owner = typeof state !== 'undefined' ? state.authUser?.id || 'anonymous' : 'anonymous';
    return `scibrain:v18:read:${owner}:${url}`;
  }

  function writeReadCache(url, value) {
    try {
      cacheStorage(url).setItem(cacheKey(url), JSON.stringify({at:Date.now(), value}));
    } catch (_) {}
  }

  function readReadCache(url) {
    try {
      const storage = cacheStorage(url);
      const raw = JSON.parse(storage.getItem(cacheKey(url)) || 'null');
      if (!raw?.value) return null;
      const maxAge = storage === sessionStorage ? 4 * 60 * 60 * 1000 : 12 * 60 * 60 * 1000;
      if (Date.now() - Number(raw.at || 0) > maxAge) return null;
      return raw.value;
    } catch (_) { return null; }
  }

  function cacheableRead(url, options={}) {
    const method = String(options.method || 'GET').toUpperCase();
    return method === 'GET' && /\/api\/(?:folders|library|projects|collaboration|science|jobs)/.test(url);
  }

  function installResilientApi() {
    if (window.__SB_V18_RESILIENT_API__ || typeof api !== 'function') return;
    window.__SB_V18_RESILIENT_API__ = true;
    const originalApi = api;
    api = async function(url, options={}, retry=true) {
      const safeRead = cacheableRead(url, options);
      const attempts = safeRead ? 3 : 1;
      let lastError = null;
      for (let attempt=0; attempt<attempts; attempt++) {
        try {
          const result = await originalApi(url, options, retry);
          if (safeRead) writeReadCache(url, result);
          return result;
        } catch (error) {
          lastError = error;
          if (!safeRead || !transientError(error) || attempt === attempts - 1) break;
          await sleep(attempt === 0 ? 280 : 760);
        }
      }
      if (safeRead && transientError(lastError)) {
        const cached = readReadCache(url);
        if (cached) {
          const now = Date.now();
          if (now - staleNoticeAt > 8000) {
            staleNoticeAt = now;
            notify(tr('Supabase demoró en responder. Se muestra el último estado válido mientras se reintenta.', 'Supabase is responding slowly. Showing the last valid state while retrying.'), false);
          }
          return {...cached, __stale_cache:true};
        }
      }
      throw lastError;
    };
  }

  function ensureCorpusHeader() {
    const view = q('#view-workspace');
    if (!view || q('#v18-corpus-banner')) return;
    const banner = document.createElement('div');
    banner.id = 'v18-corpus-banner';
    banner.className = 'v18-flow-banner';
    banner.innerHTML = `
      <h2>${esc(tr('Corpus científico', 'Scientific corpus'))}</h2>
      <p>${esc(tr('Sube tus PDFs o busca literatura. Cada paper legible entra automáticamente a extracción, análisis profundo e indexación; el estado del arte y la investigación se actualizan con la evidencia validada.', 'Upload PDFs or search the literature. Every readable paper automatically enters extraction, deep review and indexing; the state of the art and research update from validated evidence.'))}</p>
      <div class="v18-flow-steps"><span>1 · ${esc(tr('Agregar paper', 'Add paper'))}</span><span>2 · ${esc(tr('Extraer y analizar', 'Extract and analyze'))}</span><span>3 · ${esc(tr('Indexar evidencia', 'Index evidence'))}</span><span>4 · ${esc(tr('Actualizar investigación', 'Update research'))}</span></div>
      <div id="v18-corpus-metrics" class="v18-metrics"></div>`;
    view.prepend(banner);
  }

  function moveDiscoveryIntoCorpus() {
    const workspace = q('#view-workspace');
    const literature = q('#view-literature');
    if (!workspace || !literature || q('#v18-discovery')) return;
    const box = document.createElement('div');
    box.id = 'v18-discovery';
    while (literature.firstChild) box.appendChild(literature.firstChild);
    workspace.appendChild(box);
    const searchTitle = q('#v18-discovery #research-search')?.closest('.card')?.querySelector('h2');
    if (searchTitle) searchTitle.textContent = tr('Buscar literatura científica', 'Search scientific literature');
    const jobsTitle = q('#v18-discovery #jobs-list')?.closest('.card')?.querySelector('h2');
    if (jobsTitle) jobsTitle.textContent = tr('Análisis automático del corpus', 'Automatic corpus analysis');
    const jobsCard = q('#v18-discovery #jobs-list')?.closest('.card');
    if (jobsCard && !q('#v18-auto-note')) {
      const note = document.createElement('div');
      note.id = 'v18-auto-note'; note.className = 'v18-auto-note';
      note.textContent = tr('No necesitas administrar una cola: ScientificBrain analiza automáticamente cada PDF legible y conserva checkpoints si una ejecución se interrumpe.', 'You do not need to manage a queue: ScientificBrain automatically reviews each readable PDF and preserves checkpoints if execution is interrupted.');
      jobsCard.querySelector('.card-head')?.after(note);
    }
  }

  function corpusCounts() {
    const papers = Array.isArray(state?.library) ? state.library : [];
    const jobs = Array.isArray(state?.jobs) ? state.jobs.filter(x => x.job_type === 'review_paper') : [];
    const reviewed = papers.filter(p => p.review_depth === 'full_text_reviewed').length;
    const readable = papers.filter(p => p.system_can_read || p.storage_path || p.pdf_url).length;
    const pending = jobs.filter(j => ['pending','running'].includes(j.status)).length;
    const failed = jobs.filter(j => j.status === 'failed').length;
    return {total:papers.length, reviewed, readable, pending, failed};
  }

  function updateCorpusMetrics() {
    const box = q('#v18-corpus-metrics');
    if (!box) return;
    const c = corpusCounts();
    const remaining = Math.max(0, c.readable - c.reviewed);
    box.innerHTML = [
      [c.total, tr('papers en carpeta', 'papers in folder')],
      [c.readable, tr('texto completo legible', 'full text readable')],
      [c.reviewed, tr('análisis completados', 'reviews completed')],
      [Math.max(c.pending, remaining), tr('en análisis / pendientes', 'analyzing / pending')],
      [c.failed, tr('requieren reintento', 'need retry')],
    ].map(([n,label]) => `<div class="v18-metric"><strong>${esc(n)}</strong><span>${esc(label)}</span></div>`).join('');
  }

  async function fetchJobs() {
    const f = folder();
    if (!f) return [];
    if (window.SBAdaptive?.fetchJobs) return window.SBAdaptive.fetchJobs();
    const params = new URLSearchParams({folder_id:f.folder_id, limit:'500'});
    const result = await api('/api/jobs?' + params.toString());
    state.jobs = result.jobs || [];
    return state.jobs;
  }

  async function ensurePaperJob(paper) {
    const f = folder(); if (!f || !paper?.canonical_id) return null;
    await fetchJobs().catch(() => []);
    const old = (state.jobs || []).find(j => j.job_type === 'review_paper' && j.payload?.paper_id === paper.canonical_id && ['pending','running','completed'].includes(j.status));
    if (old) return old;
    const created = await api('/api/jobs', {method:'POST', body:JSON.stringify({
      folder_id:f.folder_id,
      session_id:state.session?.folder_id === f.folder_id ? state.session.session_id : null,
      job_type:'review_paper',
      payload:{paper_id:paper.canonical_id, pdf_url:paper.pdf_url || null},
    })});
    state.jobs = [created, ...(state.jobs || [])];
    return created;
  }

  async function resumeAutomaticAnalysis() {
    if (analysisRunning || !folder() || !accessToken?.()) return;
    await fetchJobs().catch(() => []);
    if ((state.jobs || []).some(j => j.job_type === 'review_paper' && j.status === 'running')) return;
    const candidates = (state.library || []).filter(p => p.review_depth !== 'full_text_reviewed' && (p.system_can_read || p.storage_path || p.pdf_url));
    if (!candidates.length) { updateCorpusMetrics(); return; }
    analysisRunning = true;
    try {
      for (const paper of candidates) {
        let job = await ensurePaperJob(paper);
        if (!job || job.status === 'completed') continue;
        try {
          if (window.SBAdaptive?.runJob) {
            await window.SBAdaptive.runJob(job.job_id, null, 500);
          } else {
            for (let step=0; step<400; step++) {
              job = await api('/api/run_job', {method:'POST', body:JSON.stringify({job_id:job.job_id})});
              if (job.status === 'completed') break;
              if (job.status === 'failed') throw new Error(job.last_error || 'paper review failed');
              await sleep(220);
            }
          }
        } catch (error) {
          console.warn('v0.18 automatic analysis', paper.canonical_id, error);
          break;
        }
        if (baseLoadLibrary) await baseLoadLibrary().catch(() => {});
        updateCorpusMetrics();
      }
      await loadResearchSnapshot({allowAutorefresh:true}).catch(() => {});
    } finally {
      analysisRunning = false;
      updateCorpusMetrics();
    }
  }

  function scheduleAutomaticAnalysis() {
    clearTimeout(analysisTimer);
    analysisTimer = setTimeout(() => resumeAutomaticAnalysis().catch(error => console.warn('v0.18 auto-analysis', error)), 2600);
  }

  function ensureResearchHub() {
    const view = q('#view-collab');
    if (!view || q('#v18-state-card')) return;
    const intro = view.querySelector('.v11-intro') || view.firstElementChild;
    const stateCard = document.createElement('article');
    stateCard.id = 'v18-state-card'; stateCard.className = 'v11-card v11-full';
    stateCard.innerHTML = `
      <div class="v11-section-head"><div><h2>${esc(tr('Estado del arte vivo', 'Living state of the art'))}</h2><p class="muted">${esc(tr('Síntesis basada en papers ya incorporados. La evidencia full-text tiene prioridad; resultados de búsqueda externos siguen siendo candidatos hasta ser agregados y revisados.', 'Synthesis based on papers already in the corpus. Full-text evidence has priority; external search results remain candidates until added and reviewed.'))}</p></div><button id="v18-refresh-research" class="ghost">${esc(tr('Actualizar', 'Refresh'))}</button></div>
      <div id="v18-research-status" class="v18-quality"></div>
      <div id="v18-stale-banner"></div>
      <div class="v18-state-grid" style="margin-top:10px"><div id="v18-state-art" class="v18-state-text"></div><div id="v18-decisions" class="v18-decision-grid"></div></div>`;
    intro?.after(stateCard);

    const assistant = document.createElement('article');
    assistant.id = 'v18-assistant-card'; assistant.className = 'v11-card v11-full';
    assistant.innerHTML = `
      <div><h2>${esc(tr('Mesa de discusión científica', 'Scientific discussion desk'))}</h2><p class="muted">${esc(tr('Pregunta, cuestiona una hipótesis, pide evidencia o solicita otra explicación. Puedes autorizar una búsqueda bibliográfica antes de que el agente responda.', 'Ask, challenge a hypothesis, request evidence or ask for an alternative explanation. You can authorize a literature search before the agent responds.'))}</p></div>
      <div class="v18-assistant" style="margin-top:10px"><div><textarea id="v18-discuss-input" placeholder="${esc(tr('Ej.: ¿La evidencia disponible permite afirmar que la geometría controla el impulse bit? ¿Qué mecanismo alternativo debemos descartar?', 'e.g. Does the available evidence support that geometry controls impulse bit? Which alternative mechanism should we rule out?'))}"></textarea><div id="v18-discuss-answer" class="v18-assistant-answer">${esc(tr('La respuesta aparecerá aquí y quedará guardada en la investigación.', 'The answer will appear here and will be saved in the research.'))}</div></div><div class="v18-assistant-controls"><label>${esc(tr('Agente', 'Agent'))}<select id="v18-discuss-agent"><option value="critical_reviewer">${esc(tr('Revisor crítico', 'Critical reviewer'))}</option><option value="literature_reviewer">${esc(tr('Revisor de literatura', 'Literature reviewer'))}</option><option value="methods_reviewer">${esc(tr('Revisor metodológico', 'Methods reviewer'))}</option><option value="theory_reviewer">${esc(tr('Revisor teórico', 'Theory reviewer'))}</option><option value="evidence_reviewer">${esc(tr('Revisor de evidencia', 'Evidence reviewer'))}</option></select></label><label class="v18-checkbox"><input id="v18-discuss-web" type="checkbox" checked><span>${esc(tr('Buscar literatura reciente antes de responder. Los resultados no se convierten en evidencia hasta agregarlos al corpus.', 'Search recent literature before answering. Results do not become evidence until added to the corpus.'))}</span></label><button id="v18-discuss-send" class="primary">${esc(tr('Discutir con ScientificBrain', 'Discuss with ScientificBrain'))}</button><button id="v18-show-candidates" class="ghost v18-hidden">${esc(tr('Ver candidatos encontrados', 'View discovered candidates'))}</button></div></div>`;
    stateCard.after(assistant);
    q('#v18-refresh-research').onclick = () => loadResearchSnapshot({allowAutorefresh:true});
    q('#v18-discuss-send').onclick = discussResearch;
    q('#v18-show-candidates').onclick = () => { setView('workspace'); setTimeout(() => q('#v18-discovery')?.scrollIntoView({behavior:'smooth', block:'start'}), 80); };
  }

  function sectionText(document, key) {
    const value = document?.sections?.[key];
    return typeof value === 'string' ? value : String(value?.text || '');
  }

  function renderResearchSnapshot(snapshot) {
    researchSnapshot = snapshot || researchSnapshot;
    const doc = researchSnapshot?.document || {};
    const corpus = researchSnapshot?.corpus || {};
    const stateArt = q('#v18-state-art');
    if (stateArt) stateArt.textContent = sectionText(doc, 'state_of_art') || tr('Todavía no hay un estado del arte sintetizado. Agrega o analiza papers y define el tema de investigación.', 'There is no synthesized state of the art yet. Add or review papers and define the research topic.');
    const status = q('#v18-research-status');
    if (status) status.innerHTML = `<span>${esc(corpus.total || 0)} papers</span><span class="${(corpus.full_text_reviewed||0)>0?'ok':'warn'}">${esc(corpus.full_text_reviewed || 0)} ${esc(tr('full-text revisados', 'full-text reviewed'))}</span><span>${esc(corpus.readable_now || 0)} ${esc(tr('legibles', 'readable'))}</span><span>${esc(doc.status || tr('sin borrador', 'no draft'))}</span>`;
    const decisions = q('#v18-decisions');
    if (decisions) {
      const rows = [
        ['research_question', tr('Pregunta', 'Question')],
        ['hypotheses', tr('Hipótesis', 'Hypotheses')],
        ['objectives', tr('Objetivos', 'Objectives')],
        ['novelty', tr('Novedad / brecha', 'Novelty / gap')],
      ];
      decisions.innerHTML = rows.map(([key,label]) => `<div class="v18-decision"><strong>${esc(label)}</strong><p>${esc(sectionText(doc,key) || '—')}</p></div>`).join('');
    }
    const stale = q('#v18-stale-banner');
    if (stale) {
      const isStale = ['stale_evidence','stale_external_literature'].includes(String(doc.status || ''));
      stale.innerHTML = isStale ? `<div class="v18-stale">${esc(doc.status === 'stale_evidence' ? tr('Hay evidencia full-text nueva. ScientificBrain actualizará las secciones generadas por IA conservando tus ediciones.', 'There is new full-text evidence. ScientificBrain will update AI-generated sections while preserving your edits.') : tr('Hay literatura externa nueva que puede afectar la novedad. Debe validarse antes de usarla como evidencia.', 'There is new external literature that may affect novelty. It must be validated before being used as evidence.'))}</div>` : '';
    }
    renderManuscript(researchSnapshot);
  }

  async function maybeRefreshStale(snapshot) {
    const doc = snapshot?.document || {};
    if (doc.status !== 'stale_evidence' || !doc.topic) return;
    const key = `scibrain:v18:autorefresh:${folder()?.folder_id || ''}:${doc.document_id || ''}:${doc.revision || 0}`;
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, '1');
    try {
      await api('/api/collaboration?op=generate_draft', {method:'POST', body:JSON.stringify({folder_id:folder().folder_id, topic:doc.topic, language:lang(), preserve_user_edits:true})});
      const fresh = await api('/api/collaboration?op=research_workspace&folder_id=' + encodeURIComponent(folder().folder_id));
      renderResearchSnapshot(fresh);
    } catch (error) {
      console.warn('v0.18 stale evidence refresh', error);
    }
  }

  async function loadResearchSnapshot({allowAutorefresh=false}={}) {
    const f = folder();
    if (!f) { researchSnapshot = null; renderResearchSnapshot(null); return null; }
    const result = await api('/api/collaboration?op=research_workspace&folder_id=' + encodeURIComponent(f.folder_id));
    renderResearchSnapshot(result);
    if (allowAutorefresh) maybeRefreshStale(result).catch(() => {});
    return result;
  }

  function answerText(result) {
    if (!result) return '';
    for (const value of [result.reply, result.answer, result.response, result.content, result.message?.content, result.assistant_message?.content, result.assistant?.content]) {
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
    return JSON.stringify(result, null, 2);
  }

  async function discussResearch() {
    const f = folder(); const input = q('#v18-discuss-input'); const button = q('#v18-discuss-send');
    const message = input?.value?.trim();
    if (!f || !message) return;
    const includeWeb = !!q('#v18-discuss-web')?.checked;
    const out = q('#v18-discuss-answer');
    button.disabled = true; button.textContent = tr('Analizando…', 'Analyzing…');
    try {
      let searchCount = 0;
      if (includeWeb) {
        const topic = researchSnapshot?.document?.topic || q('#v11-topic')?.value?.trim() || '';
        const search = await api('/api/research_search', {method:'POST', body:JSON.stringify({folder_id:f.folder_id, project_id:state.session?.project_id || null, query:[topic,message].filter(Boolean).join(' · '), from_year:1990, max_results:16, include_web:true, resolve_open_access:true})});
        state.researchResults = search.results || [];
        searchCount = state.researchResults.length;
        if (typeof renderResearchResults === 'function') renderResearchResults();
      }
      const result = await api('/api/collaboration?op=discuss', {method:'POST', body:JSON.stringify({folder_id:f.folder_id, message, agent_id:q('#v18-discuss-agent')?.value || 'critical_reviewer', section_key:null, language:lang()})});
      out.textContent = answerText(result);
      input.value = '';
      const candidates = q('#v18-show-candidates');
      if (candidates) {
        candidates.classList.toggle('v18-hidden', !searchCount);
        if (searchCount) candidates.textContent = `${tr('Ver candidatos encontrados', 'View discovered candidates')} (${searchCount})`;
      }
      await loadResearchSnapshot({allowAutorefresh:false}).catch(() => {});
    } catch (error) {
      out.textContent = error.message || String(error);
      notify(error.message || String(error), true);
    } finally {
      button.disabled = false; button.textContent = tr('Discutir con ScientificBrain', 'Discuss with ScientificBrain');
    }
  }

  function ensureManuscriptView() {
    if (q('#view-manuscript')) return;
    const view = document.createElement('section');
    view.id = 'view-manuscript'; view.className = 'view';
    view.innerHTML = `
      <div class="v18-flow-banner"><h2>${esc(tr('Manuscrito científico', 'Scientific manuscript'))}</h2><p>${esc(tr('Convierte la investigación en un documento publicable sin perder la trazabilidad. Las ediciones humanas se conservan; las secciones generadas por IA pueden actualizarse con nueva evidencia.', 'Turn the research into a publishable document without losing traceability. Human edits are preserved; AI-generated sections can update with new evidence.'))}</p><div id="v18-manuscript-quality" class="v18-quality"></div></div>
      <article class="card"><div class="card-head"><div><h2>${esc(tr('Control científico antes de exportar', 'Scientific control before export'))}</h2><p class="muted">${esc(tr('Verifica citas, soporte factual y riesgo de sobreafirmación antes de considerar una versión lista.', 'Verify citations, factual support and overclaim risk before considering a version ready.'))}</p></div><div class="v18-manuscript-toolbar"><button id="v18-manuscript-refresh" class="ghost">${esc(tr('Actualizar', 'Refresh'))}</button><button id="v18-manuscript-verify" class="secondary">${esc(tr('Auditar evidencia', 'Audit evidence'))}</button><button id="v18-manuscript-benchmark" class="secondary">${esc(tr('Benchmark científico', 'Scientific benchmark'))}</button><button id="v18-manuscript-repair" class="ghost">${esc(tr('Reparar solo secciones IA', 'Repair AI sections only'))}</button></div></div><div id="v18-manuscript-result" class="muted"></div></article>
      <div id="v18-manuscript-grid" class="v18-manuscript-grid"></div>`;
    const anchor = q('#view-map') || q('#view-protocol');
    anchor?.parentNode?.insertBefore(view, anchor);
    q('#v18-manuscript-refresh').onclick = () => loadManuscript();
    q('#v18-manuscript-verify').onclick = () => runQuality('verify_document');
    q('#v18-manuscript-benchmark').onclick = () => runQuality('benchmark_document');
    q('#v18-manuscript-repair').onclick = () => runQuality('repair_failed_sections');
  }

  function renderManuscript(snapshot) {
    manuscriptSnapshot = snapshot || manuscriptSnapshot || researchSnapshot;
    const doc = manuscriptSnapshot?.document || {};
    const grid = q('#v18-manuscript-grid');
    if (grid) {
      grid.innerHTML = sectionOrder.map(([key,label]) => {
        const section = doc.sections?.[key] || {};
        const text = typeof section === 'string' ? section : section.text || '';
        const refs = typeof section === 'object' ? section.refs || [] : [];
        const human = typeof section === 'object' && !!section.user_edited;
        return `<article class="v18-manuscript-section"><div class="v18-manuscript-head"><h3>${esc(label)}</h3><span class="pill">${esc(human ? tr('edición humana', 'human edit') : tr('borrador IA', 'AI draft'))}</span></div><textarea data-v18-section="${esc(key)}">${esc(text)}</textarea><div class="draft-refs">${esc(tr('Fuentes', 'Sources'))}: ${esc(refs.join(', ') || '—')}</div><div class="v18-section-actions"><button class="secondary v18-save-section" data-key="${esc(key)}">${esc(tr('Guardar sección', 'Save section'))}</button><button class="ghost v18-review-section" data-key="${esc(key)}">${esc(tr('Revisión crítica', 'Critical review'))}</button></div></article>`;
      }).join('');
      qa('.v18-save-section').forEach(button => button.onclick = () => saveManuscriptSection(button.dataset.key, button));
      qa('.v18-review-section').forEach(button => button.onclick = () => reviewManuscriptSection(button.dataset.key, button));
    }
    const quality = q('#v18-manuscript-quality');
    if (quality) {
      const audit = doc.evidence_manifest?.evidence_audit || {};
      const benchmark = doc.evidence_manifest?.quality_benchmark || doc.quality_benchmark || {};
      quality.innerHTML = `<span>${esc(doc.status || tr('sin documento', 'no document'))}</span><span class="${audit.passed?'ok':'warn'}">${esc(tr('evidencia', 'evidence'))}: ${audit.passed ? 'PASS' : '—'}</span><span class="${benchmark.passed?'ok':'warn'}">benchmark: ${benchmark.passed ? 'PASS' : '—'}</span><span>r${esc(doc.revision || 0)}</span>`;
    }
  }

  async function loadManuscript() {
    const result = await loadResearchSnapshot({allowAutorefresh:true});
    renderManuscript(result);
    return result;
  }

  async function saveManuscriptSection(key, button) {
    const f = folder(); const textarea = q(`textarea[data-v18-section="${key}"]`);
    if (!f || !textarea) return;
    button.disabled = true;
    try {
      await api('/api/collaboration?op=save_section', {method:'POST', body:JSON.stringify({folder_id:f.folder_id, section_key:key, content:textarea.value})});
      await loadManuscript();
      notify(tr('Sección guardada.', 'Section saved.'));
    } catch (error) { notify(error.message || String(error), true); }
    finally { button.disabled = false; }
  }

  async function reviewManuscriptSection(key, button) {
    const f = folder(); if (!f) return;
    button.disabled = true;
    try {
      const result = await api('/api/collaboration?op=review_section', {method:'POST', body:JSON.stringify({folder_id:f.folder_id, section_key:key, agent_id:'critical_reviewer', language:lang()})});
      q('#v18-manuscript-result').textContent = answerText(result);
      await loadResearchSnapshot({allowAutorefresh:false}).catch(() => {});
    } catch (error) { q('#v18-manuscript-result').textContent = error.message || String(error); }
    finally { button.disabled = false; }
  }

  async function runQuality(operation) {
    const f = folder(); const out = q('#v18-manuscript-result');
    if (!f) return;
    const button = q(operation === 'verify_document' ? '#v18-manuscript-verify' : operation === 'benchmark_document' ? '#v18-manuscript-benchmark' : '#v18-manuscript-repair');
    if (button) button.disabled = true;
    out.textContent = tr('Ejecutando control científico…', 'Running scientific control…');
    try {
      const result = await api(`/api/collaboration?op=${operation}`, {method:'POST', body:JSON.stringify({folder_id:f.folder_id, language:lang(), use_model:true, max_sections:4})});
      out.textContent = operation === 'repair_failed_sections' ? tr('Reparación limitada a secciones generadas por IA completada. Se conservaron las ediciones humanas.', 'Repair limited to AI-generated sections completed. Human edits were preserved.') : answerText(result);
      await loadManuscript();
    } catch (error) { out.textContent = error.message || String(error); notify(error.message || String(error), true); }
    finally { if (button) button.disabled = false; }
  }

  function ensureNavigation() {
    const nav = q('.sidebar nav'); if (!nav) return;
    const corpus = q('[data-view="workspace"]');
    const research = q('[data-view="collab"]');
    const map = q('[data-view="map"]');
    if (corpus) { corpus.removeAttribute('data-i18n'); corpus.textContent = tr('Corpus', 'Corpus'); corpus.classList.remove('advanced-nav-hidden'); }
    if (research) { research.removeAttribute('data-i18n'); research.textContent = tr('Investigación', 'Research'); research.classList.remove('advanced-nav-hidden'); }
    if (map) { map.removeAttribute('data-i18n'); map.textContent = tr('Mapa científico', 'Scientific map'); map.classList.remove('advanced-nav-hidden'); }
    let manuscript = q('[data-view="manuscript"]');
    if (!manuscript) {
      manuscript = document.createElement('button'); manuscript.className = 'nav'; manuscript.dataset.view = 'manuscript'; manuscript.textContent = tr('Manuscrito', 'Manuscript');
      if (research?.nextSibling) nav.insertBefore(manuscript, research.nextSibling); else nav.appendChild(manuscript);
    }
    qa('.sidebar nav .nav').forEach(button => {
      if (!['workspace','collab','manuscript','map'].includes(button.dataset.view)) button.classList.add('v18-hidden');
    });
    manuscript.onclick = () => setView('manuscript');
  }

  function installViewRouter() {
    if (window.__SB_V18_VIEW_ROUTER__ || typeof setView !== 'function') return;
    window.__SB_V18_VIEW_ROUTER__ = true;
    baseSetView = setView;
    setView = function(name) {
      const requested = name;
      const redirects = {overview:'workspace', literature:'workspace', definition:'collab', session:'collab', protocol:'collab', projects:'collab'};
      const target = redirects[name] || name;
      baseSetView(target);
      const title = q('#page-title');
      if (title) title.textContent = ({workspace:tr('Corpus científico','Scientific corpus'), collab:tr('Investigación','Research'), manuscript:tr('Manuscrito','Manuscript'), map:tr('Mapa científico','Scientific map')})[target] || title.textContent;
      ensureNavigation();
      if (target === 'collab') loadResearchSnapshot({allowAutorefresh:true}).catch(() => {});
      if (target === 'manuscript') loadManuscript().catch(() => {});
      if (target === 'workspace') { updateCorpusMetrics(); scheduleAutomaticAnalysis(); }
      if (requested === 'literature') setTimeout(() => q('#v18-discovery')?.scrollIntoView({behavior:'smooth',block:'start'}), 80);
    };
  }

  function installDataHooks() {
    if (typeof loadLibrary === 'function' && !window.__SB_V18_LIBRARY_HOOK__) {
      window.__SB_V18_LIBRARY_HOOK__ = true;
      baseLoadLibrary = loadLibrary;
      loadLibrary = async function(...args) {
        const result = await baseLoadLibrary.apply(this, args);
        updateCorpusMetrics();
        scheduleAutomaticAnalysis();
        return result;
      };
    }
    if (typeof selectFolder === 'function' && !window.__SB_V18_FOLDER_HOOK__) {
      window.__SB_V18_FOLDER_HOOK__ = true;
      baseSelectFolder = selectFolder;
      selectFolder = async function(...args) {
        const result = await baseSelectFolder.apply(this, args);
        researchSnapshot = null; manuscriptSnapshot = null;
        updateCorpusMetrics();
        await loadResearchSnapshot({allowAutorefresh:true}).catch(() => {});
        scheduleAutomaticAnalysis();
        return result;
      };
    }
  }

  function install() {
    styles();
    installResilientApi();
    ensureCorpusHeader();
    moveDiscoveryIntoCorpus();
    ensureResearchHub();
    ensureManuscriptView();
    ensureNavigation();
    installViewRouter();
    installDataHooks();
    updateCorpusMetrics();
    loadResearchSnapshot({allowAutorefresh:true}).catch(() => {});
    scheduleAutomaticAnalysis();
    if (q('#view-overview.active') || !q('.view.active')) setView('workspace');
  }

  document.addEventListener('scibrain:languagechange', () => {
    ensureNavigation();
    renderResearchSnapshot(researchSnapshot);
    renderManuscript(manuscriptSnapshot);
  });

  if (document.readyState === 'loading') window.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
