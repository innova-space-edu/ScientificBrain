(() => {
  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const h = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const folder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' && toast(text, bad);

  const sections = [
    ['abstract', 'Abstract'],
    ['state_of_art', tr('Estado del arte','State of the art')],
    ['research_question', tr('Pregunta de investigación','Research question')],
    ['objectives', tr('Objetivos','Objectives')],
    ['hypotheses', tr('Hipótesis y predicciones','Hypotheses and predictions')],
    ['development', tr('Desarrollo científico','Scientific development')],
    ['analysis', tr('Análisis de evidencia','Evidence analysis')],
    ['critical_analysis', tr('Análisis crítico','Critical analysis')],
    ['novelty', tr('Novedad y brecha','Novelty and gap')],
    ['future_work', tr('Trabajo futuro','Future work')],
    ['conclusion', tr('Conclusión','Conclusion')],
  ];

  let workspace = null;
  let activeSection = null;
  let activePaper = null;
  let autoBusy = false;
  let autoTimer = null;
  let baseLoadLibrary = null;

  function styles() {
    if (q('#v11-research-style')) return;
    const s = document.createElement('style');
    s.id = 'v11-research-style';
    s.textContent = `
      .v11-intro{padding:16px;border:1px solid #b2ccff;background:#eff8ff;border-radius:14px;margin-bottom:14px}.v11-intro strong{font-size:14px}.v11-intro p{font-size:12px;line-height:1.5;margin:5px 0 0;color:#344054}
      .v11-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.v11-full{grid-column:1/-1}.v11-card{border:1px solid #e4e7ec;border-radius:13px;padding:14px;background:#fff}.v11-card h2,.v11-card h3{margin:0}.v11-card label{display:block;font-size:11px;color:#475467;margin-top:10px}.v11-card input,.v11-card textarea,.v11-card select{width:100%;margin-top:5px}.v11-card textarea{min-height:92px;resize:vertical}.v11-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
      .v11-status{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.v11-status span{font-size:10px;border:1px solid #e4e7ec;border-radius:999px;padding:4px 8px;background:#f9fafb}.v11-status .ok{background:#ecfdf3;color:#067647;border-color:#abefc6}
      .v11-assessment{display:grid;gap:9px}.v11-assess-item{border:1px solid #e4e7ec;border-radius:11px;padding:11px}.v11-assess-item strong{font-size:12px}.v11-assess-item p{font-size:11px;color:#475467;margin:5px 0}.v11-assess-item .tag{display:inline-flex;font-size:10px;padding:3px 7px;border-radius:999px;background:#f2f4f7}.v11-assess-item .open{background:#ecfdf3;color:#067647}.v11-assess-item .contested{background:#fff4e5;color:#b54708}
      .v11-sections{display:grid;gap:12px;margin-top:14px}.v11-section{border:1px solid #e4e7ec;border-radius:13px;padding:14px;background:#fff}.v11-section-head{display:flex;align-items:center;justify-content:space-between;gap:8px}.v11-section-head .meta{font-size:10px;color:#667085}.v11-section textarea{width:100%;min-height:190px;margin-top:10px;line-height:1.5;resize:vertical}.v11-section[data-k="development"] textarea,.v11-section[data-k="analysis"] textarea,.v11-section[data-k="critical_analysis"] textarea{min-height:280px}.v11-refs{font-size:10px;color:#667085;margin-top:7px}.v11-ref-list{display:grid;gap:8px}.v11-ref{font-size:11px;line-height:1.45;padding:9px;border-bottom:1px solid #f2f4f7}.v11-ref:last-child{border-bottom:0}.v11-ref small{display:block;color:#667085;margin-top:2px}
      .v11-modal{position:fixed;inset:0;background:rgba(16,24,40,.55);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px}.v11-modal.hidden{display:none}.v11-modal-panel{width:min(920px,96vw);max-height:90vh;overflow:auto;background:#fff;border-radius:16px;box-shadow:0 24px 70px rgba(0,0,0,.25);padding:16px}.v11-modal-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.v11-chat{display:grid;gap:8px;max-height:48vh;overflow:auto;margin:12px 0}.v11-msg{border:1px solid #e4e7ec;border-radius:10px;padding:10px;font-size:11px;white-space:pre-wrap;line-height:1.45}.v11-msg.user{background:#f5f8ff}.v11-msg.agent{background:#f9fafb}.v11-chat-compose{display:grid;grid-template-columns:220px 1fr;gap:10px}.v11-chat-compose textarea{grid-column:1/-1;min-height:110px}.v11-modal-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.v11-paper-answer{white-space:pre-wrap;font-size:12px;line-height:1.5;padding:12px;background:#f9fafb;border-radius:10px;margin-top:10px}
      .v11-auto{display:inline-flex;align-items:center;gap:6px;font-size:10px;color:#067647;margin-left:7px}.v11-dot{width:7px;height:7px;border-radius:50%;background:#12b76a}.v11-dot.busy{background:#f79009;animation:v11pulse 1s infinite}@keyframes v11pulse{50%{opacity:.35}}
      @media(max-width:850px){.v11-grid{grid-template-columns:1fr}.v11-chat-compose{grid-template-columns:1fr}.v11-full{grid-column:auto}}
    `;
    document.head.appendChild(s);
  }

  function installNavOrder() {
    const nav = q('.sidebar nav');
    const research = q('[data-view="literature"]');
    const collab = q('[data-view="collab"]');
    if (nav && research && collab) nav.insertBefore(research, collab);
  }

  function buildResearchView() {
    const view = q('#view-collab');
    if (!view || view.dataset.v11 === '1') return;
    view.dataset.v11 = '1';
    view.innerHTML = `
      <div class="v11-intro"><strong>${h(tr('Sesión científica guiada','Guided scientific session'))}</strong><p>${h(tr('Primero define con precisión qué quieres investigar. ScientificBrain contrastará tus preguntas con los papers analizados y búsquedas recientes; después construirá objetivos, hipótesis, desarrollo, análisis crítico, novedad y trabajo futuro.','First define precisely what you want to investigate. ScientificBrain will contrast your questions with the analyzed papers and recent searches, then build objectives, hypotheses, development, critical analysis, novelty and future work.'))}</p></div>
      <div class="v11-grid">
        <article class="v11-card v11-full"><div style="display:flex;justify-content:space-between;gap:10px;align-items:center"><div><h2>${h(tr('1. Definición de la investigación','1. Research definition'))}</h2><p class="muted">${h(tr('No generes el documento hasta que el problema y las preguntas estén claros.','Do not generate the document until the problem and questions are clear.'))}</p></div><span id="v11-auto-status" class="v11-auto"><span class="v11-dot"></span>${h(tr('Agentes automáticos activos','Automatic agents active'))}</span></div>
          <label>${h(tr('Tema de investigación','Research topic'))}<input id="v11-topic" placeholder="${h(tr('Ej.: Propulsión de plasma para CubeSat usando plasma focus miniaturizado','e.g. Plasma propulsion for CubeSat using a miniaturized plasma focus'))}"></label>
          <label>${h(tr('Problema científico que quieres resolver','Scientific problem to solve'))}<textarea id="v11-problem"></textarea></label>
          <label>${h(tr('Preguntas de interés — una por línea','Questions of interest — one per line'))}<textarea id="v11-questions" placeholder="${h(tr('¿Qué mecanismo controla...?\n¿Qué variable explica...?\n¿Qué falta medir para...?','What mechanism controls...?\nWhich variable explains...?\nWhat remains to be measured...?'))}"></textarea></label>
          <div class="v11-grid"><label>${h(tr('Mecanismos, variables o comparaciones prioritarias','Priority mechanisms, variables or comparisons'))}<textarea id="v11-mechanisms"></textarea></label><label>${h(tr('Alcance y restricciones','Scope and constraints'))}<textarea id="v11-scope"></textarea></label></div>
          <div class="v11-grid"><label>${h(tr('Qué crees que podría ser novedoso','What may be novel'))}<textarea id="v11-novelty"></textarea></label><label>${h(tr('Resultado que esperas obtener','Desired output'))}<textarea id="v11-output"></textarea></label></div>
          <div class="v11-status" id="v11-corpus-status"></div>
          <div class="v11-actions"><button id="v11-assess" class="primary">${h(tr('Guardar, buscar y evaluar preguntas','Save, search and assess questions'))}</button><button id="v11-generate" class="secondary">${h(tr('Generar / actualizar investigación profunda','Generate / update deep research'))}</button><button id="v11-find" class="ghost">${h(tr('Ir a Research Agent','Go to Research Agent'))}</button><button id="v11-refresh" class="ghost">${h(tr('Actualizar','Refresh'))}</button></div>
        </article>
        <article class="v11-card v11-full"><h2>${h(tr('2. Qué está resuelto y qué sigue abierto','2. What is resolved and what remains open'))}</h2><div id="v11-assessment" class="v11-assessment" style="margin-top:10px"></div></article>
      </div>
      <div id="v11-sections" class="v11-sections"></div>
      <article class="v11-card" style="margin-top:14px"><h2>${h(tr('Referencias','References'))}</h2><p class="muted">${h(tr('Las citas visibles usan nomenclatura científica numérica [1], [2], ...; los identificadores internos permanecen solo para trazabilidad.','Visible citations use standard numbered scientific notation [1], [2], ...; internal identifiers remain only for traceability.'))}</p><div id="v11-references" class="v11-ref-list"></div></article>
    `;
    q('#v11-assess').onclick = assessQuestions;
    q('#v11-generate').onclick = generateDeep;
    q('#v11-find').onclick = () => {
      const topic = q('#v11-topic')?.value?.trim();
      if (topic && q('#research-query')) q('#research-query').value = topic;
      if (typeof setView === 'function') setView('literature');
    };
    q('#v11-refresh').onclick = loadWorkspace;
  }

  function ensureModals() {
    if (!q('#v11-section-modal')) {
      const el = document.createElement('div');
      el.id = 'v11-section-modal'; el.className = 'v11-modal hidden';
      el.innerHTML = `<div class="v11-modal-panel"><div class="v11-modal-head"><div><h2 id="v11-modal-title"></h2><p class="muted">${h(tr('Debate esta sección con un agente. Al finalizar, reházala usando todo lo discutido.','Debate this section with an agent. When finished, rewrite it using the complete discussion.'))}</p></div><button id="v11-modal-close" class="ghost">×</button></div><div class="v11-chat" id="v11-modal-chat"></div><div class="v11-chat-compose"><label>${h(tr('Agente','Agent'))}<select id="v11-modal-agent"></select></label><span></span><textarea id="v11-modal-input" placeholder="${h(tr('Cuestiona una afirmación, pide evidencia, propone otra hipótesis o solicita un cambio...','Challenge a claim, request evidence, propose another hypothesis or request a change...'))}"></textarea></div><div class="v11-modal-actions"><button id="v11-modal-send" class="primary">${h(tr('Enviar','Send'))}</button><button id="v11-modal-review" class="secondary">${h(tr('Revisión crítica automática','Automatic critical review'))}</button><button id="v11-modal-rewrite" class="secondary">${h(tr('Rehacer sección con todo lo discutido','Rewrite section from full discussion'))}</button></div></div>`;
      document.body.appendChild(el);
      q('#v11-modal-close').onclick = () => el.classList.add('hidden');
      el.addEventListener('click', e => { if (e.target === el) el.classList.add('hidden'); });
      q('#v11-modal-send').onclick = sendSectionMessage;
      q('#v11-modal-review').onclick = requestSectionReview;
      q('#v11-modal-rewrite').onclick = rewriteSection;
    }
    if (!q('#v11-paper-modal')) {
      const el = document.createElement('div'); el.id='v11-paper-modal'; el.className='v11-modal hidden';
      el.innerHTML = `<div class="v11-modal-panel"><div class="v11-modal-head"><div><h2 id="v11-paper-title">ChatPaper</h2><p class="muted">${h(tr('Consulta la memoria persistente del paper. El PDF no se vuelve a analizar desde cero.','Query the persistent paper memory. The PDF is not analyzed from scratch again.'))}</p></div><button id="v11-paper-close" class="ghost">×</button></div><div id="v11-paper-memory" class="v11-status"></div><textarea id="v11-paper-question" style="width:100%;min-height:100px;margin-top:12px" placeholder="${h(tr('Pregunta sobre ecuaciones, métodos, resultados, figuras, limitaciones...','Ask about equations, methods, results, figures, limitations...'))}"></textarea><div class="v11-modal-actions"><button id="v11-paper-ask" class="primary">${h(tr('Preguntar al paper','Ask paper'))}</button></div><div id="v11-paper-answer" class="v11-paper-answer"></div></div>`;
      document.body.appendChild(el);
      q('#v11-paper-close').onclick=()=>el.classList.add('hidden');
      el.addEventListener('click',e=>{if(e.target===el)el.classList.add('hidden')});
      q('#v11-paper-ask').onclick=askPaper;
    }
  }

  function briefFromForm() {
    return {
      topic: q('#v11-topic')?.value?.trim() || '',
      problem_statement: q('#v11-problem')?.value?.trim() || '',
      questions: (q('#v11-questions')?.value || '').split(/\n+/).map(x=>x.trim()).filter(Boolean),
      mechanisms_or_comparisons: q('#v11-mechanisms')?.value?.trim() || '',
      scope_constraints: q('#v11-scope')?.value?.trim() || '',
      expected_novelty: q('#v11-novelty')?.value?.trim() || '',
      desired_output: q('#v11-output')?.value?.trim() || '',
    };
  }

  function fillBrief(brief={}) {
    const set=(id,v)=>{const el=q(id);if(el && document.activeElement!==el)el.value=v||''};
    set('#v11-topic',brief.topic||workspace?.document?.topic||'');
    set('#v11-problem',brief.problem_statement);
    set('#v11-questions',(brief.questions||[]).join('\n'));
    set('#v11-mechanisms',brief.mechanisms_or_comparisons);
    set('#v11-scope',brief.scope_constraints);
    set('#v11-novelty',brief.expected_novelty);
    set('#v11-output',brief.desired_output);
  }

  function renderWorkspace() {
    if (!workspace) return;
    const doc = workspace.document || {};
    fillBrief(doc.research_brief || {topic:doc.topic});
    const c = workspace.corpus || {};
    const status=q('#v11-corpus-status');
    if(status) status.innerHTML=`<span>${c.total||0} ${h(tr('papers','papers'))}</span><span class="ok">${c.full_text_reviewed||0} ${h(tr('analizados completos','full-text reviewed'))}</span><span>${c.readable_now||0} ${h(tr('legibles','readable'))}</span><span>${(workspace.recent_searches||[]).length} ${h(tr('búsquedas recientes','recent searches'))}</span>`;
    renderAssessment(doc.novelty_assessment || {});
    renderSections(doc.sections || {});
    renderReferences((doc.evidence_manifest || {}).sources || []);
    renderModalChat();
  }

  function renderAssessment(a) {
    const box=q('#v11-assessment'); if(!box)return;
    const rows=a.questions||[];
    if(!rows.length){box.innerHTML=`<div class="empty">${h(tr('Define tus preguntas y presiona “Guardar, buscar y evaluar preguntas”.','Define your questions and press “Save, search and assess questions”.'))}</div>`;return;}
    box.innerHTML=(a.overall_assessment?`<div class="v11-assess-item"><strong>${h(tr('Evaluación general','Overall assessment'))}</strong><p>${h(a.overall_assessment)}</p></div>`:'')+rows.map(x=>`<div class="v11-assess-item"><strong>${h(x.question||'')}</strong><div class="tag ${h(x.status||'')}">${h(x.status||'')}</div><p><b>${h(tr('Conocido:','Known:'))}</b> ${h(x.what_is_known||'')}</p><p><b>${h(tr('Falta:','Missing:'))}</b> ${h(x.what_is_missing||'')}</p><p><b>${h(tr('Evidencia decisiva:','Decisive evidence:'))}</b> ${h(x.decisive_evidence_needed||'')}</p><p><b>${h(tr('Oportunidad de novedad:','Novelty opportunity:'))}</b> ${h(x.novelty_opportunity||'')}</p><div class="v11-refs">${(x.refs||[]).map(n=>`[${h(n)}]`).join(' ')}</div></div>`).join('');
  }

  function sectionLabel(k){return (sections.find(x=>x[0]===k)||[k,k])[1]}
  function renderSections(rows) {
    const box=q('#v11-sections'); if(!box)return;
    box.innerHTML=sections.map(([k,label])=>{const x=rows[k]||{};const refs=(x.refs||[]).map(n=>`[${n}]`).join(' ');const meta=x.user_edited?tr('editado por usuario','user edited'):x.discussion_rewritten?tr('reescrito desde discusión','rewritten from discussion'):tr('síntesis IA','AI synthesis');return `<article class="v11-section" data-k="${h(k)}"><div class="v11-section-head"><div><h3>${h(label)}</h3><div class="meta">${h(meta)}</div></div><button class="secondary v11-discuss" data-k="${h(k)}">${h(tr('Discutir con agente','Discuss with agent'))}</button></div><textarea data-v11-section="${h(k)}">${h(x.text||'')}</textarea><div class="v11-refs">${h(tr('Citas','Citations'))}: ${refs||'—'}</div><div class="v11-actions"><button class="ghost v11-save" data-k="${h(k)}">${h(tr('Guardar cambios','Save changes'))}</button><button class="ghost v11-rewrite" data-k="${h(k)}">${h(tr('Rehacer con discusión','Rewrite from discussion'))}</button></div></article>`}).join('');
    qa('.v11-discuss').forEach(b=>b.onclick=()=>openSectionChat(b.dataset.k));
    qa('.v11-save').forEach(b=>b.onclick=()=>saveSection(b.dataset.k,b));
    qa('.v11-rewrite').forEach(b=>b.onclick=()=>{activeSection=b.dataset.k;rewriteSection(b)});
  }

  function renderReferences(sources) {
    const box=q('#v11-references'); if(!box)return;
    const sorted=[...sources].sort((a,b)=>(a.citation_number||9999)-(b.citation_number||9999));
    box.innerHTML=sorted.length?sorted.map(s=>`<div class="v11-ref"><strong>${h(s.reference||`[${s.citation_number}] ${s.title||''}`)}</strong><small>${h(s.review_depth||'')} · ${h(s.access_label||'')}</small></div>`).join(''):`<div class="empty">${h(tr('Aún no hay referencias analizadas.','No analyzed references yet.'))}</div>`;
  }

  async function collab(op,payload={}) {
    return api('/api/collaboration?op='+encodeURIComponent(op),{method:'POST',body:JSON.stringify({folder_id:folder()?.folder_id,language:lang(),...payload})});
  }

  async function loadWorkspace() {
    const f=folder(); if(!f)return;
    try{workspace=await api('/api/collaboration?op=research_workspace&folder_id='+encodeURIComponent(f.folder_id));renderWorkspace();}
    catch(e){notify(tr('No se pudo cargar la sesión científica: ','Could not load scientific session: ')+e.message,true)}
  }

  async function saveBrief() {
    const brief=briefFromForm();
    if(!brief.topic)throw new Error(tr('Debes indicar el tema de investigación.','Research topic is required.'));
    await collab('save_brief',{brief});
    return brief;
  }

  async function assessQuestions() {
    const b=q('#v11-assess'); b.disabled=true; const original=b.textContent;
    try{
      const brief=await saveBrief();
      const questions=brief.questions.slice(0,5);
      if(!questions.length)throw new Error(tr('Agrega al menos una pregunta de investigación.','Add at least one research question.'));
      for(let i=0;i<questions.length;i++){
        b.textContent=`${tr('Buscando evidencia','Searching evidence')} ${i+1}/${questions.length}`;
        try{await api('/api/research_search',{method:'POST',body:JSON.stringify({folder_id:folder().folder_id,query:`${brief.topic}: ${questions[i]}`,max_results:12,include_web:true,resolve_open_access:true})});}catch(e){console.warn('question search',e)}
      }
      b.textContent=tr('Evaluando brechas y novedad…','Assessing gaps and novelty…');
      await collab('assess_brief');
      await loadWorkspace();
      notify(tr('Preguntas contrastadas con el corpus y búsquedas recientes.','Questions contrasted with corpus and recent searches.'));
    }catch(e){notify(e.message,true)}finally{b.disabled=false;b.textContent=original}
  }

  async function generateDeep(button=q('#v11-generate')) {
    const original=button?.textContent; if(button){button.disabled=true;button.textContent=tr('Generando síntesis profunda…','Generating deep synthesis…')}
    try{const brief=await saveBrief();await collab('generate_draft',{topic:brief.topic,preserve_user_edits:true});await loadWorkspace();notify(tr('Investigación profunda actualizada.','Deep research updated.'));}
    catch(e){notify(tr('No se pudo generar: ','Could not generate: ')+e.message,true)}finally{if(button){button.disabled=false;button.textContent=original}}
  }

  async function saveSection(k,b){const ta=q(`textarea[data-v11-section="${k}"]`);if(!ta)return;const old=b.textContent;b.disabled=true;try{await collab('save_section',{section_key:k,content:ta.value});await loadWorkspace();notify(tr('Sección guardada.','Section saved.'));}catch(e){notify(e.message,true)}finally{b.disabled=false;b.textContent=old}}

  function renderModalChat(){if(!activeSection||!workspace)return;const roles=workspace.agent_roles||[];const sel=q('#v11-modal-agent');if(sel&&sel.options.length===0)sel.innerHTML=roles.map(r=>`<option value="${h(r.id)}">${h(r.label)}</option>`).join('');const messages=(workspace.messages||[]).filter(m=>m.section_key===activeSection);const box=q('#v11-modal-chat');if(box)box.innerHTML=messages.length?messages.map(m=>`<div class="v11-msg ${h(m.message_role)}"><b>${h(m.message_role==='user'?tr('Usuario','User'):(m.agent_id||tr('Agente','Agent')))}</b><br>${h(m.content||'')}</div>`).join(''):`<div class="empty">${h(tr('Aún no hay discusión para esta sección.','No discussion for this section yet.'))}</div>`;if(box)box.scrollTop=box.scrollHeight}
  async function openSectionChat(k){activeSection=k;await loadWorkspace();q('#v11-modal-title').textContent=sectionLabel(k);q('#v11-section-modal').classList.remove('hidden');renderModalChat()}
  async function sendSectionMessage(){const ta=q('#v11-modal-input'),text=ta?.value?.trim();if(!activeSection||!text)return;const b=q('#v11-modal-send'),old=b.textContent;b.disabled=true;b.textContent=tr('Pensando…','Thinking…');try{await collab('discuss',{section_key:activeSection,agent_id:q('#v11-modal-agent')?.value||'critical_reviewer',message:text});ta.value='';await loadWorkspace();renderModalChat()}catch(e){notify(e.message,true)}finally{b.disabled=false;b.textContent=old}}
  async function requestSectionReview(){if(!activeSection)return;const b=q('#v11-modal-review'),old=b.textContent;b.disabled=true;try{await collab('review_section',{section_key:activeSection,agent_id:q('#v11-modal-agent')?.value||'critical_reviewer'});await loadWorkspace();renderModalChat()}catch(e){notify(e.message,true)}finally{b.disabled=false;b.textContent=old}}
  async function rewriteSection(button=q('#v11-modal-rewrite')){if(!activeSection)return;const old=button?.textContent;if(button){button.disabled=true;button.textContent=tr('Reescribiendo…','Rewriting…')}try{await collab('rewrite_section',{section_key:activeSection});await loadWorkspace();renderModalChat();notify(tr('Sección rehecha usando toda la discusión y la evidencia.','Section rewritten using the full discussion and evidence.'));}catch(e){notify(e.message,true)}finally{if(button){button.disabled=false;button.textContent=old}}}

  async function fetchJobs(){const f=folder();if(!f)return[];const r=await api('/api/jobs?folder_id='+encodeURIComponent(f.folder_id)+'&limit=500');state.jobs=r.jobs||[];return state.jobs}
  async function ensureJob(p){await fetchJobs();let job=(state.jobs||[]).find(j=>j.job_type==='review_paper'&&j.payload?.paper_id===p.canonical_id&&j.status!=='completed');if(job)return job;return api('/api/jobs',{method:'POST',body:JSON.stringify({folder_id:folder().folder_id,session_id:state.session?.folder_id===folder().folder_id?state.session.session_id:null,job_type:'review_paper',payload:{paper_id:p.canonical_id,pdf_url:p.pdf_url||null}})})}
  async function runResumable(job){let requestFailures=0;for(let i=0;i<400;i++){let current;try{current=await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:job.job_id})});requestFailures=0}catch(e){requestFailures++;if(requestFailures<=2){await sleep(1200*requestFailures);continue}throw e}if(current.status==='completed')return current;if(current.status==='failed')throw new Error(current.last_error||tr('El análisis falló','Analysis failed'));await sleep(180)}throw new Error(tr('Se alcanzó el límite de etapas; el checkpoint quedó guardado.','Step limit reached; checkpoint was saved.'))}
  function setAutoBusy(busy){const dot=q('#v11-auto-status .v11-dot');if(dot)dot.classList.toggle('busy',busy);const box=q('#v11-auto-status');if(box)box.lastChild.textContent=busy?tr(' Analizando papers automáticamente…',' Analyzing papers automatically…'):tr(' Agentes automáticos activos',' Automatic agents active')}

  async function autoAnalyzePending(regenerate=true){if(autoBusy||!folder()||!accessToken?.())return;const candidates=(state.library||[]).filter(p=>p.review_depth!=='full_text_reviewed'&&(p.system_can_read||p.storage_path||p.pdf_url));if(!candidates.length)return;autoBusy=true;setAutoBusy(true);let completed=0;try{for(const p of candidates){try{const job=await ensureJob(p);await runResumable(job);completed++;if(baseLoadLibrary)await baseLoadLibrary();}catch(e){console.error('auto paper analysis',p.canonical_id,e);notify(`${tr('Análisis automático detenido para','Automatic analysis stopped for')} ${p.title||p.canonical_id}: ${e.message}`,true);break}}if(completed&&regenerate){await loadWorkspace();const doc=workspace?.document;if(doc?.topic){const brief=doc.research_brief||{};if((brief.questions||[]).length){try{await collab('assess_brief')}catch(e){console.warn('auto reassess',e)}}try{await collab('generate_draft',{topic:doc.topic,preserve_user_edits:true});await loadWorkspace()}catch(e){console.warn('auto regenerate',e)}}}if(completed)notify(`${completed} ${tr('paper(s) analizado(s) automáticamente y memoria actualizada.','paper(s) automatically analyzed; memory updated.')}`)}finally{autoBusy=false;setAutoBusy(false);enhancePaperRows()}}
  function scheduleAuto(){clearTimeout(autoTimer);autoTimer=setTimeout(()=>autoAnalyzePending(true).catch(e=>console.error(e)),650)}

  function enhancePaperRows(){qa('#paper-list .paper-row').forEach(row=>{if(row.querySelector('.v11-chat-paper'))return;const item=row.querySelector('.delete-paper')?.dataset.item,p=(state.library||[]).find(x=>x.item_id===item);if(!p)return;const actions=row.querySelector('.paper-actions')||row;const b=document.createElement('button');b.className='ghost v11-chat-paper';b.textContent='Chat paper';b.onclick=()=>openPaperChat(p);actions.appendChild(b)})}
  async function openPaperChat(p){activePaper=p;q('#v11-paper-title').textContent=`ChatPaper · ${p.title||p.canonical_id}`;q('#v11-paper-answer').textContent='';q('#v11-paper-question').value='';q('#v11-paper-modal').classList.remove('hidden');try{const s=await api(`/api/paper?folder_id=${encodeURIComponent(folder().folder_id)}&paper_id=${encodeURIComponent(p.canonical_id)}`);q('#v11-paper-memory').innerHTML=s.cached?`<span class="ok">${h(tr('Memoria persistente activa','Persistent memory active'))}</span><span>${h(s.page_count||0)} ${h(tr('páginas','pages'))}</span><span>${h(s.word_count||0)} ${h(tr('palabras','words'))}</span>`:`<span>${h(tr('La memoria se creará con la primera consulta/análisis.','Memory will be created on first query/analysis.'))}</span>`}catch(e){q('#v11-paper-memory').textContent=e.message}}
  async function askPaper(){if(!activePaper)return;const question=q('#v11-paper-question')?.value?.trim();if(!question)return;const b=q('#v11-paper-ask'),old=b.textContent;b.disabled=true;b.textContent=tr('Consultando memoria…','Querying memory…');try{const r=await api('/api/paper?op=ask',{method:'POST',body:JSON.stringify({folder_id:folder().folder_id,paper_id:activePaper.canonical_id,pdf_url:activePaper.pdf_url||null,question})});q('#v11-paper-answer').textContent=r.answer||'';q('#v11-paper-memory').innerHTML=`<span class="ok">${h(tr('Memoria persistente activa','Persistent memory active'))}</span><span>${h((r.pages_used||[]).length)} ${h(tr('páginas usadas','pages used'))}</span>`}catch(e){q('#v11-paper-answer').textContent=e.message}finally{b.disabled=false;b.textContent=old}}

  function installAutomation(){if(typeof loadLibrary==='function'&&!window.__sbV11LoadWrapped){window.__sbV11LoadWrapped=true;baseLoadLibrary=loadLibrary;loadLibrary=async function(...args){const r=await baseLoadLibrary.apply(this,args);enhancePaperRows();scheduleAuto();return r}}else if(typeof loadLibrary==='function')baseLoadLibrary=loadLibrary;const upload=q('#upload-papers');if(upload&&typeof uploadPapers==='function'&&!upload.dataset.v11){upload.dataset.v11='1';const previous=uploadPapers;upload.onclick=async()=>{await previous();scheduleAuto()}}enhancePaperRows();scheduleAuto()}

  function bindNavigation(){document.addEventListener('click',e=>{const nav=e.target.closest('[data-view="collab"]');if(nav)setTimeout(loadWorkspace,80);const item=e.target.closest('.folder-item');if(item)setTimeout(()=>{loadWorkspace();enhancePaperRows();scheduleAuto()},250)});document.addEventListener('scibrain:languagechange',()=>{buildResearchView();renderWorkspace()})}

  function install(){styles();installNavOrder();buildResearchView();ensureModals();installAutomation();bindNavigation();loadWorkspace().catch(()=>{})}
  if(document.readyState==='loading')window.addEventListener('DOMContentLoaded',install);else install();
})();
