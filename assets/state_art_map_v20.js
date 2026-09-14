(() => {
  if (window.__SB_V20_STATE_ART_MAP__) return;
  window.__SB_V20_STATE_ART_MAP__ = true;

  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const folder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad ? 'error' : 'log'](text);

  let matrix = null;
  let matrixFolder = null;
  let graph = {summary:null,nodes:[],edges:[],contradictions:[],competitions:[]};
  let graphFolder = null;
  let matrixBusy = false;
  let graphBusy = false;
  let baseSetView = null;
  let baseSelectFolder = null;

  function styles() {
    if (q('#v20-style')) return;
    const style = document.createElement('style');
    style.id = 'v20-style';
    style.textContent = `
      .v20-card{border:1px solid #e4e7ec;border-radius:13px;padding:14px;background:#fff;margin-top:14px}.v20-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}.v20-actions{display:flex;gap:7px;flex-wrap:wrap;align-items:center}.v20-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.v20-badge{font-size:9px;padding:4px 7px;border-radius:999px;background:#f2f4f7;color:#344054}.v20-badge.ok{background:#ecfdf3;color:#067647}.v20-badge.warn{background:#fffaeb;color:#93370d}.v20-table-wrap{overflow:auto;margin-top:10px;border:1px solid #e4e7ec;border-radius:10px;max-height:58vh}.v20-table{border-collapse:collapse;width:max-content;min-width:100%;font-size:10px}.v20-table th{position:sticky;top:0;background:#f9fafb;z-index:2;text-align:left;padding:8px;border-bottom:1px solid #d0d5dd;min-width:150px}.v20-table th:first-child{left:0;z-index:3;min-width:240px}.v20-table td{padding:8px;border-bottom:1px solid #eaecf0;vertical-align:top;max-width:280px;min-width:170px}.v20-table td:first-child{position:sticky;left:0;background:#fff;z-index:1;min-width:240px}.v20-cell{display:grid;gap:3px}.v20-cell span{display:block;line-height:1.35}.v20-paper-title{font-weight:650;color:#101828}.v20-mini{font-size:9px;color:#667085;margin-top:3px}.v20-detail{margin-top:10px;padding:12px;background:#f8fafc;border:1px solid #e4e7ec;border-radius:10px;font-size:11px;line-height:1.5}.v20-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.v20-detail h4{margin:0 0 5px}.v20-list{margin:0;padding-left:17px}.v20-search{min-width:240px}.v20-recurring{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:10px}.v20-recurring>div{border:1px solid #e4e7ec;border-radius:9px;padding:9px}.v20-recurring strong{font-size:10px}.v20-recurring p{font-size:10px;color:#475467;margin:5px 0 0;line-height:1.4}
      .v20-map-shell{display:grid;gap:12px}.v20-map-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.v20-map-toolbar input,.v20-map-toolbar select{width:auto;min-width:180px}.v20-map-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:12px}.v20-network{overflow:auto;border:1px solid #e4e7ec;border-radius:12px;background:#fcfcfd;min-height:520px}.v20-network svg{display:block;min-width:930px}.v20-node{cursor:pointer}.v20-node rect{stroke:#98a2b3;stroke-width:1}.v20-node text{font-size:9px;pointer-events:none}.v20-edge{stroke:#d0d5dd;stroke-width:1;opacity:.75}.v20-edge.supported_by{stroke:#12b76a}.v20-edge.contradicted_by{stroke:#f04438}.v20-node.paper rect{fill:#eff8ff}.v20-node.claim rect{fill:#f9f5ff}.v20-node.evidence rect{fill:#ecfdf3}.v20-node.other rect{fill:#fff7ed}.v20-inspector{border:1px solid #e4e7ec;border-radius:12px;padding:12px;background:#fff;max-height:680px;overflow:auto}.v20-inspector pre{white-space:pre-wrap;font-size:10px}.v20-section{border-top:1px solid #eaecf0;padding-top:10px;margin-top:10px}.v20-contradiction{padding:9px;border:1px solid #fedf89;background:#fffaeb;border-radius:9px;margin-top:7px;font-size:10px;line-height:1.4}.v20-hypothesis{padding:9px;border:1px solid #b2ccff;background:#f5f8ff;border-radius:9px;margin-top:7px;font-size:10px;line-height:1.4}.v20-empty{padding:14px;color:#667085;font-size:11px}.v20-map-question{flex:1;min-width:260px}
      @media(max-width:980px){.v20-detail-grid,.v20-recurring,.v20-map-grid{grid-template-columns:1fr}.v20-search{width:100%}.v20-inspector{max-height:none}}
    `;
    document.head.appendChild(style);
  }

  function shortList(values, limit=4) {
    const rows = (values || []).map(value => typeof value === 'string' ? value : (value?.text || value?.name || value?.claim || value?.label || '')).filter(Boolean);
    if (!rows.length) return '<span>—</span>';
    return rows.slice(0, limit).map(value => `<span>${esc(value)}</span>`).join('') + (rows.length > limit ? `<span class="v20-mini">+${rows.length-limit}</span>` : '');
  }

  function ensureMatrixCard() {
    const view = q('#view-collab');
    if (!view || q('#v20-matrix-card')) return;
    const card = document.createElement('article');
    card.id = 'v20-matrix-card'; card.className = 'v20-card v11-full';
    card.innerHTML = `
      <div class="v20-head"><div><h2>${esc(tr('Matriz estructurada del estado del arte','Structured state-of-the-art matrix'))}</h2><p class="muted">${esc(tr('Organiza lo extraído del full text por paper: régimen/modelo, variables, métodos, resultados, incertidumbre, limitaciones y trazabilidad. Las coincidencias entre papers son dimensiones compartidas, no consenso automático.','Organizes full-text extraction by paper: regime/model, variables, methods, results, uncertainty, limitations and provenance. Recurrence across papers is a shared dimension, not automatic consensus.'))}</p></div><div class="v20-actions"><input id="v20-matrix-search" class="v20-search" placeholder="${esc(tr('Filtrar papers o contenido…','Filter papers or content…'))}"><button id="v20-matrix-refresh" class="ghost">${esc(tr('Actualizar matriz','Refresh matrix'))}</button></div></div>
      <div id="v20-matrix-badges" class="v20-badges"></div><div id="v20-recurring" class="v20-recurring"></div><div id="v20-matrix-body" class="v20-table-wrap"><div class="v20-empty">${esc(tr('Cargando matriz…','Loading matrix…'))}</div></div><div id="v20-matrix-detail"></div>`;
    const assistant = q('#v18-assistant-card');
    if (assistant?.parentNode) assistant.parentNode.insertBefore(card, assistant); else view.appendChild(card);
    q('#v20-matrix-refresh').onclick = () => loadMatrix(true);
    q('#v20-matrix-search').addEventListener('input', renderMatrix);
  }

  async function loadMatrix(force=false) {
    const f = folder();
    if (!f?.folder_id || matrixBusy) return null;
    if (!force && matrixFolder === f.folder_id && matrix) return matrix;
    matrixBusy = true;
    try {
      const result = await api('/api/collaboration?op=research_workspace&folder_id=' + encodeURIComponent(f.folder_id));
      matrix = result.literature_matrix || {rows:[],coverage:{},recurring_dimensions:{}};
      matrixFolder = f.folder_id;
      renderMatrix();
      return matrix;
    } catch (error) {
      const body=q('#v20-matrix-body'); if(body) body.innerHTML=`<div class="v20-empty">${esc(error.message||String(error))}</div>`;
      return null;
    } finally { matrixBusy=false; }
  }

  function renderRecurring() {
    const box=q('#v20-recurring'); if(!box)return;
    const recurring=matrix?.recurring_dimensions||{};
    const groups=[['mechanisms',tr('Modelos / mecanismos compartidos','Shared models / mechanisms')],['variables',tr('Variables compartidas','Shared variables')],['diagnostics',tr('Diagnósticos compartidos','Shared diagnostics')],['regimes',tr('Regímenes compartidos','Shared regimes')],['equations',tr('Ecuaciones compartidas','Shared equations')]];
    const visible=groups.filter(([key])=>(recurring[key]||[]).length);
    box.innerHTML=visible.slice(0,3).map(([key,label])=>`<div><strong>${esc(label)}</strong><p>${(recurring[key]||[]).slice(0,6).map(x=>`${esc(x.label)} (${esc(x.paper_count)})`).join(' · ')}</p></div>`).join('');
    box.style.display=visible.length?'grid':'none';
  }

  function renderMatrix() {
    if (!matrix) return;
    const coverage=matrix.coverage||{}; const badges=q('#v20-matrix-badges');
    if(badges) badges.innerHTML=`<span class="v20-badge ok">${esc(coverage.full_text_papers||0)} full-text</span><span class="v20-badge">${esc(coverage.evidence_records||0)} evidencia</span><span class="v20-badge">${esc(coverage.claims||0)} claims</span><span class="v20-badge ${coverage.papers_with_uncertainty?'ok':'warn'}">${esc(coverage.papers_with_uncertainty||0)} ${esc(tr('con incertidumbre','with uncertainty'))}</span><span class="v20-badge ${coverage.papers_with_limitations?'ok':'warn'}">${esc(coverage.papers_with_limitations||0)} ${esc(tr('con limitaciones','with limitations'))}</span>`;
    renderRecurring();
    const term=(q('#v20-matrix-search')?.value||'').trim().toLowerCase();
    let rows=matrix.rows||[];
    if(term) rows=rows.filter(row=>JSON.stringify(row).toLowerCase().includes(term));
    const body=q('#v20-matrix-body'); if(!body)return;
    if(!rows.length){body.innerHTML=`<div class="v20-empty">${esc(tr('No hay papers full-text analizados que coincidan con el filtro.','No analyzed full-text papers match this filter.'))}</div>`;return;}
    body.innerHTML=`<table class="v20-table"><thead><tr><th>${esc(tr('Paper','Paper'))}</th><th>${esc(tr('Régimen / modelo','Regime / model'))}</th><th>${esc(tr('Variables / parámetros','Variables / parameters'))}</th><th>${esc(tr('Método / diagnóstico','Method / diagnostic'))}</th><th>${esc(tr('Resultados extraídos','Extracted results'))}</th><th>${esc(tr('Incertidumbre','Uncertainty'))}</th><th>${esc(tr('Limitaciones','Limitations'))}</th><th>${esc(tr('Trazabilidad','Provenance'))}</th></tr></thead><tbody>${rows.map(row=>`<tr><td><div class="v20-paper-title">${esc(row.title||row.paper_id)}</div><div class="v20-mini">${esc(row.publication_date||'')} ${row.journal?'· '+esc(row.journal):''}</div><button class="ghost v20-paper-detail" data-paper="${esc(row.paper_id)}" style="margin-top:6px">${esc(tr('Ver detalle','Details'))}</button></td><td><div class="v20-cell">${shortList([...(row.regimes||[]),...(row.mechanisms||[])],5)}</div></td><td><div class="v20-cell">${shortList(row.variables,6)}</div></td><td><div class="v20-cell">${shortList([...(row.diagnostics||[]),...(row.methods||[])],6)}</div></td><td><div class="v20-cell">${shortList(row.results,6)}</div></td><td><div class="v20-cell">${shortList(row.uncertainties,5)}</div></td><td><div class="v20-cell">${shortList(row.limitations,5)}</div></td><td><div class="v20-cell">${shortList(row.evidence_locations,6)}<span class="v20-mini">${esc(row.direct_evidence_count||0)}/${esc(row.evidence_count||0)} directas</span></div></td></tr>`).join('')}</tbody></table>`;
    qa('.v20-paper-detail').forEach(button=>button.onclick=()=>showMatrixDetail(button.dataset.paper));
  }

  function showMatrixDetail(paperId) {
    const row=(matrix?.rows||[]).find(x=>String(x.paper_id)===String(paperId)); const box=q('#v20-matrix-detail'); if(!row||!box)return;
    const block=(title,values,formatter=null)=>{if(!(values||[]).length)return'';return`<div><h4>${esc(title)}</h4><ul class="v20-list">${values.slice(0,30).map(x=>`<li>${esc(formatter?formatter(x):(typeof x==='string'?x:(x.text||x.name||JSON.stringify(x))))}</li>`).join('')}</ul></div>`};
    box.innerHTML=`<div class="v20-detail"><div class="v20-head"><div><strong>${esc(row.title||row.paper_id)}</strong><div class="v20-mini">${esc(row.paper_id)}</div></div><button id="v20-detail-close" class="ghost">×</button></div><div class="v20-detail-grid" style="margin-top:10px">${block(tr('Resultados','Results'),row.results,x=>x.text||'')}${block(tr('Ecuaciones','Equations'),row.equations)}${block(tr('Condiciones iniciales','Initial conditions'),row.initial_conditions)}${block(tr('Condiciones de borde','Boundary conditions'),row.boundary_conditions)}${block(tr('Reproducibilidad','Reproducibility'),row.reproducibility)}${block(tr('Pruebas propuestas','Proposed tests'),row.proposed_tests)}${block(tr('Ubicaciones de evidencia','Evidence locations'),row.evidence_locations)}</div></div>`;
    q('#v20-detail-close').onclick=()=>box.innerHTML='';
    box.scrollIntoView({behavior:'smooth',block:'nearest'});
  }

  function ensureMapView() {
    let view=q('#view-map');
    if(!view){view=document.createElement('section');view.id='view-map';view.className='view';q('.main')?.appendChild(view);}
    let nav=q('[data-view="map"]');
    if(!nav){nav=document.createElement('button');nav.className='nav';nav.dataset.view='map';nav.textContent=tr('Mapa científico','Scientific map');q('.sidebar nav')?.appendChild(nav);}
    nav.classList.remove('v18-hidden','advanced-nav-hidden');
    nav.onclick=()=>setView('map');
    if(view.dataset.v20==='1')return;
    view.dataset.v20='1';
    view.innerHTML=`<div class="v20-map-shell"><div class="v18-flow-banner"><h2>${esc(tr('Mapa científico basado en evidencia','Evidence-based scientific map'))}</h2><p>${esc(tr('Navega paper → claim → evidencia → modelo/diagnóstico. Las contradicciones e hipótesis se agregan como análisis explícitos y no se infieren del grafo determinista.','Navigate paper → claim → evidence → model/diagnostic. Contradictions and hypotheses are explicit analyses and are not inferred by the deterministic graph.'))}</p></div><article class="v20-card" style="margin-top:0"><div class="v20-head"><div><h2>${esc(tr('Grafo de conocimiento científico','Scientific knowledge graph'))}</h2><div id="v20-graph-badges" class="v20-badges"></div></div><div class="v20-map-toolbar"><button id="v20-build-graph" class="secondary">${esc(tr('Reconstruir grafo','Rebuild graph'))}</button><button id="v20-find-contradictions" class="ghost">${esc(tr('Analizar contradicciones','Analyze contradictions'))}</button><select id="v20-node-type"><option value="">${esc(tr('Todos los tipos','All types'))}</option><option value="paper">paper</option><option value="claim">claim</option><option value="evidence">evidence</option><option value="model">model</option><option value="equation">equation</option><option value="diagnostic">diagnostic</option></select><input id="v20-graph-search" placeholder="${esc(tr('Filtrar nodos…','Filter nodes…'))}"></div></div><div class="v20-map-grid" style="margin-top:12px"><div id="v20-network" class="v20-network"><div class="v20-empty">${esc(tr('Cargando grafo…','Loading graph…'))}</div></div><aside id="v20-inspector" class="v20-inspector"><strong>${esc(tr('Inspector de evidencia','Evidence inspector'))}</strong><p class="muted">${esc(tr('Selecciona un nodo para ver propiedades y relaciones.', 'Select a node to inspect properties and relations.'))}</p></aside></div></article><article class="v20-card"><div class="v20-head"><div><h2>${esc(tr('Contradicciones e hipótesis competidoras','Contradictions and competing hypotheses'))}</h2><p class="muted">${esc(tr('Las contradicciones son candidatas hasta revisión humana. Las hipótesis deben producir predicciones distintas y una prueba discriminante.','Contradictions remain candidates until human review. Hypotheses must produce distinct predictions and a discriminating test.'))}</p></div></div><div class="v20-map-toolbar" style="margin-top:9px"><input id="v20-hypothesis-question" class="v20-map-question" placeholder="${esc(tr('Pregunta que debe explicar la competencia de hipótesis…','Question the competing hypotheses should explain…'))}"><button id="v20-generate-hypotheses" class="primary">${esc(tr('Generar competencia','Generate competition'))}</button></div><div id="v20-contradictions"></div><div id="v20-competitions"></div></article></div>`;
    q('#v20-build-graph').onclick=()=>buildGraph(true);
    q('#v20-find-contradictions').onclick=detectContradictions;
    q('#v20-generate-hypotheses').onclick=generateHypotheses;
    q('#v20-node-type').onchange=renderGraph;
    q('#v20-graph-search').oninput=renderGraph;
  }

  async function getGraphData() {
    const f=folder(); if(!f?.folder_id)return null;
    const id=encodeURIComponent(f.folder_id);
    const [summary,nodes,edges,contradictions,competitions]=await Promise.all([
      api(`/api/science?op=graph_summary&folder_id=${id}`),api(`/api/science?op=graph_nodes&folder_id=${id}&limit=5000`),api(`/api/science?op=graph_edges&folder_id=${id}&limit=10000`),api(`/api/science?op=contradictions&folder_id=${id}&limit=500`),api(`/api/science?op=hypotheses&folder_id=${id}&limit=20`)
    ]);
    graph={summary,nodes:nodes.nodes||[],edges:edges.edges||[],contradictions:contradictions.contradictions||[],competitions:competitions.competitions||[]}; graphFolder=f.folder_id; return graph;
  }

  async function loadGraph(autoBuild=true) {
    const f=folder(); if(!f?.folder_id||graphBusy)return;
    graphBusy=true;
    try{
      await loadMatrix(false);
      await getGraphData();
      const saved=localStorage.getItem(`scibrain:v20:graph:${f.folder_id}`)||'';
      const fingerprint=matrix?.fingerprint||'';
      if(autoBuild && (Number(graph.summary?.nodes||0)===0 || (fingerprint && saved!==fingerprint)) && Number(matrix?.coverage?.full_text_papers||0)>0){
        await api('/api/science?op=build_graph',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,full_text_only:true})});
        if(fingerprint)localStorage.setItem(`scibrain:v20:graph:${f.folder_id}`,fingerprint);
        await getGraphData();
      }
      renderGraph(); renderContradictions(); renderCompetitions();
    }catch(error){q('#v20-network').innerHTML=`<div class="v20-empty">${esc(error.message||String(error))}</div>`;}finally{graphBusy=false;}
  }

  async function buildGraph(manual=false) {
    const f=folder(); if(!f?.folder_id||graphBusy)return; graphBusy=true;
    const button=q('#v20-build-graph'); if(button)button.disabled=true;
    try{await api('/api/science?op=build_graph',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,full_text_only:true})});if(matrix?.fingerprint)localStorage.setItem(`scibrain:v20:graph:${f.folder_id}`,matrix.fingerprint);await getGraphData();renderGraph();renderContradictions();renderCompetitions();if(manual)notify(tr('Grafo reconstruido desde análisis full-text.','Graph rebuilt from full-text analyses.'));}catch(error){notify(error.message||String(error),true)}finally{graphBusy=false;if(button)button.disabled=false;}
  }

  function typeColumn(node) {
    if(node.node_type==='paper')return 0; if(node.node_type==='claim')return 1; if(node.node_type==='evidence')return 2; return 3;
  }

  function renderGraph() {
    const network=q('#v20-network'); if(!network)return;
    const summary=graph.summary||{}; const badges=q('#v20-graph-badges');
    if(badges)badges.innerHTML=`<span class="v20-badge">${esc(summary.nodes||0)} nodos</span><span class="v20-badge">${esc(summary.edges||0)} relaciones</span><span class="v20-badge">${esc(summary.contradictions||0)} contradicciones</span><span class="v20-badge">${esc(summary.candidate_hypotheses||0)} hipótesis</span>`;
    const type=q('#v20-node-type')?.value||''; const term=(q('#v20-graph-search')?.value||'').trim().toLowerCase();
    let nodes=(graph.nodes||[]).filter(n=>(!type||n.node_type===type)&&(!term||`${n.label} ${n.paper_id||''} ${JSON.stringify(n.properties||{})}`.toLowerCase().includes(term)));
    const limits={paper:18,claim:42,evidence:42,other:30}; const counts={paper:0,claim:0,evidence:0,other:0};
    nodes=nodes.filter(n=>{const key=['paper','claim','evidence'].includes(n.node_type)?n.node_type:'other';counts[key]+=1;return counts[key]<=limits[key];});
    if(!nodes.length){network.innerHTML=`<div class="v20-empty">${esc(tr('El grafo no contiene nodos para este filtro.','The graph has no nodes for this filter.'))}</div>`;return;}
    const columns=[[],[],[],[]]; nodes.forEach(n=>columns[typeColumn(n)].push(n));
    const pos=new Map(); const xs=[20,250,480,710]; const height=Math.max(540,...columns.map(c=>c.length*48+70));
    columns.forEach((col,ci)=>col.forEach((node,i)=>pos.set(node.node_id,{x:xs[ci],y:38+i*48,node})));
    const visible=new Set(pos.keys()); const edges=(graph.edges||[]).filter(e=>visible.has(e.source_node_id)&&visible.has(e.target_node_id)).slice(0,260);
    const edgeSvg=edges.map(e=>{const a=pos.get(e.source_node_id),b=pos.get(e.target_node_id);return`<line class="v20-edge ${esc(e.relation)}" x1="${a.x+190}" y1="${a.y+16}" x2="${b.x}" y2="${b.y+16}"/>`}).join('');
    const nodeSvg=[...pos.values()].map(({x,y,node})=>{const key=['paper','claim','evidence'].includes(node.node_type)?node.node_type:'other';const label=String(node.label||node.node_id).replace(/\s+/g,' ').slice(0,31);return`<g class="v20-node ${key}" data-node="${esc(node.node_id)}"><rect x="${x}" y="${y}" width="190" height="32" rx="6"/><text x="${x+7}" y="${y+13}">${esc(node.node_type)}</text><text x="${x+7}" y="${y+25}">${esc(label)}</text></g>`}).join('');
    network.innerHTML=`<svg viewBox="0 0 930 ${height}" width="100%" height="${height}">${edgeSvg}${nodeSvg}</svg>`;
    network.querySelectorAll('[data-node]').forEach(el=>el.addEventListener('click',()=>inspectNode(el.dataset.node)));
  }

  function inspectNode(id) {
    const node=(graph.nodes||[]).find(n=>n.node_id===id); const box=q('#v20-inspector'); if(!node||!box)return;
    const related=(graph.edges||[]).filter(e=>e.source_node_id===id||e.target_node_id===id).slice(0,80);
    const nodeMap=new Map((graph.nodes||[]).map(n=>[n.node_id,n]));
    box.innerHTML=`<strong>${esc(node.node_type)} · ${esc(node.epistemic_state||'')}</strong><p>${esc(node.label||'')}</p><div class="v20-mini">${esc(node.paper_id||'')}</div>${Object.keys(node.properties||{}).length?`<div class="v20-section"><strong>${esc(tr('Propiedades','Properties'))}</strong><pre>${esc(JSON.stringify(node.properties,null,2))}</pre></div>`:''}<div class="v20-section"><strong>${esc(tr('Relaciones','Relations'))}</strong>${related.map(e=>{const other=e.source_node_id===id?e.target_node_id:e.source_node_id;const target=nodeMap.get(other);return`<div class="v20-mini" style="margin-top:6px"><b>${esc(e.relation)}</b> → ${esc(target?.label||other)}</div>`}).join('')||'—'}</div>`;
  }

  async function detectContradictions() {
    const f=folder(); const button=q('#v20-find-contradictions'); if(!f?.folder_id||!button)return;button.disabled=true;
    try{const r=await api('/api/science?op=detect_contradictions',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,context:matrix?.epistemic_note||''})});graph.contradictions=r.contradictions||[];renderContradictions();await getGraphData();renderGraph();notify(`${r.count||0} ${tr('candidatas encontradas','candidates found')}`);}catch(error){notify(error.message||String(error),true)}finally{button.disabled=false;}
  }

  function renderContradictions() {
    const box=q('#v20-contradictions'); if(!box)return; const rows=graph.contradictions||[];
    box.innerHTML=rows.length?`<div class="v20-section"><strong>${esc(tr('Contradicciones candidatas','Candidate contradictions'))}</strong>${rows.slice(0,20).map(x=>`<div class="v20-contradiction"><b>${esc(x.contradiction_type||'contradiction')}</b> · ${esc(Math.round(Number(x.confidence||0)*100))}%<br>${esc(x.summary||'')}${x.regime_difference?`<br><span class="v20-mini">${esc(tr('Diferencia de régimen','Regime difference'))}: ${esc(x.regime_difference)}</span>`:''}${x.required_test?`<br><b>${esc(tr('Prueba requerida','Required test'))}:</b> ${esc(x.required_test)}`:''}</div>`).join('')}</div>`:'';
  }

  async function generateHypotheses() {
    const f=folder(); const question=q('#v20-hypothesis-question')?.value?.trim(); const button=q('#v20-generate-hypotheses'); if(!f?.folder_id||!question||!button)return;button.disabled=true;
    try{await api('/api/science?op=generate_hypotheses',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,question})});await getGraphData();renderCompetitions();renderGraph();}catch(error){notify(error.message||String(error),true)}finally{button.disabled=false;}
  }

  function renderCompetitions() {
    const box=q('#v20-competitions'); if(!box)return; const comps=graph.competitions||[];
    box.innerHTML=comps.length?`<div class="v20-section"><strong>${esc(tr('Competencias de hipótesis','Hypothesis competitions'))}</strong>${comps.slice(0,8).map(c=>`<div class="v20-hypothesis"><b>${esc(c.question||'')}</b>${(c.hypotheses||[]).map(h=>`<div style="margin-top:8px"><b>${esc(h.statement||'')}</b><br><span class="v20-mini">${esc(h.mechanism||'')}</span>${(h.falsifiable_predictions||[]).length?`<br>${esc(tr('Predicción','Prediction'))}: ${esc(h.falsifiable_predictions.join(' · '))}`:''}${h.discriminating_experiment?`<br>${esc(tr('Experimento discriminante','Discriminating experiment'))}: ${esc(h.discriminating_experiment)}`:''}${h.rejection_criterion?`<br>${esc(tr('Rechazo','Rejection'))}: ${esc(h.rejection_criterion)}`:''}</div>`).join('')}${c.decision_needed?`<div class="v20-mini" style="margin-top:8px">${esc(c.decision_needed)}</div>`:''}</div>`).join('')}</div>`:'';
  }

  function installRouting() {
    if(typeof setView==='function'&&!window.__SB_V20_VIEW_HOOK__){window.__SB_V20_VIEW_HOOK__=true;baseSetView=setView;setView=function(name){baseSetView(name);if(name==='collab'||name==='research')loadMatrix(false).catch(()=>{});if(name==='map')loadGraph(true).catch(()=>{});};}
    if(typeof selectFolder==='function'&&!window.__SB_V20_FOLDER_HOOK__){window.__SB_V20_FOLDER_HOOK__=true;baseSelectFolder=selectFolder;selectFolder=async function(...args){const result=await baseSelectFolder.apply(this,args);matrix=null;matrixFolder=null;graph={summary:null,nodes:[],edges:[],contradictions:[],competitions:[]};graphFolder=null;if(q('#view-collab.active'))loadMatrix(true);if(q('#view-map.active'))loadGraph(true);return result;};}
  }

  function install() {
    styles(); ensureMatrixCard(); ensureMapView(); installRouting();
    if(q('#view-collab.active'))loadMatrix(false);
    if(q('#view-map.active'))loadGraph(true);
    setInterval(()=>{if(q('#view-collab.active')&&folder()?.folder_id)loadMatrix(true).catch(()=>{});},30000);
  }

  document.addEventListener('scibrain:languagechange',()=>{ensureMapView();renderMatrix();renderGraph();renderContradictions();renderCompetitions();});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
