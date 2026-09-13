(() => {
  const lang = () => window.SBI18N?.language?.() || 'es';
  const msg = (es, en, pt=es, fr=es) => ({es,en,pt,fr}[lang()] || es);
  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const html = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  let graphSummary = null;
  let graphNodes = [];
  let contradictions = [];
  let competitions = [];
  let autoRunningJob = false;

  const base = {
    uploadPapers: typeof uploadPapers === 'function' ? uploadPapers : null,
    renderLibrary: typeof renderLibrary === 'function' ? renderLibrary : null,
    refreshJobs: typeof refreshJobs === 'function' ? refreshJobs : null,
    renderJobs: typeof renderJobs === 'function' ? renderJobs : null,
    loadLibrary: typeof loadLibrary === 'function' ? loadLibrary : null,
    setView: typeof setView === 'function' ? setView : null,
  };

  function injectStyles() {
    if (q('#scibrain-v08-style')) return;
    const style = document.createElement('style');
    style.id = 'scibrain-v08-style';
    style.textContent = `
      .guided-flow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:16px 0}.guided-step{border:1px solid #e4e7ec;border-radius:12px;padding:12px;background:#fff;min-height:108px}.guided-step.done{border-color:#abefc6;background:#f6fef9}.guided-step.active{border-color:#8098f9;background:#f5f8ff}.guided-step .n{width:26px;height:26px;border-radius:99px;display:grid;place-items:center;background:#eef2ff;color:#3538cd;font-weight:700;font-size:12px}.guided-step.done .n{background:#dcfae6;color:#067647}.guided-step h3{font-size:13px;margin:8px 0 4px}.guided-step p{font-size:11px;color:#667085;margin:0 0 8px;line-height:1.35}.analysis-banner{margin:12px 0;padding:12px 14px;border-radius:10px;border:1px solid #b2ccff;background:#eff8ff;color:#1849a9;font-size:12px}.paper-analysis-state{display:inline-flex;margin-top:6px;padding:3px 7px;border-radius:999px;font-size:10px;background:#f2f4f7;color:#475467}.paper-analysis-state.running{background:#fff4e5;color:#b54708}.paper-analysis-state.done{background:#ecfdf3;color:#067647}.paper-analysis-state.failed{background:#fef3f2;color:#b42318}.map-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}.map-metric{padding:12px;border:1px solid #e4e7ec;border-radius:10px}.map-metric strong{display:block;font-size:24px}.map-metric span{font-size:11px;color:#667085}.map-list{display:grid;gap:10px}.map-card{border:1px solid #e4e7ec;border-radius:11px;padding:13px}.map-card h3{font-size:13px;margin:0 0 6px}.map-card p{font-size:12px;color:#475467;line-height:1.45;margin:5px 0}.map-card code{font-size:10px;white-space:normal}.map-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:end}.map-toolbar label{margin:0;min-width:260px;flex:1}.node-filter{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.node-filter button.active{background:#eef2ff;border-color:#8098f9;color:#3538cd}@media(max-width:1100px){.guided-flow,.map-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.guided-flow,.map-metrics{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function setupMapView() {
    const nav = q('.sidebar nav');
    if (nav && !q('[data-view="map"]')) {
      const b = document.createElement('button');
      b.className = 'nav'; b.dataset.view = 'map';
      b.textContent = msg('Mapa científico','Scientific map','Mapa científico','Carte scientifique');
      const protocol = q('[data-view="protocol"]');
      nav.insertBefore(b, protocol || null);
      b.onclick = () => setView('map');
    }
    if (!q('#view-map')) {
      const section = document.createElement('section');
      section.id = 'view-map'; section.className = 'view';
      section.innerHTML = `
        <div id="map-folder-context" class="folder-context">${html(msg('Selecciona una carpeta con papers analizados.','Select a folder with reviewed papers.','Selecione uma pasta com papers analisados.','Sélectionnez un dossier avec des articles analysés.'))}</div>
        <article class="card">
          <div class="card-head"><div><h2>${html(msg('Mapa científico','Scientific map','Mapa científico','Carte scientifique'))}</h2><p class="muted">${html(msg('Convierte los papers revisados en claims, evidencia, modelos, supuestos, ecuaciones y relaciones trazables.','Transforms reviewed papers into traceable claims, evidence, models, assumptions, equations and relations.','Converte papers revisados em claims, evidências, modelos, suposições, equações e relações rastreáveis.','Transforme les articles examinés en affirmations, preuves, modèles, hypothèses, équations et relations traçables.'))}</p></div></div>
          <div class="map-toolbar">
            <button id="map-build" class="primary">${html(msg('Construir / actualizar mapa','Build / refresh map','Construir / atualizar mapa','Construire / actualiser'))}</button>
            <button id="map-contradictions" class="secondary">${html(msg('Analizar contradicciones','Analyze contradictions','Analisar contradições','Analyser les contradictions'))}</button>
            <label>${html(msg('Pregunta para hipótesis','Question for hypotheses','Pergunta para hipóteses','Question pour hypothèses'))}<input id="map-question" placeholder="${html(msg('¿Qué mecanismo explica los resultados?','What mechanism explains the results?','Qual mecanismo explica os resultados?','Quel mécanisme explique les résultats ?'))}" /></label>
            <button id="map-hypotheses" class="secondary">${html(msg('Generar hipótesis competidoras','Generate competing hypotheses','Gerar hipóteses concorrentes','Générer des hypothèses concurrentes'))}</button>
            <button id="map-refresh" class="ghost">${html(msg('Actualizar','Refresh','Atualizar','Actualiser'))}</button>
          </div>
        </article>
        <div id="map-metrics" class="map-metrics" style="margin:14px 0"></div>
        <div class="grid two">
          <article class="card"><div class="card-head"><h2>${html(msg('Claims y evidencia','Claims and evidence','Claims e evidências','Affirmations et preuves'))}</h2></div><div id="map-node-filters" class="node-filter"></div><div id="map-nodes" class="map-list empty">—</div></article>
          <article class="card"><div class="card-head"><h2>${html(msg('Contradicciones','Contradictions','Contradições','Contradictions'))}</h2><span id="map-contradiction-count" class="pill">0</span></div><div id="map-contradiction-list" class="map-list empty">—</div></article>
        </div>
        <article class="card"><div class="card-head"><h2>${html(msg('Hipótesis competidoras','Competing hypotheses','Hipóteses concorrentes','Hypothèses concurrentes'))}</h2></div><div id="map-hypothesis-list" class="map-list empty">—</div></article>`;
      const protocolView = q('#view-protocol');
      protocolView?.parentNode?.insertBefore(section, protocolView);
      q('#map-build').onclick = buildGraph;
      q('#map-contradictions').onclick = detectContradictions;
      q('#map-hypotheses').onclick = generateHypotheses;
      q('#map-refresh').onclick = loadScientificMap;
    }
  }

  function setupGuidedFlow() {
    const overview = q('#view-overview');
    if (!overview || q('#guided-flow-card')) return;
    const card = document.createElement('article');
    card.id = 'guided-flow-card'; card.className = 'card';
    card.innerHTML = `<div class="card-head"><div><h2>${html(msg('Flujo de trabajo','Workflow','Fluxo de trabalho','Flux de travail'))}</h2><p class="muted">${html(msg('ScientificBrain no debería dejarte adivinar qué hacer. Sigue estos pasos.','ScientificBrain should not make you guess what to do. Follow these steps.','ScientificBrain não deve deixar você adivinhar o que fazer. Siga estes passos.','ScientificBrain ne doit pas vous laisser deviner quoi faire. Suivez ces étapes.'))}</p></div></div><div id="guided-flow" class="guided-flow"></div><div id="guided-action"></div>`;
    const context = q('#overview-folder-context');
    context?.after(card);
    renderGuidedFlow();
  }

  function jobForPaper(paper) {
    return (state.jobs || []).find(j => j.job_type === 'review_paper' && j.payload?.paper_id === paper.canonical_id);
  }

  function renderGuidedFlow() {
    const box = q('#guided-flow'); if (!box) return;
    const folder = typeof selectedFolder === 'function' ? selectedFolder() : null;
    const papers = state.library || [];
    const reviewed = papers.filter(p => p.review_depth === 'full_text_reviewed').length;
    const mapBuilt = (graphSummary?.nodes || 0) > 0;
    const project = !!state.session;
    const steps = [
      {done:!!folder,title:msg('1. Carpeta','1. Folder','1. Pasta','1. Dossier'),text:folder?folder.name:msg('Crea o selecciona una carpeta.','Create or select a folder.','Crie ou selecione uma pasta.','Créez ou sélectionnez un dossier.'),go:'workspace'},
      {done:papers.length>0,title:msg('2. Papers','2. Papers','2. Papers','2. Articles'),text:papers.length?`${papers.length} ${msg('en la carpeta','in folder','na pasta','dans le dossier')}`:msg('Sube PDF o busca papers.','Upload PDFs or search papers.','Envie PDFs ou pesquise papers.','Téléversez des PDF ou recherchez des articles.'),go:'workspace'},
      {done:reviewed>0,title:msg('3. Analizar','3. Analyze','3. Analisar','3. Analyser'),text:`${reviewed}/${papers.length} ${msg('revisados a texto completo','full-text reviewed','revisados em texto completo','analysés en texte intégral')}`,go:'literature'},
      {done:mapBuilt,title:msg('4. Mapa científico','4. Scientific map','4. Mapa científico','4. Carte scientifique'),text:mapBuilt?`${graphSummary.claims || graphSummary.node_types?.claim || 0} claims · ${graphSummary.evidence || graphSummary.node_types?.evidence || 0} evidence`:msg('Construye relaciones y contradicciones.','Build relations and contradictions.','Construa relações e contradições.','Construisez relations et contradictions.'),go:'map'},
      {done:project,title:msg('5. Proyecto y agentes','5. Project & agents','5. Projeto e agentes','5. Projet et agents'),text:project?msg('Sesión científica activa.','Scientific session active.','Sessão científica ativa.','Session scientifique active.'):msg('Define la pregunta y crea el proyecto.','Define the question and create the project.','Defina a pergunta e crie o projeto.','Définissez la question et créez le projet.'),go:'definition'},
    ];
    const firstPending = steps.findIndex(s => !s.done);
    box.innerHTML = steps.map((s,i)=>`<div class="guided-step ${s.done?'done':i===firstPending?'active':''}"><span class="n">${s.done?'✓':i+1}</span><h3>${html(s.title)}</h3><p>${html(s.text)}</p><button class="ghost guided-go" data-view="${s.go}">${html(s.done?msg('Ver','View','Ver','Voir'):msg('Continuar','Continue','Continuar','Continuer'))}</button></div>`).join('');
    qa('.guided-go').forEach(b => b.onclick = () => setView(b.dataset.view));
    const action = q('#guided-action');
    if (action) action.innerHTML = papers.length && !reviewed ? `<div class="analysis-banner">${html(msg('Tus PDF ya están guardados. El siguiente paso es analizarlos. Los papers nuevos se agregan automáticamente a la cola de análisis.','Your PDFs are stored. The next step is analysis. New papers are automatically added to the review queue.','Seus PDFs estão armazenados. O próximo passo é analisá-los. Novos papers entram automaticamente na fila.','Vos PDF sont stockés. L’étape suivante est l’analyse. Les nouveaux articles sont automatiquement ajoutés à la file.'))}</div>` : '';
  }

  async function queuePaperReview(paper, autoStart=false) {
    const folder = typeof selectedFolder === 'function' ? selectedFolder() : null;
    if (!folder || !paper?.canonical_id || paper.review_depth === 'full_text_reviewed') return null;
    const existing = jobForPaper(paper);
    if (existing && ['pending','running','completed'].includes(existing.status)) return existing;
    const job = await api('/api/jobs', {method:'POST', body:JSON.stringify({
      folder_id:folder.folder_id,
      session_id:state.session?.folder_id === folder.folder_id ? state.session.session_id : null,
      job_type:'review_paper', payload:{paper_id:paper.canonical_id}
    })});
    state.jobs = [job, ...(state.jobs || [])];
    renderPaperAnalysisButtons(); renderGuidedFlow();
    if (autoStart && !autoRunningJob) runFolderJob(job.job_id).catch(()=>{});
    return job;
  }

  async function runFolderJob(jobId) {
    autoRunningJob = true;
    try {
      const result = await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:jobId})});
      await refreshJobs();
      await loadLibrary();
      await loadScientificMap().catch(()=>{});
      toast(msg('Análisis científico completado.','Scientific review completed.','Análise científica concluída.','Analyse scientifique terminée.'));
      return result;
    } catch(e) {
      await refreshJobs().catch(()=>{});
      toast(msg('El análisis falló: ','Review failed: ','A análise falhou: ','L’analyse a échoué : ')+e.message,true);
      throw e;
    } finally { autoRunningJob = false; renderPaperAnalysisButtons(); renderGuidedFlow(); }
  }

  function renderPaperAnalysisButtons() {
    qa('#paper-list .paper-row').forEach(row => {
      const itemId = row.querySelector('.delete-paper')?.dataset.item;
      const paper = (state.library || []).find(p => p.item_id === itemId);
      if (!paper) return;
      let status = row.querySelector('.paper-analysis-state');
      if (!status) { status = document.createElement('span'); status.className='paper-analysis-state'; row.querySelector('div')?.appendChild(status); }
      const job = jobForPaper(paper);
      if (paper.review_depth === 'full_text_reviewed') { status.className='paper-analysis-state done'; status.textContent=msg('✓ Analizado','✓ Reviewed','✓ Analisado','✓ Analysé'); }
      else if (job?.status === 'running') { status.className='paper-analysis-state running'; status.textContent=msg('Analizando…','Analyzing…','Analisando…','Analyse…'); }
      else if (job?.status === 'failed') { status.className='paper-analysis-state failed'; status.textContent=msg('Falló el análisis','Review failed','Análise falhou','Analyse échouée'); }
      else if (job) { status.className='paper-analysis-state'; status.textContent=msg('En cola','Queued','Na fila','En file'); }
      else { status.className='paper-analysis-state'; status.textContent=msg('Sin analizar','Not reviewed','Não analisado','Non analysé'); }
      const actions = row.querySelector('.paper-actions');
      if (actions && paper.review_depth !== 'full_text_reviewed' && !row.querySelector('.analyze-paper')) {
        const b=document.createElement('button'); b.className='primary analyze-paper'; b.textContent=msg('Analizar ahora','Analyze now','Analisar agora','Analyser maintenant');
        b.onclick=async()=>{b.disabled=true;try{const j=await queuePaperReview(paper,false);if(j)await runFolderJob(j.job_id)}finally{b.disabled=false}};
        actions.prepend(b);
      }
    });
  }

  if (base.uploadPapers) {
    uploadPapers = async function() {
      const before = new Set((state.library || []).map(p=>p.item_id));
      await base.uploadPapers();
      const fresh = (state.library || []).filter(p=>!before.has(p.item_id));
      if (!fresh.length) return;
      for (const paper of fresh) await queuePaperReview(paper, false);
      toast(msg(`${fresh.length} paper${fresh.length>1?'s':''} subido${fresh.length>1?'s':''} y agregado${fresh.length>1?'s':''} a la cola de análisis.`,`Uploaded ${fresh.length} paper${fresh.length>1?'s':''} and queued for review.`,`Enviados ${fresh.length} papers e adicionados à fila de análise.`,`Téléversé ${fresh.length} article(s) et ajouté(s) à la file d’analyse.`));
      await refreshJobs();
      renderPaperAnalysisButtons(); renderGuidedFlow();
      if (fresh.length === 1) {
        const j = jobForPaper(fresh[0]);
        if (j) runFolderJob(j.job_id).catch(()=>{});
      }
    };
  }

  if (base.refreshJobs) {
    refreshJobs = async function() {
      const folder = typeof selectedFolder === 'function' ? selectedFolder() : null;
      if (!folder) { state.jobs=[]; base.renderJobs?.(); renderGuidedFlow(); return; }
      try {
        const params = new URLSearchParams({folder_id:folder.folder_id});
        if (state.session?.folder_id === folder.folder_id) params.set('session_id',state.session.session_id);
        const r = await api('/api/jobs?'+params.toString());
        state.jobs=r.jobs||[];
        base.renderJobs?.(); renderPaperAnalysisButtons(); renderGuidedFlow();
      } catch(e) { log?.('Jobs',e.message); }
    };
  }

  if (base.renderLibrary) {
    renderLibrary = function() { base.renderLibrary(); renderPaperAnalysisButtons(); renderGuidedFlow(); };
  }
  if (base.loadLibrary) {
    loadLibrary = async function() { const r=await base.loadLibrary(); await refreshJobs().catch(()=>{}); renderPaperAnalysisButtons(); renderGuidedFlow(); return r; };
  }

  async function loadScientificMap() {
    const folder=typeof selectedFolder==='function'?selectedFolder():null;
    if(!folder){graphSummary=null;graphNodes=[];contradictions=[];competitions=[];renderMap();renderGuidedFlow();return;}
    const f=encodeURIComponent(folder.folder_id);
    const calls=await Promise.allSettled([
      api(`/api/science?op=graph_summary&folder_id=${f}`),
      api(`/api/science?op=graph_nodes&folder_id=${f}&limit=5000`),
      api(`/api/science?op=contradictions&folder_id=${f}&limit=500`),
      api(`/api/science?op=hypotheses&folder_id=${f}&limit=20`),
    ]);
    graphSummary=calls[0].status==='fulfilled'?calls[0].value:null;
    graphNodes=calls[1].status==='fulfilled'?(calls[1].value.nodes||[]):[];
    contradictions=calls[2].status==='fulfilled'?(calls[2].value.contradictions||[]):[];
    competitions=calls[3].status==='fulfilled'?(calls[3].value.competitions||[]):[];
    renderMap();renderGuidedFlow();
  }

  function renderMap(nodeType='claim') {
    const folder=typeof selectedFolder==='function'?selectedFolder():null;
    const context=q('#map-folder-context'); if(context)context.textContent=folder?`${msg('Carpeta activa','Active folder','Pasta ativa','Dossier actif')}: ${folder.name}`:msg('Selecciona una carpeta.','Select a folder.','Selecione uma pasta.','Sélectionnez un dossier.');
    const types=graphSummary?.node_types||{};
    const metrics=[['papers',types.paper||0],['claims',types.claim||0],['evidence',types.evidence||0],['models',types.model||0],['contradictions',graphSummary?.contradictions||0],['hypotheses',graphSummary?.candidate_hypotheses||0]];
    const m=q('#map-metrics');if(m)m.innerHTML=metrics.map(([k,v])=>`<div class="map-metric"><strong>${v}</strong><span>${html(k)}</span></div>`).join('');
    const filters=['claim','evidence','model','assumption','equation','diagnostic','paper'];
    const fb=q('#map-node-filters');if(fb){fb.innerHTML=filters.map(x=>`<button class="ghost node-type ${x===nodeType?'active':''}" data-type="${x}">${html(x)} (${types[x]||0})</button>`).join('');qa('.node-type').forEach(b=>b.onclick=()=>renderMap(b.dataset.type));}
    const rows=graphNodes.filter(n=>n.node_type===nodeType).slice(0,100);
    const nb=q('#map-nodes');if(nb){nb.className=rows.length?'map-list':'map-list empty';nb.innerHTML=rows.length?rows.map(n=>`<div class="map-card"><h3>${html(n.label)}</h3><code>${html(n.paper_id||'')} · ${html(n.epistemic_state||'')}</code></div>`).join(''):msg('No hay nodos de este tipo.','No nodes of this type.','Não há nós deste tipo.','Aucun nœud de ce type.');}
    const cb=q('#map-contradiction-count');if(cb)cb.textContent=String(contradictions.length);
    const cl=q('#map-contradiction-list');if(cl){cl.className=contradictions.length?'map-list':'map-list empty';cl.innerHTML=contradictions.length?contradictions.map(c=>`<div class="map-card"><h3>${html(c.summary)}</h3><p><strong>${html(msg('Explicación posible','Possible explanation','Explicação possível','Explication possible'))}:</strong> ${html(c.possible_explanation||'—')}</p><p><strong>${html(msg('Prueba discriminante','Discriminating test','Teste discriminante','Test discriminant'))}:</strong> ${html(c.required_test||'—')}</p><code>${Math.round((c.confidence||0)*100)}% · ${html(c.status)}</code></div>`).join(''):msg('Aún no hay contradicciones analizadas.','No contradictions analyzed yet.','Ainda não há contradições analisadas.','Aucune contradiction analysée pour le moment.');}
    const hs=competitions.flatMap(c=>(c.hypotheses||[]).map(h=>({...h,question:c.question,decision_needed:c.decision_needed})));
    const hl=q('#map-hypothesis-list');if(hl){hl.className=hs.length?'map-list':'map-list empty';hl.innerHTML=hs.length?hs.map(h=>`<div class="map-card"><h3>${html(h.statement)}</h3><p><strong>${html(msg('Mecanismo','Mechanism','Mecanismo','Mécanisme'))}:</strong> ${html(h.mechanism||'—')}</p><p><strong>${html(msg('Predicciones','Predictions','Predições','Prédictions'))}:</strong> ${html((h.falsifiable_predictions||[]).join(' · ')||'—')}</p><p><strong>${html(msg('Observables','Observables','Observáveis','Observables'))}:</strong> ${html((h.discriminating_observables||[]).join(', ')||'—')}</p><p><strong>${html(msg('Experimento discriminante','Discriminating experiment','Experimento discriminante','Expérience discriminante'))}:</strong> ${html(h.discriminating_experiment||'—')}</p><p><strong>${html(msg('Criterio de rechazo','Rejection criterion','Critério de rejeição','Critère de rejet'))}:</strong> ${html(h.rejection_criterion||'—')}</p></div>`).join(''):msg('Genera hipótesis después de analizar contradicciones.','Generate hypotheses after contradiction analysis.','Gere hipóteses após analisar contradições.','Générez des hypothèses après l’analyse des contradictions.');}
  }

  async function buildGraph(){const folder=selectedFolder?.();if(!folder)return toast(msg('Selecciona una carpeta.','Select a folder.','Selecione uma pasta.','Sélectionnez un dossier.'),true);try{toast(msg('Construyendo mapa científico…','Building scientific map…','Construindo mapa científico…','Construction de la carte scientifique…'));await api('/api/science?op=build_graph',{method:'POST',body:JSON.stringify({folder_id:folder.folder_id,full_text_only:true})});await loadScientificMap();toast(msg('Mapa científico actualizado.','Scientific map updated.','Mapa científico atualizado.','Carte scientifique actualisée.'))}catch(e){toast(msg('No se pudo construir el mapa: ','Could not build map: ','Não foi possível construir o mapa: ','Impossible de construire la carte : ')+e.message,true)}}
  async function detectContradictions(){const folder=selectedFolder?.();if(!folder)return;try{toast(msg('Analizando contradicciones…','Analyzing contradictions…','Analisando contradições…','Analyse des contradictions…'));await api('/api/science?op=detect_contradictions',{method:'POST',body:JSON.stringify({folder_id:folder.folder_id})});await loadScientificMap();toast(msg('Análisis de contradicciones completado.','Contradiction analysis completed.','Análise de contradições concluída.','Analyse des contradictions terminée.'))}catch(e){toast(msg('No se pudieron analizar contradicciones: ','Could not analyze contradictions: ','Não foi possível analisar contradições: ','Impossible d’analyser les contradictions : ')+e.message,true)}}
  async function generateHypotheses(){const folder=selectedFolder?.();if(!folder)return;const question=q('#map-question')?.value.trim()||state.session?.question||'';if(!question)return toast(msg('Escribe una pregunta científica o crea un proyecto primero.','Enter a scientific question or create a project first.','Digite uma pergunta científica ou crie um projeto primeiro.','Saisissez une question scientifique ou créez d’abord un projet.'),true);try{toast(msg('Generando hipótesis competidoras…','Generating competing hypotheses…','Gerando hipóteses concorrentes…','Génération d’hypothèses concurrentes…'));await api('/api/science?op=generate_hypotheses',{method:'POST',body:JSON.stringify({folder_id:folder.folder_id,question})});await loadScientificMap();toast(msg('Hipótesis generadas.','Hypotheses generated.','Hipóteses geradas.','Hypothèses générées.'))}catch(e){toast(msg('No se pudieron generar hipótesis: ','Could not generate hypotheses: ','Não foi possível gerar hipóteses: ','Impossible de générer les hypothèses : ')+e.message,true)}}

  if (base.setView) {
    setView = function(name) {
      base.setView(name);
      if(name==='map'){const title=q('#page-title');if(title)title.textContent=msg('Mapa científico','Scientific map','Mapa científico','Carte scientifique');loadScientificMap().catch(()=>{});}
    };
  }

  document.addEventListener('scibrain:languagechange',()=>{setupMapView();renderGuidedFlow();renderPaperAnalysisButtons();renderMap();});
  window.addEventListener('DOMContentLoaded',()=>{
    injectStyles(); setupMapView(); setupGuidedFlow();
    setTimeout(async()=>{await refreshJobs?.().catch(()=>{});await loadScientificMap().catch(()=>{});renderPaperAnalysisButtons();renderGuidedFlow();},700);
  });
})();
