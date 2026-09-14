(() => {
  if (window.__SB_V22_GAP_MODE__) return;
  window.__SB_V22_GAP_MODE__ = true;

  const q = s => document.querySelector(s);
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const currentFolder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad ? 'error' : 'log'](text);

  async function generateFromQuestion() {
    const f = currentFolder();
    const question = q('#v22-question')?.value?.trim() || '';
    const button = q('#v22-generate');
    const status = q('#v22-status');
    if (!f?.folder_id) return notify(tr('Selecciona una carpeta de investigación.','Select a research folder.'), true);
    if (!question) return notify(tr('Escribe una pregunta científica antes de generar hipótesis.','Write a scientific question before generating hypotheses.'), true);
    if (button?.disabled) return;
    if (button) button.disabled = true;
    try {
      if (status) status.textContent = tr('Preparando grafo científico desde evidencia full-text…','Preparing the scientific graph from full-text evidence…');
      const graph = await api('/api/science?op=build_graph', {
        method:'POST',
        body:JSON.stringify({folder_id:f.folder_id, full_text_only:true}),
      });
      if (!Number(graph?.claim_count || 0)) {
        throw new Error(tr(
          'No hay claims validados de papers full-text. Completa primero el análisis profundo del corpus.',
          'There are no validated claims from full-text papers. Complete deep corpus analysis first.'
        ));
      }

      if (status) status.textContent = tr('Comprobando si existen contradicciones relevantes…','Checking for relevant contradictions…');
      const contradictionResult = await api('/api/science?op=detect_contradictions', {
        method:'POST',
        body:JSON.stringify({folder_id:f.folder_id, context:question}),
      });
      const count = Number(contradictionResult?.count || 0);
      if (status) status.textContent = count
        ? tr(`Se detectaron ${count} contradicción(es). Generando explicaciones competidoras…`,`${count} contradiction(s) detected. Generating competing explanations…`)
        : tr('No se detectaron contradicciones: usando la pregunta y claims validados como problema abierto de evidencia.','No contradictions detected: using the question and validated claims as an open evidence problem.');

      const result = await api('/api/science?op=generate_hypotheses', {
        method:'POST',
        body:JSON.stringify({folder_id:f.folder_id, question}),
      });
      q('#v22-load')?.click();
      if (status) status.textContent = count
        ? tr('Competencia de hipótesis basada en contradicciones generada y persistida.','Contradiction-based hypothesis competition generated and persisted.')
        : tr('Competencia de hipótesis para brecha/pregunta abierta generada y persistida.','Open-gap/question hypothesis competition generated and persisted.');
      notify(tr(
        `Hipótesis competidoras generadas (${result?.hypotheses?.length || 0}).`,
        `Competing hypotheses generated (${result?.hypotheses?.length || 0}).`
      ));
    } catch (error) {
      if (status) status.textContent = error.message || String(error);
      notify(error.message || String(error), true);
    } finally {
      if (button) button.disabled = false;
    }
  }

  function install() {
    const button = q('#v22-generate');
    if (!button) return false;
    button.onclick = generateFromQuestion;
    button.title = tr(
      'Funciona con contradicciones o con una pregunta abierta sustentada por claims full-text.',
      'Works with contradictions or an open question grounded in full-text claims.'
    );
    return true;
  }

  if (!install()) {
    document.addEventListener('scibrain:modulesready', install, {once:true});
    setTimeout(install, 0);
  }
})();
