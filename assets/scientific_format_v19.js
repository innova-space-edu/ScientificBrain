(() => {
  if (window.__SB_V19_SCIENTIFIC_FORMAT__) return;
  window.__SB_V19_SCIENTIFIC_FORMAT__ = true;

  const q = s => document.querySelector(s);
  const qa = s => [...document.querySelectorAll(s)];
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const folder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad ? 'error' : 'log'](text);
  let corpusThread = null;
  let corpusBusy = false;
  let mathPromise = null;

  function styles() {
    if (q('#v19-scientific-style')) return;
    const style = document.createElement('style');
    style.id = 'v19-scientific-style';
    style.textContent = `
      .sb-scientific-render{white-space:normal!important;line-height:1.58}.sb-scientific-render h3{font-size:14px;margin:16px 0 7px;color:#101828}.sb-scientific-render h4{font-size:12px;margin:12px 0 6px}.sb-scientific-render p{margin:6px 0}.sb-scientific-render ul,.sb-scientific-render ol{margin:6px 0 8px 20px;padding:0}.sb-scientific-render li{margin:4px 0}.sb-scientific-render strong{color:#101828}.sb-scientific-render code:not(.sb-code){background:#f2f4f7;padding:1px 4px;border-radius:4px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
      .sb-code-wrap{margin:10px 0;border:1px solid #d0d5dd;border-radius:10px;overflow:hidden;background:#101828}.sb-code-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 9px;background:#1d2939;color:#eaecf0;font-size:10px}.sb-code-actions{display:flex;gap:5px}.sb-code-actions button{padding:4px 7px;font-size:9px;background:#344054;color:#fff;border:1px solid #475467;border-radius:6px}.sb-code-wrap pre{margin:0;padding:12px;overflow:auto;max-height:420px}.sb-code{color:#f2f4f7;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;line-height:1.55;white-space:pre}
      .sb-rich-note{font-size:10px;color:#667085;margin-top:7px}.sb-preview{margin-top:10px;padding:12px;border:1px solid #d0d5dd;border-radius:10px;background:#f8fafc}.sb-preview.hidden{display:none}.sb-v19-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.sb-v19-badge{font-size:9px;padding:4px 7px;border-radius:999px;background:#f2f4f7;color:#344054}.sb-v19-badge.ok{background:#ecfdf3;color:#067647}.sb-v19-badge.warn{background:#fffaeb;color:#93370d}
    `;
    document.head.appendChild(style);
  }

  function inline(text) {
    let html = esc(text);
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    return html;
  }

  function proseHtml(text) {
    const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
    const out = [];
    let list = null;
    const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (!line.trim()) { closeList(); continue; }
      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) { closeList(); const level = Math.min(4, heading[1].length + 1); out.push(`<h${level}>${inline(heading[2])}</h${level}>`); continue; }
      const bullet = line.match(/^\s*[-*]\s+(.+)$/);
      if (bullet) { if (list !== 'ul') { closeList(); list='ul'; out.push('<ul>'); } out.push(`<li>${inline(bullet[1])}</li>`); continue; }
      const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (numbered) { if (list !== 'ol') { closeList(); list='ol'; out.push('<ol>'); } out.push(`<li>${inline(numbered[1])}</li>`); continue; }
      const nested = line.match(/^\s{2,}[-*]\s+(.+)$/);
      if (nested) { if (list !== 'ul') { closeList(); list='ul'; out.push('<ul>'); } out.push(`<li>${inline(nested[1])}</li>`); continue; }
      closeList();
      if (/^\\\[|^\\\]|^\$\$/.test(line.trim())) out.push(`<div>${inline(line)}</div>`);
      else out.push(`<p>${inline(line)}</p>`);
    }
    closeList();
    return out.join('');
  }

  function toHtml(text) {
    const source = String(text || '');
    const regex = /```([A-Za-z0-9_+.-]*)\s*\n([\s\S]*?)```/g;
    let html = '', last = 0, match;
    while ((match = regex.exec(source))) {
      html += proseHtml(source.slice(last, match.index));
      const language = (match[1] || 'text').toLowerCase();
      const code = match[2].replace(/\s+$/, '');
      html += `<div class="sb-code-wrap" data-lang="${esc(language)}"><div class="sb-code-head"><span>${esc(language)}</span><div class="sb-code-actions"><button type="button" data-code-action="copy">${esc(tr('Copiar','Copy'))}</button>${language === 'python' ? `<button type="button" data-code-action="download">${esc(tr('Descargar .py','Download .py'))}</button>` : ''}</div></div><pre><code class="sb-code">${esc(code)}</code></pre></div>`;
      last = regex.lastIndex;
    }
    html += proseHtml(source.slice(last));
    return html;
  }

  function loadMathJax() {
    if (window.MathJax?.typesetPromise) return Promise.resolve(window.MathJax);
    if (mathPromise) return mathPromise;
    mathPromise = new Promise(resolve => {
      window.MathJax = window.MathJax || {
        tex: {inlineMath: [['$', '$'], ['\\(', '\\)']], displayMath: [['$$','$$'], ['\\[','\\]']]},
        options: {skipHtmlTags: ['script','noscript','style','textarea','pre','code']},
      };
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js';
      script.async = true;
      script.onload = () => resolve(window.MathJax);
      script.onerror = () => resolve(null);
      document.head.appendChild(script);
    });
    return mathPromise;
  }

  function bindCodeActions(container) {
    container.querySelectorAll('[data-code-action="copy"]').forEach(button => button.onclick = async () => {
      const code = button.closest('.sb-code-wrap')?.querySelector('.sb-code')?.textContent || '';
      try { await navigator.clipboard.writeText(code); button.textContent = tr('Copiado','Copied'); setTimeout(() => button.textContent = tr('Copiar','Copy'), 1200); } catch (_) {}
    });
    container.querySelectorAll('[data-code-action="download"]').forEach(button => button.onclick = () => {
      const code = button.closest('.sb-code-wrap')?.querySelector('.sb-code')?.textContent || '';
      const blob = new Blob([code], {type:'text/x-python;charset=utf-8'});
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'scientificbrain_verification.py'; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 500);
    });
  }

  function render(container, text) {
    if (!container) return;
    const raw = String(text || '');
    container.dataset.sbRendering = '1';
    container.dataset.sbLastRaw = raw;
    container.classList.add('sb-scientific-render');
    container.innerHTML = toHtml(raw);
    bindCodeActions(container);
    if (/[\\$]/.test(raw)) loadMathJax().then(mj => mj?.typesetPromise?.([container]).catch?.(() => {}));
    setTimeout(() => { container.dataset.sbRendering = '0'; }, 0);
  }

  window.SBScientificFormat = {render, toHtml, loadMathJax};

  function watchRich(element) {
    if (!element || element.dataset.sbWatch === '1') return;
    element.dataset.sbWatch = '1';
    const observer = new MutationObserver(() => {
      if (element.dataset.sbRendering === '1') return;
      const raw = element.textContent || '';
      if (raw && raw !== element.dataset.sbLastRaw) render(element, raw);
    });
    observer.observe(element, {childList:true, subtree:true, characterData:true});
    const initial = element.textContent || '';
    if (initial.trim()) render(element, initial);
  }

  function watchDecisions() {
    const box = q('#v18-decisions'); if (!box || box.dataset.sbWatch === '1') return;
    box.dataset.sbWatch = '1';
    const apply = () => box.querySelectorAll('.v18-decision p').forEach(p => {
      if (p.dataset.sbFormatted === '1') return;
      const raw = p.textContent || ''; p.dataset.sbFormatted = '1'; render(p, raw);
    });
    const observer = new MutationObserver(() => { if (box.dataset.sbBusy === '1') return; box.dataset.sbBusy='1'; apply(); setTimeout(()=>box.dataset.sbBusy='0',0); });
    observer.observe(box, {childList:true, subtree:true});
    apply();
  }

  function enhanceManuscriptPreviews() {
    const grid = q('#v18-manuscript-grid'); if (!grid) return;
    grid.querySelectorAll('.v18-manuscript-section').forEach(section => {
      if (section.querySelector('.sb-preview-toggle')) return;
      const textarea = section.querySelector('textarea[data-v18-section]');
      const actions = section.querySelector('.v18-section-actions');
      if (!textarea || !actions) return;
      const button = document.createElement('button'); button.type='button'; button.className='ghost sb-preview-toggle'; button.textContent=tr('Vista LaTeX','LaTeX preview');
      const preview = document.createElement('div'); preview.className='sb-preview hidden';
      actions.appendChild(button); actions.after(preview);
      button.onclick = () => {
        const hidden = preview.classList.toggle('hidden');
        if (!hidden) render(preview, textarea.value);
      };
      textarea.addEventListener('input', () => { if (!preview.classList.contains('hidden')) render(preview, textarea.value); });
    });
  }

  function watchManuscriptGrid() {
    const grid = q('#v18-manuscript-grid'); if (!grid || grid.dataset.sbPreviewWatch === '1') return;
    grid.dataset.sbPreviewWatch='1'; enhanceManuscriptPreviews();
    new MutationObserver(() => enhanceManuscriptPreviews()).observe(grid, {childList:true, subtree:true});
  }

  function sourceCards(references) {
    return (references || []).map(r => `<div class="v14-source"><strong>[${esc(r.number)}]</strong> ${esc(r.reference || r.title || r.paper_id)}</div>`).join('');
  }

  async function askCorpusRich() {
    const f = folder(); const button=q('#v14-ask'); const question=q('#v14-question')?.value?.trim(); const out=q('#v14-corpus-result');
    if (!f?.folder_id || !question || !out || corpusBusy) return;
    corpusBusy=true; button.disabled=true;
    out.innerHTML=`<div class="v14-note">${esc(tr('Recuperando evidencia full-text, ecuaciones, verificaciones cuantitativas y trazabilidad…','Retrieving full-text evidence, equations, quantitative checks and traceability…'))}</div>`;
    try {
      const result=await api('/api/corpus?op=ask',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,question,thread_id:corpusThread,language:lang(),limit:30})});
      corpusThread=result.thread_id||corpusThread;
      const audit=result.citation_audit||{}; const emb=result.retrieval?.embedding_stats||{};
      out.innerHTML=`<div class="sb-v19-badges"><span class="sb-v19-badge ${audit.passed?'ok':'warn'}">${esc(audit.passed?tr('Citas verificadas','Citations verified'):tr('Revisar citas','Review citations'))}</span><span class="sb-v19-badge">${esc(result.references?.length||0)} papers</span><span class="sb-v19-badge">${esc(result.evidence?.length||0)} chunks</span><span class="sb-v19-badge">embedding ${esc(Math.round((emb.coverage||0)*100))}%</span>${result.structured_response?.python_verification?`<span class="sb-v19-badge ok">Python</span>`:''}${(result.structured_response?.equations||[]).length?`<span class="sb-v19-badge ok">LaTeX ${(result.structured_response.equations||[]).length}</span>`:''}</div><div id="sb-v19-corpus-answer" class="v14-output"></div>${result.references?.length?`<h3 style="margin:12px 0 5px">${esc(tr('Referencias utilizadas','References used'))}</h3><div class="v14-sources">${sourceCards(result.references)}</div>`:''}`;
      render(q('#sb-v19-corpus-answer'), result.answer || '');
    } catch (error) { out.innerHTML=`<div class="v14-errors">${esc(error.message||String(error))}</div>`; notify(error.message||String(error),true); }
    finally { corpusBusy=false; button.disabled=false; }
  }

  async function discussRich() {
    const f=folder(); const input=q('#v18-discuss-input'); const button=q('#v18-discuss-send'); const out=q('#v18-discuss-answer');
    const message=input?.value?.trim(); if(!f?.folder_id||!message||!button||!out)return;
    button.disabled=true; button.textContent=tr('Analizando evidencia…','Analyzing evidence…');
    try {
      let searchCount=0;
      if(q('#v18-discuss-web')?.checked){
        const topic=q('#v11-topic')?.value?.trim()||'';
        try {
          const search=await api('/api/research_search',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,project_id:state.session?.project_id||null,query:[topic,message].filter(Boolean).join(' · '),from_year:1990,max_results:16,include_web:true,resolve_open_access:true})});
          state.researchResults=search.results||[]; searchCount=state.researchResults.length; if(typeof renderResearchResults==='function')renderResearchResults();
        } catch(error){ console.warn('v0.19 discovery search',error); }
      }
      const result=await api('/api/collaboration?op=discuss',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,message,agent_id:q('#v18-discuss-agent')?.value||'critical_reviewer',section_key:null,language:lang()})});
      render(out, result.message?.content || result.response || result.answer || ''); input.value='';
      const candidates=q('#v18-show-candidates'); if(candidates){candidates.classList.toggle('v18-hidden',!searchCount); if(searchCount)candidates.textContent=`${tr('Ver candidatos encontrados','View discovered candidates')} (${searchCount})`;}
    }catch(error){render(out,error.message||String(error));notify(error.message||String(error),true)}finally{button.disabled=false;button.textContent=tr('Discutir con ScientificBrain','Discuss with ScientificBrain')}
  }

  function patchActions() {
    const ask=q('#v14-ask'); if(ask && ask.dataset.v19!=='1'){ask.dataset.v19='1';ask.onclick=askCorpusRich}
    const fresh=q('#v14-new-thread'); if(fresh && fresh.dataset.v19!=='1'){fresh.dataset.v19='1';fresh.onclick=()=>{corpusThread=null;const out=q('#v14-corpus-result');if(out)out.innerHTML='';notify(tr('Nueva conversación de corpus.','New corpus conversation.'))}}
    const discuss=q('#v18-discuss-send'); if(discuss && discuss.dataset.v19!=='1'){discuss.dataset.v19='1';discuss.onclick=discussRich}
  }

  function install() {
    styles(); patchActions();
    watchRich(q('#v18-state-art'));
    watchRich(q('#v18-manuscript-result'));
    watchDecisions(); watchManuscriptGrid();
    document.addEventListener('scibrain:languagechange',()=>setTimeout(()=>{patchActions();watchDecisions();enhanceManuscriptPreviews()},30));
    document.addEventListener('click',event=>{
      if(event.target?.closest?.('[data-view="workspace"],[data-view="collab"],[data-view="manuscript"]'))setTimeout(()=>{patchActions();watchRich(q('#v18-state-art'));watchRich(q('#v18-manuscript-result'));watchDecisions();watchManuscriptGrid()},80);
    });
    setTimeout(patchActions,400);
  }

  if(document.readyState==='loading')window.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
