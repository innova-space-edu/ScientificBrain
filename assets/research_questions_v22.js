(() => {
  if (window.__SB_V22_RESEARCH_QUESTIONS__) return;
  window.__SB_V22_RESEARCH_QUESTIONS__ = true;

  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const folder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad ? 'error' : 'log'](text);

  let workspace = null;
  let contradictions = [];
  let competitions = [];
  let busy = false;
  let baseSelectFolder = null;
  let baseSetView = null;

  function styles() {
    if (q('#v22-style')) return;
    const style = document.createElement('style');
    style.id = 'v22-style';
    style.textContent = `
      .v22-shell{display:grid;gap:14px}.v22-card{border:1px solid #e4e7ec;border-radius:13px;padding:14px;background:#fff}.v22-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}.v22-head h2,.v22-head h3{margin:0}.v22-actions{display:flex;gap:7px;flex-wrap:wrap;align-items:center}.v22-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(320px,.78fr);gap:14px}.v22-context-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:10px}.v22-context{border:1px solid #e4e7ec;border-radius:10px;padding:10px;background:#fcfcfd;min-height:92px}.v22-context strong{font-size:10px;display:block;margin-bottom:5px}.v22-context p,.v22-context li{font-size:10px;line-height:1.45;color:#475467}.v22-context ul{margin:0;padding-left:16px}.v22-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.v22-badge{font-size:9px;padding:4px 7px;border-radius:999px;background:#f2f4f7;color:#344054}.v22-badge.ok{background:#ecfdf3;color:#067647}.v22-badge.warn{background:#fffaeb;color:#93370d}.v22-badge.bad{background:#fef3f2;color:#b42318}.v22-question{width:100%;min-height:92px;resize:vertical;margin-top:7px}.v22-note{margin-top:9px;padding:9px 11px;border-radius:9px;border:1px solid #b2ccff;background:#f5f8ff;color:#344054;font-size:10px;line-height:1.5}.v22-pipeline{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:10px}.v22-step{border:1px solid #e4e7ec;border-radius:9px;padding:9px;background:#fff}.v22-step strong{display:block;font-size:10px}.v22-step span{display:block;font-size:9px;color:#667085;margin-top:4px;line-height:1.4}.v22-list{display:grid;gap:10px;margin-top:10px}.v22-competition{border:1px solid #d0d5dd;border-radius:12px;padding:12px;background:#fff}.v22-competition-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap}.v22-competition h3{font-size:12px;margin:0;line-height:1.45}.v22-decision{font-size:10px;color:#475467;margin-top:6px;line-height:1.45}.v22-hypotheses{display:grid;gap:9px;margin-top:10px}.v22-hypothesis{border:1px solid #d6bbfb;border-radius:10px;padding:10px;background:#fcfaff}.v22-hypothesis-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.v22-hypothesis h4{font-size:11px;line-height:1.45;margin:0}.v22-confidence{font-size:9px;white-space:nowrap;padding:4px 6px;border-radius:999px;background:#f2f4f7;color:#344054}.v22-field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:8px}.v22-field{border-top:1px solid #eaecf0;padding-top:7px}.v22-field strong{display:block;font-size:9px;margin-bottom:4px;color:#344054}.v22-field p,.v22-field li{font-size:9px;line-height:1.45;color:#475467}.v22-field p{margin:0}.v22-field ul{margin:0;padding-left:15px}.v22-evidence{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.v22-empty{padding:18px;text-align:center;color:#667085;font-size:11px;border:1px dashed #d0d5dd;border-radius:10px}.v22-source{font-size:9px;color:#667085}.v22-toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.v22-toolbar button{font-size:10px}.v22-status{font-size:10px;color:#667085;margin-top:8px}.v22-copy{font-size:9px}.v22-gaps{display:grid;gap:7px;margin-top:8px}.v22-gap{padding:8px;border-radius:8px;border:1px solid #eaecf0;background:#f9fafb;font-size:9px;line-height:1.4;color:#475467}
      @media(max-width:980px){.v22-grid,.v22-context-grid,.v22-pipeline,.v22-field-grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function ensureView() {
    let view = q('#view-hypotheses');
    if (!view) {
      view = document.createElement('section');
      view.id = 'view-hypotheses';
      view.className = 'view';
      q('.main')?.insertBefore(view, q('.site-footer'));
    }
    let nav = q('[data-view="hypotheses"]');
    if (!nav) {
      nav = document.createElement('button');
      nav.className = 'nav';
      nav.dataset.view = 'hypotheses';
      nav.textContent = tr('Preguntas e hipótesis', 'Questions & hypotheses');
      q('.sidebar nav')?.appendChild(nav);
    }
    nav.onclick = () => setView('hypotheses');
    if (view.dataset.v22 === '1') return;
    view.dataset.v22 = '1';
    view.innerHTML = `
      <div class="v22-shell">
        <article class="v22-card">
          <div class="v22-head">
            <div><p class="eyebrow">ScientificBrain v0.22</p><h2>${esc(tr('Motor de preguntas e hipótesis científicas','Scientific question and hypothesis engine'))}</h2><p class="muted">${esc(tr('Convierte el estado del arte, contradicciones y evidencia revisada a texto completo en preguntas falsables e hipótesis competidoras. No usa títulos o abstracts como prueba.','Turns the state of the art, contradictions and full-text-reviewed evidence into falsifiable questions and competing hypotheses. Titles and abstracts are not treated as proof.'))}</p></div>
            <div class="v22-actions"><button id="v22-refresh" class="ghost">${esc(tr('Actualizar contexto','Refresh context'))}</button></div>
          </div>
          <div id="v22-badges" class="v22-badges"></div>
          <div id="v22-context" class="v22-context-grid"></div>
        </article>

        <div class="v22-grid">
          <article class="v22-card">
            <div class="v22-head"><div><h3>${esc(tr('Pregunta científica','Scientific question'))}</h3><p class="muted">${esc(tr('Formula una pregunta que pueda resolverse mediante observables, evidencia y una prueba discriminante.','Formulate a question that can be resolved through observables, evidence and a discriminating test.'))}</p></div></div>
            <textarea id="v22-question" class="v22-question" placeholder="${esc(tr('Ej.: ¿Qué mecanismo explica la discrepancia entre los resultados A y B bajo regímenes comparables?','e.g. Which mechanism explains the discrepancy between results A and B under comparable regimes?'))}"></textarea>
            <div class="v22-pipeline">
              <div class="v22-step"><strong>1 · ${esc(tr('Grafo científico','Scientific graph'))}</strong><span>${esc(tr('Reconstruye papers → claims → evidencia usando solo full-text revisado.','Rebuilds papers → claims → evidence using only full-text-reviewed papers.'))}</span></div>
              <div class="v22-step"><strong>2 · ${esc(tr('Contradicciones','Contradictions'))}</strong><span>${esc(tr('Busca incompatibilidades reales y diferencias de régimen o método.','Finds real incompatibilities and regime or method differences.'))}</span></div>
              <div class="v22-step"><strong>3 · ${esc(tr('Competencia de hipótesis','Hypothesis competition'))}</strong><span>${esc(tr('Genera alternativas falsables con predicciones y criterios de rechazo.','Generates falsifiable alternatives with predictions and rejection criteria.'))}</span></div>
            </div>
            <div class="v22-toolbar">
              <button id="v22-prepare" class="secondary">${esc(tr('Preparar evidencia','Prepare evidence'))}</button>
              <button id="v22-generate" class="primary">${esc(tr('Generar hipótesis competidoras','Generate competing hypotheses'))}</button>
              <button id="v22-save-question" class="ghost">${esc(tr('Guardar pregunta en el documento','Save question to document'))}</button>
            </div>
            <div id="v22-status" class="v22-status"></div>
            <div class="v22-note">${esc(tr('Regla epistemológica: una hipótesis candidata no se convierte en resultado. Debe conservar su estado de hipótesis hasta que una medición, simulación o análisis posterior satisfaga una prueba definida y sobreviva a revisión crítica.','Epistemic rule: a candidate hypothesis does not become a result. It remains a hypothesis until a later measurement, simulation or analysis satisfies a defined test and survives critical review.'))}</div>
          </article>

          <aside class="v22-card">
            <div class="v22-head"><div><h3>${esc(tr('Brechas y contradicciones activas','Active gaps and contradictions'))}</h3><p class="muted">${esc(tr('Material que debe orientar la pregunta, no reemplazar la evidencia.','Material that should guide the question, not replace evidence.'))}</p></div></div>
            <div id="v22-gaps" class="v22-gaps"></div>
          </aside>
        </div>

        <article class="v22-card">
          <div class="v22-head"><div><h3>${esc(tr('Hipótesis competidoras','Competing hypotheses'))}</h3><p class="muted">${esc(tr('Cada alternativa muestra mecanismo, predicciones, observables discriminantes, experimento decisivo, régimen de validez y criterio explícito de rechazo.','Each alternative shows mechanism, predictions, discriminating observables, decisive experiment, validity regime and explicit rejection criterion.'))}</p></div><div class="v22-actions"><button id="v22-load" class="ghost">${esc(tr('Recargar hipótesis','Reload hypotheses'))}</button></div></div>
          <div id="v22-competitions" class="v22-list"><div class="v22-empty">${esc(tr('No hay hipótesis cargadas.','No hypotheses loaded.'))}</div></div>
        </article>
      </div>`;

    q('#v22-refresh').onclick = () => loadAll(true);
    q('#v22-load').onclick = () => loadCompetitions(true);
    q('#v22-prepare').onclick = prepareEvidence;
    q('#v22-generate').onclick = generateHypotheses;
    q('#v22-save-question').onclick = saveQuestion;
  }

  function activeDocument() {
    return workspace?.document || window.__SCIBRAIN_RECOVERED_DOCUMENT__ || null;
  }

  function sourceQuestion() {
    const document = activeDocument();
    const sections = document?.sections || {};
    const section = sections.research_question;
    if (typeof section === 'string') return section.trim();
    if (section?.text) return String(section.text).trim();
    const brief = document?.research_brief || {};
    const questions = Array.isArray(brief.questions) ? brief.questions : [];
    if (questions.length) return String(questions[0] || '').trim();
    return '';
  }

  function gapsFromWorkspace() {
    const doc = activeDocument() || {};
    const manifest = doc.evidence_manifest || {};
    const novelty = doc.novelty_assessment || {};
    const values = [];
    for (const key of ['knowledge_gaps','contested_points','limitations']) {
      const rows = manifest[key];
      if (Array.isArray(rows)) values.push(...rows);
    }
    for (const key of ['gaps','open_questions','risks','limitations']) {
      const rows = novelty[key];
      if (Array.isArray(rows)) values.push(...rows);
      else if (rows) values.push(rows);
    }
    return [...new Set(values.map(x => String(x || '').trim()).filter(Boolean))].slice(0, 18);
  }

  function renderContext() {
    const box = q('#v22-context');
    const badges = q('#v22-badges');
    if (!box || !badges) return;
    const corpus = workspace?.corpus || {};
    const reviewed = Number(corpus.full_text_reviewed || 0);
    const total = Number(corpus.total || 0);
    const gaps = gapsFromWorkspace();
    badges.innerHTML = `
      <span class="v22-badge ${reviewed ? 'ok' : 'warn'}">${esc(reviewed)} ${esc(tr('full-text revisados','full-text reviewed'))}</span>
      <span class="v22-badge">${esc(total)} ${esc(tr('papers en carpeta','papers in folder'))}</span>
      <span class="v22-badge ${contradictions.length ? 'warn' : ''}">${esc(contradictions.length)} ${esc(tr('contradicciones','contradictions'))}</span>
      <span class="v22-badge ${competitions.length ? 'ok' : ''}">${esc(competitions.length)} ${esc(tr('competencias','competitions'))}</span>`;
    const topContr = contradictions.slice(0, 4);
    const topGaps = gaps.slice(0, 4);
    const question = q('#v22-question')?.value?.trim() || sourceQuestion();
    box.innerHTML = `
      <div class="v22-context"><strong>${esc(tr('Cobertura de evidencia','Evidence coverage'))}</strong><p>${reviewed ? esc(tr(`${reviewed} paper(s) cuentan como evidencia de texto completo para este motor.`,`${reviewed} paper(s) count as full-text evidence for this engine.`)) : esc(tr('Aún no hay papers full-text revisados; primero completa el análisis profundo.','There are no full-text-reviewed papers yet; complete deep analysis first.'))}</p></div>
      <div class="v22-context"><strong>${esc(tr('Brechas principales','Main gaps'))}</strong>${topGaps.length ? `<ul>${topGaps.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>` : `<p>${esc(tr('Sin brechas persistidas todavía.','No persisted gaps yet.'))}</p>`}</div>
      <div class="v22-context"><strong>${esc(tr('Contradicciones principales','Main contradictions'))}</strong>${topContr.length ? `<ul>${topContr.map(x=>`<li>${esc(x.summary || x.contradiction_type || '')}</li>`).join('')}</ul>` : `<p>${esc(tr('Ejecuta el análisis de contradicciones para poblar esta sección.','Run contradiction analysis to populate this section.'))}</p>`}</div>`;
    if (q('#v22-question') && !q('#v22-question').value.trim() && question) q('#v22-question').value = question;
  }

  function renderGaps() {
    const box = q('#v22-gaps');
    if (!box) return;
    const rows = [];
    gapsFromWorkspace().slice(0, 8).forEach(value => rows.push({kind:tr('Brecha','Gap'), text:value}));
    contradictions.slice(0, 8).forEach(value => rows.push({kind:tr('Contradicción','Contradiction'), text:value.summary || value.possible_explanation || value.contradiction_type || ''}));
    if (!rows.length) {
      box.innerHTML = `<div class="v22-empty">${esc(tr('Todavía no hay brechas o contradicciones suficientes.','There are not enough gaps or contradictions yet.'))}</div>`;
      return;
    }
    box.innerHTML = rows.slice(0,12).map(row => `<div class="v22-gap"><strong>${esc(row.kind)}</strong><br>${esc(row.text)}</div>`).join('');
  }

  function listField(title, values) {
    const rows = Array.isArray(values) ? values.filter(Boolean) : [];
    if (!rows.length) return '';
    return `<div class="v22-field"><strong>${esc(title)}</strong><ul>${rows.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`;
  }

  function textField(title, value) {
    const text = String(value || '').trim();
    if (!text) return '';
    return `<div class="v22-field"><strong>${esc(title)}</strong><p>${esc(text)}</p></div>`;
  }

  function renderCompetitions() {
    const box = q('#v22-competitions');
    if (!box) return;
    if (!competitions.length) {
      box.innerHTML = `<div class="v22-empty">${esc(tr('No hay competencias de hipótesis persistidas para esta carpeta. Prepara la evidencia y genera una desde una pregunta científica.','No persisted hypothesis competitions exist for this folder. Prepare the evidence and generate one from a scientific question.'))}</div>`;
      renderContext();
      return;
    }
    box.innerHTML = competitions.map(comp => `
      <div class="v22-competition">
        <div class="v22-competition-head"><div><h3>${esc(comp.question || tr('Pregunta sin título','Untitled question'))}</h3><div class="v22-source">${esc(comp.competition_id || '')}</div></div><span class="v22-badge">${esc((comp.hypotheses || []).length)} ${esc(tr('hipótesis','hypotheses'))}</span></div>
        ${comp.decision_needed ? `<div class="v22-decision"><strong>${esc(tr('Decisión científica necesaria:','Scientific decision needed:'))}</strong> ${esc(comp.decision_needed)}</div>` : ''}
        <div class="v22-hypotheses">${(comp.hypotheses || []).map((hyp, index) => `
          <div class="v22-hypothesis">
            <div class="v22-hypothesis-head"><h4>H${index+1} · ${esc(hyp.statement || '')}</h4><span class="v22-confidence">${esc(Math.round(Number(hyp.confidence || 0) * 100))}%</span></div>
            <div class="v22-field-grid">
              ${textField(tr('Mecanismo','Mechanism'), hyp.mechanism)}
              ${textField(tr('Régimen de validez','Validity regime'), hyp.regime_of_validity)}
              ${listField(tr('Predicciones falsables','Falsifiable predictions'), hyp.falsifiable_predictions)}
              ${listField(tr('Observables discriminantes','Discriminating observables'), hyp.discriminating_observables)}
              ${textField(tr('Prueba / experimento discriminante','Discriminating test / experiment'), hyp.discriminating_experiment)}
              ${textField(tr('Criterio de rechazo','Rejection criterion'), hyp.rejection_criterion)}
            </div>
            <div class="v22-evidence"><span class="v22-badge ok">${esc((hyp.supporting_evidence_ids || []).length)} ${esc(tr('evidencias a favor','supporting evidence'))}</span><span class="v22-badge bad">${esc((hyp.contradicting_evidence_ids || []).length)} ${esc(tr('evidencias en contra','contradicting evidence'))}</span><span class="v22-badge">${esc(hyp.status || 'candidate')}</span></div>
            <div class="v22-toolbar"><button class="ghost v22-copy" data-hypothesis="${esc(hyp.hypothesis_id || '')}">${esc(tr('Copiar hipótesis estructurada','Copy structured hypothesis'))}</button></div>
          </div>`).join('')}</div>
      </div>`).join('');
    qa('.v22-copy').forEach(button => button.onclick = async () => {
      const id = button.dataset.hypothesis;
      let found = null;
      for (const comp of competitions) {
        found = (comp.hypotheses || []).find(h => String(h.hypothesis_id) === String(id));
        if (found) break;
      }
      if (!found) return;
      const payload = {
        statement: found.statement,
        mechanism: found.mechanism,
        falsifiable_predictions: found.falsifiable_predictions || [],
        discriminating_observables: found.discriminating_observables || [],
        discriminating_experiment: found.discriminating_experiment,
        regime_of_validity: found.regime_of_validity,
        rejection_criterion: found.rejection_criterion,
        confidence: found.confidence,
        status: found.status,
      };
      try {
        await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
        notify(tr('Hipótesis copiada.','Hypothesis copied.'));
      } catch (_) {
        notify(tr('No se pudo copiar al portapapeles.','Could not copy to clipboard.'), true);
      }
    });
    renderContext();
  }

  async function loadWorkspace() {
    const f = folder();
    if (!f?.folder_id) { workspace = null; renderContext(); renderGaps(); return null; }
    workspace = await api('/api/science?op=research_workspace&folder_id=' + encodeURIComponent(f.folder_id));
    const question = sourceQuestion();
    if (question && q('#v22-question') && !q('#v22-question').value.trim()) q('#v22-question').value = question;
    renderContext();
    renderGaps();
    return workspace;
  }

  async function loadContradictions() {
    const f = folder();
    if (!f?.folder_id) { contradictions = []; renderContext(); renderGaps(); return []; }
    const result = await api('/api/science?op=contradictions&folder_id=' + encodeURIComponent(f.folder_id) + '&limit=500');
    contradictions = result.contradictions || [];
    renderContext(); renderGaps();
    return contradictions;
  }

  async function loadCompetitions() {
    const f = folder();
    if (!f?.folder_id) { competitions = []; renderCompetitions(); return []; }
    const result = await api('/api/science?op=hypotheses&folder_id=' + encodeURIComponent(f.folder_id) + '&limit=50');
    competitions = result.competitions || [];
    renderCompetitions();
    return competitions;
  }

  async function loadAll(force=false) {
    const f = folder();
    if (!f?.folder_id) {
      workspace = null; contradictions = []; competitions = [];
      renderContext(); renderGaps(); renderCompetitions();
      return;
    }
    if (busy && !force) return;
    busy = true;
    const status = q('#v22-status');
    if (status) status.textContent = tr('Actualizando contexto científico…','Refreshing scientific context…');
    try {
      await Promise.allSettled([loadWorkspace(), loadContradictions(), loadCompetitions()]);
      if (status) status.textContent = tr('Contexto actualizado.','Context refreshed.');
    } finally { busy = false; }
  }

  async function prepareEvidence() {
    const f = folder();
    if (!f?.folder_id || busy) return notify(tr('Selecciona una carpeta de investigación.','Select a research folder.'), true);
    busy = true;
    const status = q('#v22-status');
    const button = q('#v22-prepare');
    if (button) button.disabled = true;
    try {
      if (status) status.textContent = tr('Reconstruyendo grafo desde papers full-text revisados…','Rebuilding graph from full-text-reviewed papers…');
      const graph = await api('/api/science?op=build_graph', {method:'POST', body:JSON.stringify({folder_id:f.folder_id, full_text_only:true})});
      if (status) status.textContent = tr(`Grafo listo: ${graph.paper_count || 0} papers, ${graph.claim_count || 0} claims. Buscando contradicciones…`,`Graph ready: ${graph.paper_count || 0} papers, ${graph.claim_count || 0} claims. Detecting contradictions…`);
      const question = q('#v22-question')?.value?.trim() || '';
      const result = await api('/api/science?op=detect_contradictions', {method:'POST', body:JSON.stringify({folder_id:f.folder_id, context:question})});
      contradictions = result.contradictions || [];
      if (status) status.textContent = tr(`Base preparada: ${contradictions.length} contradicción(es) candidata(s).`,`Evidence prepared: ${contradictions.length} contradiction candidate(s).`);
      renderContext(); renderGaps();
      notify(tr('Evidencia preparada para competir hipótesis.','Evidence prepared for hypothesis competition.'));
    } catch (error) {
      if (status) status.textContent = error.message || String(error);
      notify(error.message || String(error), true);
    } finally {
      busy = false;
      if (button) button.disabled = false;
    }
  }

  async function generateHypotheses() {
    const f = folder();
    const question = q('#v22-question')?.value?.trim() || '';
    if (!f?.folder_id) return notify(tr('Selecciona una carpeta de investigación.','Select a research folder.'), true);
    if (!question) return notify(tr('Escribe una pregunta científica antes de generar hipótesis.','Write a scientific question before generating hypotheses.'), true);
    if (busy) return;
    busy = true;
    const button = q('#v22-generate');
    const status = q('#v22-status');
    if (button) button.disabled = true;
    try {
      if (!contradictions.length) {
        if (status) status.textContent = tr('No hay contradicciones cargadas; preparando evidencia primero…','No contradictions loaded; preparing evidence first…');
        busy = false;
        await prepareEvidence();
        busy = true;
      }
      if (!contradictions.length) throw new Error(tr('No se detectaron contradicciones suficientes para una competencia de hipótesis.','No sufficient contradictions were detected for a hypothesis competition.'));
      if (status) status.textContent = tr('Generando hipótesis competidoras y pruebas discriminantes…','Generating competing hypotheses and discriminating tests…');
      const result = await api('/api/science?op=generate_hypotheses', {method:'POST', body:JSON.stringify({folder_id:f.folder_id, question})});
      if (result?.competition_id) {
        const existing = competitions.filter(x => x.competition_id !== result.competition_id);
        competitions = [result, ...existing];
      } else {
        await loadCompetitions(true);
      }
      renderCompetitions();
      if (status) status.textContent = tr('Competencia de hipótesis generada y persistida en el grafo científico.','Hypothesis competition generated and persisted in the scientific graph.');
      notify(tr('Hipótesis competidoras generadas.','Competing hypotheses generated.'));
    } catch (error) {
      if (status) status.textContent = error.message || String(error);
      notify(error.message || String(error), true);
    } finally {
      busy = false;
      if (button) button.disabled = false;
    }
  }

  async function saveQuestion() {
    const f = folder();
    const question = q('#v22-question')?.value?.trim() || '';
    if (!f?.folder_id || !question) return notify(tr('Selecciona una carpeta y escribe la pregunta.','Select a folder and write the question.'), true);
    try {
      const result = await api('/api/science?op=save_section', {method:'POST', body:JSON.stringify({folder_id:f.folder_id, section_key:'research_question', content:question})});
      if (result?.document) workspace = {...(workspace || {}), document:result.document};
      notify(tr('Pregunta guardada en el documento científico.','Question saved to the scientific document.'));
      renderContext();
    } catch (error) {
      notify(tr('No hay un documento científico activo. Genera o abre el borrador de investigación antes de guardar la pregunta.','There is no active scientific document. Generate or open the research draft before saving the question.'), true);
    }
  }

  function installHooks() {
    if (typeof setView === 'function' && !window.__SB_V22_SETVIEW_HOOK__) {
      window.__SB_V22_SETVIEW_HOOK__ = true;
      baseSetView = setView;
      setView = function(name) {
        const result = baseSetView.apply(this, arguments);
        if (name === 'hypotheses') {
          const title = q('#page-title');
          if (title) title.textContent = tr('Preguntas e hipótesis','Questions & hypotheses');
          loadAll(false).catch(error => console.warn('ScientificBrain v0.22 load', error));
        }
        return result;
      };
    }
    if (typeof selectFolder === 'function' && !window.__SB_V22_FOLDER_HOOK__) {
      window.__SB_V22_FOLDER_HOOK__ = true;
      baseSelectFolder = selectFolder;
      selectFolder = async function(...args) {
        const result = await baseSelectFolder.apply(this, args);
        workspace = null; contradictions = []; competitions = [];
        const question = q('#v22-question'); if (question) question.value = '';
        await loadAll(true).catch(error => console.warn('ScientificBrain v0.22 folder refresh', error));
        return result;
      };
    }
  }

  function boot() {
    styles();
    ensureView();
    installHooks();
    loadAll(false).catch(error => console.warn('ScientificBrain v0.22 boot', error));
  }

  boot();
})();
