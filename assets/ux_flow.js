(() => {
  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const lang = () => window.SBI18N?.language?.() || 'es';
  const msg = (es,en,pt=es,fr=es) => ({es,en,pt,fr}[lang()] || es);
  const escx = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const base = {
    renderLibrary: typeof renderLibrary === 'function' ? renderLibrary : null,
    renderFolders: typeof renderFolders === 'function' ? renderFolders : null,
    renderSession: typeof renderSession === 'function' ? renderSession : null,
    selectFolder: typeof selectFolder === 'function' ? selectFolder : null,
    setView: typeof setView === 'function' ? setView : null,
  };
  let processing = false;
  let study = null, suggestions = null, reviews = [], messages = [];
  let graph = null, graphNodes = [], contradictions = [], competitions = [];

  const dynamicIds = [
    'folder-list','paper-list','paper-progress-label','selected-folder-title','selected-folder-meta',
    'overview-folder-context','definition-folder-context','research-folder-context','projects-folder-context',
    'research-results','research-source-summary','jobs-list','review-progress-summary','session-summary',
    'stage-agents','artifact-list','projects-list','map-folder-context'
  ];
  function stripDynamicI18n(){ dynamicIds.forEach(id=>q('#'+id)?.removeAttribute('data-i18n')); }
  function folder(){ return typeof selectedFolder === 'function' ? selectedFolder() : null; }
  function fullTextAvailable(p){ return !!(p.storage_path || p.pdf_url || p.arxiv_id || ['uploaded','open_access','public_full_text'].includes(p.access_status)); }
  function paperKey(p){ return p.canonical_id || p.item_id; }
  function jobFor(p){ return (state.jobs||[]).find(j=>j.job_type==='review_paper' && j.payload?.paper_id===p.canonical_id); }

  function injectStyles(){
    if(q('#v09-styles')) return;
    const s=document.createElement('style');s.id='v09-styles';s.textContent=`
    .flow9{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.flow9>div{border:1px solid #e4e7ec;border-radius:12px;padding:12px}.flow9 .done{background:#f6fef9;border-color:#abefc6}.flow9 .active{background:#f5f8ff;border-color:#8098f9}.flow9 b{display:block;margin-bottom:5px}.access-badge,.paper-state{display:inline-flex;padding:3px 7px;border-radius:999px;font-size:10px;margin:4px 5px 0 0}.access-oa,.paper-state.done{background:#ecfdf3;color:#067647}.access-public{background:#eff8ff;color:#175cd3}.access-page{background:#f9f5ff;color:#6941c6}.access-locked,.paper-state.fail{background:#fef3f2;color:#b42318}.access-meta,.paper-state.queue{background:#f2f4f7;color:#475467}.paper-state.run{background:#fff4e5;color:#b54708}.studio-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(300px,.7fr);gap:16px}.section-card{border:1px solid #e4e7ec;border-radius:12px;padding:14px;margin-bottom:12px}.section-card textarea{min-height:150px;width:100%}.source-refs{font-size:10px;color:#667085;margin-top:6px}.discussion{max-height:430px;overflow:auto;display:grid;gap:9px}.bubble{padding:10px 12px;border-radius:12px;background:#f2f4f7;white-space:pre-wrap;font-size:12px}.bubble.user{background:#eef2ff}.bubble.agent{border:1px solid #e4e7ec;background:white}.suggestion{border:1px solid #e4e7ec;border-radius:10px;padding:11px;margin:8px 0}.map-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}.map-metric{border:1px solid #e4e7ec;border-radius:10px;padding:10px}.map-metric strong{display:block;font-size:22px}.map-list{display:grid;gap:8px}.map-card{border:1px solid #e4e7ec;border-radius:10px;padding:11px}.advanced-tag{font-size:9px;background:#344054;color:#fff;border-radius:99px;padding:2px 6px;margin-left:5px}.goal-note{font-size:11px;color:#667085}.analysis-info{padding:10px;border:1px solid #b2ccff;background:#eff8ff;border-radius:10px;margin:10px 0;color:#1849a9}.studio-actions{display:flex;gap:8px;flex-wrap:wrap}.studio-actions button{width:auto}@media(max-width:1100px){.flow9{grid-template-columns:repeat(2,1fr)}.studio-grid{grid-template-columns:1fr}.map-metrics{grid-template-columns:repeat(3,1fr)}}@media(max-width:650px){.flow9,.map-metrics{grid-template-columns:1fr}}
    `;document.head.appendChild(s);
  }

  function decorateAdvancedNav(){
    const def=q('[data-view="definition"]'), ses=q('[data-view="session"]');
    if(def){def.innerHTML=`${escx(msg('Definición formal','Formal definition','Definição formal','Définition formelle'))}<span class="advanced-tag">${escx(msg('Avanzado','Advanced','Avançado','Avancé'))}</span>`;}
    if(ses){ses.innerHTML=`${escx(msg('Sesión de agentes','Agent session','Sessão de agentes','Session agents'))}<span class="advanced-tag">${escx(msg('Avanzado','Advanced','Avançado','Avancé'))}</span>`;}
  }

  function setupWorkflow(){
    const root=q('#view-overview'); if(!root || q('#workflow-v09')) return;
    const card=document.createElement('article');card.id='workflow-v09';card.className='card';
    const anchor=q('#overview-folder-context'); anchor?.after(card); renderWorkflow();
  }
  function renderWorkflow(){
    const card=q('#workflow-v09'); if(!card) return;
    const f=folder(), papers=state.library||[], reviewed=papers.filter(p=>p.review_depth==='full_text_reviewed').length;
    const steps=[
      [!!f,msg('1. Tema y carpeta','1. Topic & folder'),f?.name||msg('Elige una línea de trabajo','Choose a research line'),'workspace'],
      [papers.length>0,msg('2. Fuentes','2. Sources'),`${papers.length} ${msg('papers disponibles','papers available')}`,'literature'],
      [reviewed>0,msg('3. Analizar','3. Analyze'),`${reviewed}/${papers.length} ${msg('a texto completo','full text')}`,'literature'],
      [!!study,msg('4. Estudio colaborativo','4. Collaborative study'),study?.title||msg('Pregunta, borrador y discusión','Question, draft and discussion'),'study'],
      [(graph?.nodes||0)>0,msg('5. Contrastar','5. Challenge'),msg('Mapa, contradicciones e hipótesis','Map, contradictions and hypotheses'),'map'],
    ];
    const next=steps.findIndex(x=>!x[0]);
    card.innerHTML=`<div class="card-head"><div><h2>${escx(msg('Flujo recomendado','Recommended workflow'))}</h2><p class="muted">${escx(msg('La meta de papers es orientativa: puedes avanzar con las fuentes que ya tengas.','The paper target is a guide: you can proceed with the sources you already have.'))}</p></div></div><div class="flow9">${steps.map((s,i)=>`<div class="${s[0]?'done':i===next?'active':''}"><b>${s[0]?'✓ ':''}${escx(s[1])}</b><span>${escx(s[2])}</span><br><button class="ghost flow-go" data-go="${s[3]}">${escx(msg('Abrir','Open'))}</button></div>`).join('')}</div>`;
    qa('.flow-go').forEach(b=>b.onclick=()=>setView(b.dataset.go));
  }

  if(base.renderFolders){ renderFolders=function(){ stripDynamicI18n(); base.renderFolders(); const list=q('#folder-list'); if(list&&state.folders?.length) list.removeAttribute('data-i18n'); renderWorkflow(); }; }
  if(base.renderLibrary){ renderLibrary=function(){ stripDynamicI18n(); base.renderLibrary(); decoratePapers(); renderAnalysis(); renderWorkflow(); }; }
  if(base.renderSession){ renderSession=function(){ base.renderSession(); renderAnalysis(); }; }
  if(base.selectFolder){ selectFolder=async function(id){ const r=await base.selectFolder(id); study=null;suggestions=null;await refreshFolderJobs().catch(()=>{});await loadStudy().catch(()=>{});await loadMap().catch(()=>{});renderWorkflow();return r; }; }

  function accessMeta(r){
    const status=r.access_status||'metadata_only';
    if(status==='open_access') return [msg('Open Access verificado','Verified Open Access'),'access-oa'];
    if(status==='public_full_text') return [msg('Texto completo público','Public full text'),'access-public'];
    if(status==='oa_landing_page') return [msg('Página Open Access','Open Access page'),'access-public'];
    if(status==='public_page') return [msg('Página pública','Public page'),'access-page'];
    if(status==='uploaded') return [msg('PDF privado cargado','Private PDF uploaded'),'access-oa'];
    if(status==='restricted_or_unknown'||status==='manual_download') return [msg('Acceso no verificado/restringido','Restricted/unverified'),'access-locked'];
    return [msg('Solo metadatos','Metadata only'),'access-meta'];
  }
  function decoratePapers(){
    qa('#paper-list .paper-row').forEach(row=>{
      const item=row.querySelector('.delete-paper')?.dataset.item;
      const p=(state.library||[]).find(x=>x.item_id===item); if(!p)return;
      row.querySelectorAll('.paper-state,.access-badge').forEach(x=>x.remove());
      const [label,cls]=accessMeta(p); const meta=row.querySelector('.paper-meta:last-of-type')||row.querySelector('.paper-meta');
      if(meta) meta.insertAdjacentHTML('afterend',`<span class="access-badge ${cls}">${escx(label)}</span>`);
      const j=jobFor(p); let st=msg('Sin analizar','Not analyzed'), sc='queue';
      if(p.review_depth==='full_text_reviewed'){st=msg('✓ Analizado','✓ Analyzed');sc='done';}
      else if(j?.status==='running'){st=msg('Analizando…','Analyzing…');sc='run';}
      else if(j?.status==='failed'){st=msg('Falló · reintentar','Failed · retry');sc='fail';}
      else if(j){st=msg('En cola','Queued');sc='queue';}
      if(meta) meta.insertAdjacentHTML('afterend',`<span class="paper-state ${sc}">${escx(st)}</span>`);
      const actions=row.querySelector('.paper-actions');
      if(actions && p.review_depth!=='full_text_reviewed' && !actions.querySelector('.v09-analyze')){
        const b=document.createElement('button');b.className='primary v09-analyze';
        b.textContent=fullTextAvailable(p)?msg('Analizar ahora','Analyze now'):msg('PDF requerido','PDF required');b.disabled=!fullTextAvailable(p);
        b.onclick=()=>analyzePaper(p,b);actions.prepend(b);
      }
    });
  }

  function renderResearchResultsV09(){
    const box=q('#research-results'); if(!box)return;
    const rows=state.researchResults||[]; const existing=new Set((state.library||[]).map(p=>paperKey(p)));
    if(!rows.length){box.className='result-list empty';box.textContent=msg('No hay resultados.','No results.');return;}
    box.className='result-list';box.innerHTML=rows.map((r,i)=>{
      const [lab,cls]=accessMeta(r), added=existing.has(paperKey(r));
      const open=r.pdf_url||r.url; const rg=`https://www.researchgate.net/search/publication?q=${encodeURIComponent(r.title||'')}`;
      return `<div class="result-card"><h3>${escx(r.title)}</h3><div class="source-line"><span>${escx(r.source||'')}</span><span>${escx(r.publication_date||'')}</span>${r.doi?`<span>DOI ${escx(r.doi)}</span>`:''}<span class="access-badge ${cls}">${escx(lab)}</span></div>${r.abstract?`<p>${escx(String(r.abstract).replace(/<[^>]+>/g,' '))}</p>`:''}${r.manual_lookup_message?`<div class="manual-note">${escx(r.manual_lookup_message)}</div>`:''}<div class="row">${open?`<a class="secondary linklike" target="_blank" rel="noopener" href="${escx(open)}">${escx(r.pdf_url?msg('Abrir PDF','Open PDF'):msg('Abrir fuente','Open source'))}</a>`:''}${!r.pdf_url?`<a class="ghost linklike" target="_blank" rel="noopener" href="${escx(rg)}">ResearchGate</a>`:''}<button class="primary v09-add-result" data-i="${i}" ${added?'disabled':''}>${escx(added?msg('Agregado ✓','Added ✓'):msg('Agregar a carpeta','Add to folder'))}</button></div></div>`;
    }).join('');
    qa('.v09-add-result').forEach(b=>b.onclick=()=>addResult(Number(b.dataset.i),b));
  }
  renderResearchResults=renderResearchResultsV09;
  async function addResult(i,b){
    const f=folder(),r=state.researchResults?.[i];if(!f||!r)return;b.disabled=true;
    try{await api('/api/library',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,canonical_id:r.canonical_id,title:r.title,authors:r.authors||[],publication_date:r.publication_date||null,journal:r.journal||null,doi:r.doi||null,arxiv_id:r.arxiv_id||null,source_type:r.source||'web',source_url:r.url||null,pdf_url:r.pdf_url||null,access_status:r.access_status||'metadata_only',manual_lookup_required:!!r.manual_lookup_required,abstract:r.abstract||'',cited_by_count:r.cited_by_count||0})});await loadLibrary();renderResearchResultsV09();toast(msg('Paper agregado. Puedes seguir agregando resultados de esta misma búsqueda.','Paper added. You can keep adding results from this search.'));}catch(e){b.disabled=false;toast(msg('No se pudo agregar: ','Could not add: ')+e.message,true);}
  }
  addResearchResult=addResult;

  async function refreshFolderJobs(){
    const f=folder();if(!f){state.jobs=[];renderAnalysis();return;}
    try{const r=await api('/api/jobs?folder_id='+encodeURIComponent(f.folder_id));state.jobs=r.jobs||[];}catch(e){state.jobs=[];}
    renderJobsV09();decoratePapers();renderAnalysis();
  }
  refreshJobs=refreshFolderJobs;
  function renderJobsV09(){
    const box=q('#jobs-list');if(!box)return;const jobs=(state.jobs||[]).filter(j=>j.job_type==='review_paper');
    if(!jobs.length){box.className='jobs-list empty';box.textContent=msg('No hay análisis en cola.','No analyses queued.');return;}
    box.className='artifact-list';box.innerHTML=jobs.slice(0,30).map(j=>`<div class="agent-row"><div><strong>${escx(msg('Análisis de paper','Paper analysis'))}</strong><span>${escx(j.payload?.paper_id||'')}<br>${escx(j.last_error||'')}</span></div><span class="agent-state">${escx(j.status)}</span></div>`).join('');
  }
  async function queuePaper(p){
    const existing=jobFor(p);if(existing&&['pending','running','completed'].includes(existing.status))return existing;
    return api('/api/jobs',{method:'POST',body:JSON.stringify({folder_id:folder().folder_id,session_id:state.session?.folder_id===folder().folder_id?state.session.session_id:null,job_type:'review_paper',payload:{paper_id:p.canonical_id,pdf_url:p.pdf_url||null}})});
  }
  async function analyzePaper(p,b){
    if(!fullTextAvailable(p))return toast(msg('Este registro necesita un PDF o una ruta pública de texto completo.','This record needs a PDF or public full-text route.'),true);
    if(b){b.disabled=true;b.textContent=msg('Analizando…','Analyzing…');}
    try{const j=await queuePaper(p);await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:j.job_id})});await loadLibrary();await refreshFolderJobs();toast(msg('Análisis científico completado.','Scientific analysis completed.'));}catch(e){toast(msg('El análisis falló: ','Analysis failed: ')+e.message,true);await refreshFolderJobs();}finally{if(b)b.disabled=false;}
  }
  async function prepareReviews(){
    const papers=(state.library||[]).filter(p=>p.review_depth!=='full_text_reviewed'&&fullTextAvailable(p));let n=0;
    for(const p of papers.slice(0,100)){const j=jobFor(p);if(!j||j.status==='failed'){await queuePaper(p);n++;}}
    await refreshFolderJobs();toast(`${n} ${msg('papers preparados para análisis.','papers queued for analysis.')}`);
  }
  async function analyzeNext(){
    await refreshFolderJobs();let j=(state.jobs||[]).find(x=>x.job_type==='review_paper'&&['pending','failed'].includes(x.status));
    if(!j){const p=(state.library||[]).find(x=>x.review_depth!=='full_text_reviewed'&&fullTextAvailable(x));if(p)j=await queuePaper(p);}
    if(!j)return toast(msg('No hay papers analizables pendientes.','No analyzable papers pending.'));
    try{await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:j.job_id})});await loadLibrary();await refreshFolderJobs();toast(msg('Paper analizado.','Paper analyzed.'));}catch(e){toast(msg('Falló el análisis: ','Analysis failed: ')+e.message,true);}
  }
  async function analyzeQueue(){
    if(processing){processing=false;return;}processing=true;renderAnalysis();let done=0;
    try{while(processing&&done<100){await refreshFolderJobs();const j=(state.jobs||[]).find(x=>x.job_type==='review_paper'&&x.status==='pending');if(!j)break;try{await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:j.job_id})});done++;}catch{break;}}await loadLibrary();await refreshFolderJobs();}finally{processing=false;renderAnalysis();}if(done)toast(`${done} ${msg('papers analizados.','papers analyzed.')}`);
  }
  function bindAnalysisButtons(){
    const binds=[['#enqueue-reviews',prepareReviews],['#process-next-review',analyzeNext],['#process-review-queue',analyzeQueue],['#refresh-jobs',refreshFolderJobs]];
    binds.forEach(([sel,fn])=>{const old=q(sel);if(!old)return;const n=old.cloneNode(true);old.replaceWith(n);n.onclick=fn;});renderAnalysis();
  }
  function renderAnalysis(){
    const papers=state.library||[], reviewed=papers.filter(p=>p.review_depth==='full_text_reviewed').length, accessible=papers.filter(p=>p.review_depth!=='full_text_reviewed'&&fullTextAvailable(p)).length;
    const s=q('#review-progress-summary');if(s)s.textContent=`${reviewed} ${msg('analizados a texto completo','full-text analyzed')} · ${papers.length} ${msg('en la carpeta','in folder')} · ${accessible} ${msg('listos para analizar','ready to analyze')}`;
    ['#enqueue-reviews','#process-next-review','#process-review-queue'].forEach(sel=>{const b=q(sel);if(b)b.disabled=!folder()||!papers.length;});
    const b=q('#process-review-queue');if(b)b.textContent=processing?msg('Detener cola','Stop queue'):msg('Procesar cola','Process queue');
  }

  function setupStudy(){
    const nav=q('.sidebar nav');if(nav&&!q('[data-view="study"]')){const b=document.createElement('button');b.className='nav';b.dataset.view='study';b.textContent=msg('Estudio colaborativo','Collaborative study');const map=q('[data-view="map"]')||q('[data-view="protocol"]');nav.insertBefore(b,map);b.onclick=()=>setView('study');}
    if(q('#view-study'))return;const sec=document.createElement('section');sec.id='view-study';sec.className='view';sec.innerHTML=`
    <div class="folder-context" id="study-context"></div><div class="studio-grid"><div>
    <article class="card"><div class="card-head"><div><h2>${escx(msg('Tema y pregunta de investigación','Topic and research question'))}</h2><p class="muted">${escx(msg('ScientificBrain propone, redacta y contrasta; tú puedes editar todo.','ScientificBrain proposes, drafts and challenges; you can edit everything.'))}</p></div></div><label>${escx(msg('Tema','Topic'))}<input id="study-topic"></label><label>${escx(msg('Pregunta de investigación','Research question'))}<textarea id="study-question" class="small-editor"></textarea></label><div class="studio-actions"><button id="study-suggest" class="secondary">${escx(msg('Sugerir preguntas y brechas','Suggest questions and gaps'))}</button><button id="study-search" class="ghost">${escx(msg('Buscar más papers','Search more papers'))}</button><button id="study-generate" class="primary">${escx(msg('Generar / actualizar borrador','Generate / update draft'))}</button><button id="study-save" class="ghost">${escx(msg('Guardar ediciones','Save edits'))}</button></div><div id="study-suggestions"></div></article>
    <div id="study-sections"></div></div><aside>
    <article class="card"><h2>${escx(msg('Discusión con agentes','Discussion with agents'))}</h2><p class="muted">${escx(msg('Pregunta, objeta o solicita una revisión. El agente puede discrepar y debe apoyar afirmaciones con las fuentes disponibles.','Question, challenge or request a review. The agent may disagree and must ground claims in available sources.'))}</p><label>${escx(msg('Agente','Agent'))}<select id="chat-role"><option value="adversarial">Adversarial</option><option value="theory">Teoría</option><option value="experiment">Experimental</option><option value="methodology">Metodología</option><option value="reproducibility">Reproducibilidad</option><option value="writer">Editor científico</option></select></label><div id="study-messages" class="discussion"></div><textarea id="study-chat" class="small-editor" placeholder="${escx(msg('Discute una afirmación, pide evidencia o propone un cambio…','Discuss a claim, ask for evidence, or propose a change…'))}"></textarea><button id="study-send" class="primary">${escx(msg('Enviar al agente','Send to agent'))}</button></article><article class="card"><h2>${escx(msg('Última revisión crítica','Latest critical review'))}</h2><div id="study-review">—</div></article></aside></div>`;q('#view-protocol')?.parentNode?.insertBefore(sec,q('#view-protocol'));
    q('#study-suggest').onclick=suggestStudy;q('#study-search').onclick=searchFromStudy;q('#study-generate').onclick=generateStudy;q('#study-save').onclick=saveStudy;q('#study-send').onclick=sendChat;
  }
  const sectionNames={resumen:'Resumen / abstract',estado_del_arte:'Estado del arte',brecha:'Brecha de conocimiento',pregunta_investigacion:'Pregunta de investigación',objetivo_general:'Objetivo general',objetivos_especificos:'Objetivos específicos',hipotesis:'Hipótesis',desarrollo:'Desarrollo / marco científico',analisis_discusion:'Análisis y discusión',conclusiones:'Conclusiones',limitaciones:'Limitaciones',proximos_pasos:'Próximos pasos'};
  async function loadStudy(){const f=folder();if(!f){study=null;renderStudy();return;}try{study=(await api(`/api/science?op=study&folder_id=${encodeURIComponent(f.folder_id)}`)).study||null;if(study){const r=await Promise.allSettled([api(`/api/science?op=study_messages&study_id=${encodeURIComponent(study.study_id)}`),api(`/api/science?op=study_reviews&study_id=${encodeURIComponent(study.study_id)}`)]);messages=r[0].status==='fulfilled'?(r[0].value.messages||[]):[];reviews=r[1].status==='fulfilled'?(r[1].value.reviews||[]):[];}renderStudy();}catch(e){renderStudy();}}
  function renderStudy(){
    const f=folder(), ctx=q('#study-context');if(ctx)ctx.textContent=f?`${msg('Carpeta activa','Active folder')}: ${f.name} · ${(state.library||[]).length} ${msg('papers; la meta no bloquea el avance','papers; target does not block progress')}`:msg('Selecciona una carpeta.','Select a folder.');
    if(q('#study-topic')&&!q('#study-topic').matches(':focus'))q('#study-topic').value=study?.topic||f?.research_line||f?.area||'';
    if(q('#study-question')&&!q('#study-question').matches(':focus'))q('#study-question').value=study?.research_question||'';
    const sections=q('#study-sections');if(sections){const data=study?.sections||{};sections.innerHTML=Object.entries(sectionNames).map(([key,name])=>{const x=data[key]||{};return `<article class="card section-card"><div class="card-head"><h2>${escx(name)}</h2><button class="secondary review-section" data-section="${key}">${escx(msg('Revisar con agente','Review with agent'))}</button></div><textarea data-study-section="${key}">${escx(x.content||'')}</textarea><div class="source-refs">${x.source_refs?.length?escx(msg('Fuentes: ','Sources: ')+x.source_refs.join(', ')):escx(msg('Sin referencias asignadas todavía.','No source references assigned yet.'))}</div></article>`}).join('');qa('.review-section').forEach(b=>b.onclick=()=>reviewSection(b.dataset.section,b));}
    const chat=q('#study-messages');if(chat){chat.innerHTML=messages.length?messages.map(m=>`<div class="bubble ${m.speaker}"><strong>${escx(m.speaker==='user'?msg('Tú','You'):(m.agent_role||'agent'))}</strong><br>${escx(m.content)}</div>`).join(''):`<div class="muted">${escx(msg('Inicia una discusión después de crear el estudio.','Start a discussion after creating the study.'))}</div>`;chat.scrollTop=chat.scrollHeight;}
    const rv=q('#study-review');if(rv){const last=reviews[0]?.review;rv.innerHTML=last?`<strong>${escx(last.verdict||'')}</strong><p>${escx((last.concerns||[]).join(' · '))}</p><p><b>${escx(msg('Cambios requeridos:','Required changes:'))}</b> ${escx((last.required_changes||[]).join(' · '))}</p>`:'—';}
    renderWorkflow();
  }
  async function ensureStudy(){if(study)return study;const f=folder(),topic=q('#study-topic')?.value.trim();if(!f||!topic)throw new Error(msg('Selecciona carpeta y escribe un tema.','Select a folder and enter a topic.'));const r=await api('/api/science?op=study_create',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,topic,research_question:q('#study-question')?.value.trim()||'',language:lang()})});study=r.study;return study;}
  async function suggestStudy(){const f=folder(),topic=q('#study-topic')?.value.trim();if(!f||!topic)return toast(msg('Escribe el tema a investigar.','Enter the research topic.'),true);const b=q('#study-suggest');b.disabled=true;b.textContent=msg('Analizando corpus…','Analyzing corpus…');try{suggestions=await api('/api/science?op=study_suggest',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,topic,language:lang()})});renderSuggestions();}catch(e){toast(msg('No se pudieron generar sugerencias: ','Could not generate suggestions: ')+e.message,true);}finally{b.disabled=false;b.textContent=msg('Sugerir preguntas y brechas','Suggest questions and gaps');}}
  function renderSuggestions(){const box=q('#study-suggestions');if(!box||!suggestions)return;const qs=suggestions.research_questions||[];box.innerHTML=`<h3>${escx(msg('Preguntas sugeridas','Suggested questions'))}</h3>${qs.map((x,i)=>`<div class="suggestion"><strong>${escx(x.question||x)}</strong><p>${escx(x.rationale||'')}</p><button class="ghost use-question" data-i="${i}">${escx(msg('Usar esta pregunta','Use this question'))}</button></div>`).join('')}<h3>${escx(msg('Brechas detectadas','Detected gaps'))}</h3><ul>${(suggestions.gaps||[]).map(x=>`<li>${escx(x)}</li>`).join('')}</ul>`;qa('.use-question').forEach(b=>b.onclick=()=>{const x=qs[Number(b.dataset.i)];q('#study-question').value=x.question||x;});}
  function searchFromStudy(){const topic=q('#study-topic')?.value.trim(),question=q('#study-question')?.value.trim();q('#research-query').value=[topic,question].filter(Boolean).join(' ');setView('literature');}
  async function saveStudy(){try{await ensureStudy();const sections={};qa('[data-study-section]').forEach(t=>sections[t.dataset.studySection]={content:t.value,source_refs:study?.sections?.[t.dataset.studySection]?.source_refs||[],status:'edited_by_user'});const r=await api('/api/science?op=study',{method:'PATCH',body:JSON.stringify({study_id:study.study_id,topic:q('#study-topic').value.trim(),research_question:q('#study-question').value.trim(),sections})});study=r.study;renderStudy();toast(msg('Ediciones guardadas.','Edits saved.'));}catch(e){toast(msg('No se pudo guardar: ','Could not save: ')+e.message,true);}}
  async function generateStudy(){const b=q('#study-generate');b.disabled=true;b.textContent=msg('Generando…','Generating…');try{await ensureStudy();await saveStudy();const r=await api('/api/science?op=study_generate',{method:'POST',body:JSON.stringify({study_id:study.study_id,language:lang()})});study=r.study;renderStudy();toast(msg('Borrador científico actualizado y editable.','Scientific draft updated and editable.'));}catch(e){toast(msg('No se pudo generar: ','Could not generate: ')+e.message,true);}finally{b.disabled=false;b.textContent=msg('Generar / actualizar borrador','Generate / update draft');}}
  async function reviewSection(key,b){try{await ensureStudy();await saveStudy();b.disabled=true;b.textContent=msg('Revisando…','Reviewing…');const role=q('#chat-role')?.value||'adversarial';const r=await api('/api/science?op=study_review',{method:'POST',body:JSON.stringify({study_id:study.study_id,section_key:key,agent_role:role,language:lang()})});reviews=[r.review,...reviews];renderStudy();}catch(e){toast(msg('Falló la revisión: ','Review failed: ')+e.message,true);}finally{b.disabled=false;}}
  async function sendChat(){const text=q('#study-chat')?.value.trim();if(!text)return;const b=q('#study-send');b.disabled=true;try{await ensureStudy();await api('/api/science?op=study_chat',{method:'POST',body:JSON.stringify({study_id:study.study_id,message:text,agent_role:q('#chat-role').value,language:lang()})});q('#study-chat').value='';await loadStudy();}catch(e){toast(msg('No se pudo enviar: ','Could not send: ')+e.message,true);}finally{b.disabled=false;}}

  function setupMap(){
    const nav=q('.sidebar nav');if(nav&&!q('[data-view="map"]')){const b=document.createElement('button');b.className='nav';b.dataset.view='map';b.textContent=msg('Mapa científico','Scientific map');const p=q('[data-view="protocol"]');nav.insertBefore(b,p);b.onclick=()=>setView('map');}
    if(q('#view-map'))return;const sec=document.createElement('section');sec.id='view-map';sec.className='view';sec.innerHTML=`<div id="map-folder-context" class="folder-context"></div><article class="card"><div class="studio-actions"><button id="map-build" class="primary">${escx(msg('Construir mapa','Build map'))}</button><button id="map-contr" class="secondary">${escx(msg('Analizar contradicciones','Analyze contradictions'))}</button><input id="map-question" placeholder="${escx(msg('Pregunta para hipótesis','Question for hypotheses'))}"><button id="map-hyp" class="secondary">${escx(msg('Generar hipótesis','Generate hypotheses'))}</button></div></article><div id="map-metrics" class="map-metrics"></div><div class="grid two"><article class="card"><h2>Claims / evidence</h2><div id="map-nodes" class="map-list"></div></article><article class="card"><h2>${escx(msg('Contradicciones','Contradictions'))}</h2><div id="map-contradictions" class="map-list"></div></article></div><article class="card"><h2>${escx(msg('Hipótesis competidoras','Competing hypotheses'))}</h2><div id="map-hypotheses" class="map-list"></div></article>`;q('#view-protocol')?.parentNode?.insertBefore(sec,q('#view-protocol'));q('#map-build').onclick=buildMap;q('#map-contr').onclick=analyzeContradictions;q('#map-hyp').onclick=generateHypotheses;
  }
  async function loadMap(){const f=folder();if(!f){graph=null;graphNodes=[];contradictions=[];competitions=[];renderMap();return;}const id=encodeURIComponent(f.folder_id);const r=await Promise.allSettled([api(`/api/science?op=graph_summary&folder_id=${id}`),api(`/api/science?op=graph_nodes&folder_id=${id}&limit=5000`),api(`/api/science?op=contradictions&folder_id=${id}`),api(`/api/science?op=hypotheses&folder_id=${id}`)]);graph=r[0].status==='fulfilled'?r[0].value:null;graphNodes=r[1].status==='fulfilled'?(r[1].value.nodes||[]):[];contradictions=r[2].status==='fulfilled'?(r[2].value.contradictions||[]):[];competitions=r[3].status==='fulfilled'?(r[3].value.competitions||[]):[];renderMap();renderWorkflow();}
  function renderMap(){const f=folder();if(q('#map-folder-context'))q('#map-folder-context').textContent=f?`${msg('Carpeta activa','Active folder')}: ${f.name}`:msg('Selecciona una carpeta.','Select a folder.');const t=graph?.node_types||{},metrics=[['papers',t.paper||0],['claims',t.claim||0],['evidence',t.evidence||0],['models',t.model||0],['contradictions',graph?.contradictions||0],['hypotheses',graph?.candidate_hypotheses||0]];if(q('#map-metrics'))q('#map-metrics').innerHTML=metrics.map(x=>`<div class="map-metric"><strong>${x[1]}</strong><span>${x[0]}</span></div>`).join('');const nodes=graphNodes.filter(n=>['claim','evidence'].includes(n.node_type)).slice(0,80);if(q('#map-nodes'))q('#map-nodes').innerHTML=nodes.map(n=>`<div class="map-card"><strong>${escx(n.label)}</strong><br><small>${escx(n.node_type)} · ${escx(n.paper_id||'')}</small></div>`).join('')||'—';if(q('#map-contradictions'))q('#map-contradictions').innerHTML=contradictions.map(c=>`<div class="map-card"><strong>${escx(c.summary)}</strong><p>${escx(c.possible_explanation||'')}</p></div>`).join('')||'—';const hs=competitions.flatMap(c=>c.hypotheses||[]);if(q('#map-hypotheses'))q('#map-hypotheses').innerHTML=hs.map(h=>`<div class="map-card"><strong>${escx(h.statement)}</strong><p>${escx(h.mechanism||'')}</p></div>`).join('')||'—';}
  async function buildMap(){const f=folder();if(!f)return;try{await api('/api/science?op=build_graph',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,full_text_only:true})});await loadMap();toast(msg('Mapa actualizado.','Map updated.'));}catch(e){toast(e.message,true);}}
  async function analyzeContradictions(){const f=folder();if(!f)return;try{await api('/api/science?op=detect_contradictions',{method:'POST',body:JSON.stringify({folder_id:f.folder_id})});await loadMap();}catch(e){toast(e.message,true);}}
  async function generateHypotheses(){const f=folder();if(!f)return;const question=q('#map-question')?.value.trim()||study?.research_question||state.session?.question;if(!question)return toast(msg('Escribe una pregunta.','Enter a question.'),true);try{await api('/api/science?op=generate_hypotheses',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,question})});await loadMap();}catch(e){toast(e.message,true);}}

  if(base.setView){setView=function(name){stripDynamicI18n();base.setView(name);if(name==='study'){q('#page-title').textContent=msg('Estudio colaborativo','Collaborative study');loadStudy().catch(()=>{});}if(name==='map'){q('#page-title').textContent=msg('Mapa científico','Scientific map');loadMap().catch(()=>{});}if(name==='literature')refreshFolderJobs().catch(()=>{});};}

  function boot(){stripDynamicI18n();injectStyles();decorateAdvancedNav();setupMap();setupStudy();setupWorkflow();bindAnalysisButtons();setTimeout(async()=>{stripDynamicI18n();await loadFolders?.().catch(()=>{});await refreshFolderJobs().catch(()=>{});await loadStudy().catch(()=>{});await loadMap().catch(()=>{});renderResearchResultsV09();renderWorkflow();},500);}
  document.addEventListener('scibrain:languagechange',()=>{stripDynamicI18n();decorateAdvancedNav();renderResearchResultsV09();renderStudy();renderMap();renderWorkflow();});
  if(document.readyState==='loading')window.addEventListener('DOMContentLoaded',boot);else boot();
})();
