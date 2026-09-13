(() => {
  const i18n = () => window.SBI18N;
  const t = (key, fallback='') => i18n()?.t(key, fallback) || fallback || key;
  let consentRequired = false;
  let queueRunning = false;

  const originals = {
    signIn: typeof signIn === 'function' ? signIn : null,
    signUp: typeof signUp === 'function' ? signUp : null,
    afterAuthentication: typeof afterAuthentication === 'function' ? afterAuthentication : null,
    setView: typeof setView === 'function' ? setView : null,
    selectFolder: typeof selectFolder === 'function' ? selectFolder : null,
    loadLibrary: typeof loadLibrary === 'function' ? loadLibrary : null,
    renderLibrary: typeof renderLibrary === 'function' ? renderLibrary : null,
    enqueueReviews: typeof enqueueReviews === 'function' ? enqueueReviews : null,
    renderJobs: typeof renderJobs === 'function' ? renderJobs : null,
    toast: typeof toast === 'function' ? toast : null,
  };

  function translatedToast(message, bad=false) {
    const text = i18n()?.free(message) || message;
    return originals.toast ? originals.toast(text, bad) : undefined;
  }
  if (originals.toast) toast = translatedToast;

  function modal(show=true, forced=false) {
    consentRequired = forced;
    const el = document.querySelector('#consent-modal');
    if (!el) return;
    el.classList.toggle('hidden', !show);
    const close = document.querySelector('#close-consent');
    const cancel = document.querySelector('#cancel-consent');
    if (close) close.style.display = forced ? 'none' : '';
    if (cancel) cancel.style.display = forced ? 'none' : '';
    if (show) {
      const master = document.querySelector('#consent-master');
      if (master) master.checked = false;
      i18n()?.apply(el);
    }
  }

  async function consentStatus() {
    try { return await api('/api/consent'); }
    catch (e) { log?.('Consent status error', e.message); throw e; }
  }

  async function ensureConsentGate() {
    if (!accessToken?.()) return false;
    const status = await consentStatus();
    if (status.accepted) { modal(false); return true; }
    modal(true, true);
    return false;
  }

  async function acceptConsent() {
    const master = document.querySelector('#consent-master');
    if (!master?.checked) {
      translatedToast(t('consent_master','Debes aceptar las condiciones para continuar.'), true);
      return;
    }
    if (!accessToken?.()) {
      const activeSignup = document.querySelector('#auth-signup')?.classList.contains('active');
      const box = document.querySelector(activeSignup ? '#signup-terms' : '#signin-terms');
      if (box) box.checked = true;
      modal(false);
      return;
    }
    try {
      const payload = {
        terms_accepted:true,
        ai_use_accepted:true,
        data_processing_accepted:true,
        cybersecurity_acknowledged:true,
        scientific_responsibility_acknowledged:true,
      };
      const result = await api('/api/consent',{method:'POST',body:JSON.stringify(payload)});
      if (!result.accepted) throw new Error('Consent was not recorded');
      consentRequired = false;
      modal(false);
      translatedToast(i18n()?.language()==='es' ? 'Condiciones aceptadas.' : 'Consent accepted.');
    } catch (e) {
      translatedToast((i18n()?.language()==='es' ? 'No se pudo registrar la aceptación: ' : 'Could not record consent: ') + e.message, true);
    }
  }

  if (originals.afterAuthentication) {
    afterAuthentication = async function() {
      await originals.afterAuthentication();
      try { await ensureConsentGate(); }
      catch (e) { modal(true, true); }
    };
  }

  if (originals.signIn) {
    signIn = async function() {
      if (!document.querySelector('#signin-terms')?.checked) {
        setAuthMessage?.(i18n()?.language()==='es' ? 'Debes aceptar las condiciones de uso, IA, datos y ciberseguridad.' : 'You must accept the platform, AI, data and cybersecurity conditions.', true);
        modal(true, false);
        return;
      }
      return originals.signIn();
    };
  }

  if (originals.signUp) {
    signUp = async function() {
      if (!document.querySelector('#signup-terms')?.checked) {
        setAuthMessage?.(i18n()?.language()==='es' ? 'Debes aceptar las condiciones antes de registrarte.' : 'You must accept the conditions before creating an account.', true);
        modal(true, false);
        return;
      }
      return originals.signUp();
    };
  }

  const viewKeys = {overview:'nav_overview',workspace:'nav_workspace',definition:'nav_definition',session:'nav_session',literature:'nav_research_agent',protocol:'nav_protocol',projects:'nav_projects'};
  if (originals.setView) {
    setView = function(name) {
      originals.setView(name);
      const title = document.querySelector('#page-title');
      if (title && viewKeys[name]) title.textContent = t(viewKeys[name], title.textContent);
    };
  }

  async function syncActiveFolderContext() {
    const folder = selectedFolder?.();
    if (!folder || !accessToken?.()) return null;
    const body = {folder_id:folder.folder_id};
    if (state.session?.folder_id === folder.folder_id) body.session_id = state.session.session_id;
    try {
      const result = await api('/api/sync_context',{method:'POST',body:JSON.stringify(body)});
      if (state.session?.folder_id === folder.folder_id) {
        state.session.candidate_paper_ids = result.paper_ids || [];
        const allowed = new Set(result.paper_ids || []);
        state.session.selected_paper_ids = (state.session.selected_paper_ids || []).filter(id => allowed.has(id));
      }
      const badge = document.querySelector('#active-folder-badge');
      if (badge) badge.title = `corpus ${result.corpus_hash || ''}`;
      return result;
    } catch (e) {
      log?.('Folder context sync', e.message);
      return null;
    }
  }

  if (originals.selectFolder) {
    selectFolder = async function(id) {
      if (state.session && state.session.folder_id && state.session.folder_id !== id) {
        state.session = null;
        state.artifacts = [];
        localStorage.removeItem('scibrain_session');
        const input = document.querySelector('#session-input'); if (input) input.value = '';
        renderSession?.();
        translatedToast(i18n()?.language()==='es' ? 'Se cambió de carpeta: la sesión anterior se cerró para evitar mezclar contextos.' : 'Folder changed: the previous session was cleared to avoid mixing contexts.');
      }
      const result = await originals.selectFolder(id);
      await syncActiveFolderContext();
      return result;
    };
  }

  if (originals.loadLibrary) {
    loadLibrary = async function() {
      const result = await originals.loadLibrary();
      await syncActiveFolderContext();
      enhanceLibraryRows();
      updateReviewProgress();
      return result;
    };
  }

  if (originals.renderLibrary) {
    renderLibrary = function() {
      originals.renderLibrary();
      enhanceLibraryRows();
      updateReviewProgress();
      i18n()?.apply(document.querySelector('#view-workspace') || document);
    };
  }

  function updateReviewProgress() {
    const full = (state.library || []).filter(p => p.review_depth === 'full_text_reviewed').length;
    const total = (state.library || []).length;
    const el = document.querySelector('#review-progress-summary');
    if (el) {
      const lang=i18n()?.language();
      el.textContent = lang==='en' ? `${full} full-text reviewed · ${total} in folder` : lang==='pt' ? `${full} revisados em texto completo · ${total} na pasta` : lang==='fr' ? `${full} analysés en texte intégral · ${total} dans le dossier` : `${full} analizados a texto completo · ${total} en la carpeta`;
    }
    const next = document.querySelector('#process-next-review');
    const all = document.querySelector('#process-review-queue');
    const pending = (state.jobs || []).some(j => j.job_type === 'review_paper' && ['pending','failed'].includes(j.status));
    if (next) next.disabled = !state.session || !pending || queueRunning;
    if (all) all.disabled = !state.session || !pending;
  }

  function enhanceLibraryRows() {
    const rows = [...document.querySelectorAll('#paper-list .paper-row')];
    rows.forEach(row => {
      const deleteButton = row.querySelector('.delete-paper');
      const itemId = deleteButton?.dataset.item;
      const paper = (state.library || []).find(p => p.item_id === itemId);
      if (!paper) return;
      const meta = row.querySelector('.paper-meta:last-of-type') || row.querySelector('.paper-meta');
      if (meta && !row.querySelector('.paper-review-badge')) {
        const badge = document.createElement('span');
        badge.className = 'paper-review-badge' + (paper.review_depth === 'full_text_reviewed' ? ' done' : '');
        badge.textContent = paper.review_depth === 'full_text_reviewed' ? (i18n()?.language()==='es'?'texto completo revisado':'full text reviewed') : (i18n()?.language()==='es'?'pendiente de análisis profundo':'deep review pending');
        meta.after(badge);
      }
      if (!paper.storage_path && !row.querySelector('.attach-pdf')) {
        const button = document.createElement('button');
        button.className = 'secondary attach-pdf';
        button.dataset.item = itemId;
        button.textContent = i18n()?.language()==='es' ? 'Adjuntar PDF' : i18n()?.language()==='pt' ? 'Anexar PDF' : i18n()?.language()==='fr' ? 'Joindre le PDF' : 'Attach PDF';
        button.onclick = () => choosePdfForPaper(paper, button);
        row.querySelector('.paper-actions')?.prepend(button);
      }
    });
  }

  function choosePdfForPaper(paper, button) {
    const input = document.createElement('input');
    input.type='file'; input.accept='application/pdf'; input.hidden=true;
    input.onchange = async () => { const file=input.files?.[0]; if (file) await attachPdf(paper,file,button); input.remove(); };
    document.body.appendChild(input); input.click();
  }

  async function attachPdf(paper, file, button) {
    const folder = selectedFolder?.();
    if (!folder) return;
    if (file.size > 100*1024*1024) return translatedToast(i18n()?.language()==='es' ? 'El PDF supera 100 MB.' : 'PDF exceeds 100 MB.', true);
    const safe = file.name.replace(/[^a-zA-Z0-9._-]+/g,'_');
    const storagePath = `${state.authUser.id}/${folder.folder_id}/${crypto.randomUUID()}-${safe}`;
    const encoded = storagePath.split('/').map(encodeURIComponent).join('/');
    button.disabled=true; button.textContent=i18n()?.language()==='es'?'Subiendo…':'Uploading…';
    try {
      const upload = await fetch(`${state.config.url.replace(/\/$/,'')}/storage/v1/object/scibrain-papers/${encoded}`,{method:'POST',headers:{apikey:state.config.publishable_key,Authorization:`Bearer ${accessToken()}`,'Content-Type':'application/pdf','x-upsert':'false'},body:file});
      if (!upload.ok) throw new Error(await upload.text());
      await api(`/api/attach_pdf?item_id=${encodeURIComponent(paper.item_id)}`,{method:'PATCH',body:JSON.stringify({storage_path:storagePath,original_filename:file.name,mime_type:'application/pdf',file_size_bytes:file.size})});
      translatedToast(i18n()?.language()==='es' ? 'PDF adjuntado al registro existente.' : 'PDF attached to the existing record.');
      await loadLibrary();
    } catch(e) {
      translatedToast((i18n()?.language()==='es'?'No se pudo adjuntar el PDF: ':'Could not attach PDF: ')+e.message,true);
      button.disabled=false;
    }
  }

  if (originals.enqueueReviews) {
    enqueueReviews = async function() {
      if (!state.session) return;
      const paperIds = (state.library || []).filter(p => p.canonical_id && p.review_depth !== 'full_text_reviewed').map(p=>p.canonical_id);
      if (!paperIds.length) return translatedToast(i18n()?.language()==='es'?'No hay papers pendientes de análisis profundo.':'No papers are pending deep review.');
      try {
        const parent = await api('/api/jobs',{method:'POST',body:JSON.stringify({session_id:state.session.session_id,job_type:'enqueue_selected_reviews',payload:{limit:100,paper_ids:paperIds}})});
        await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:parent.job_id})});
        translatedToast(i18n()?.language()==='es'?`${paperIds.length} papers preparados para análisis incremental.`:`${paperIds.length} papers queued for incremental review.`);
        await refreshJobs();
      } catch(e) { translatedToast((i18n()?.language()==='es'?'No se pudo preparar la cola: ':'Could not prepare queue: ')+e.message,true); }
    };
  }

  if (originals.renderJobs) {
    renderJobs = function() {
      originals.renderJobs();
      updateReviewProgress();
      i18n()?.apply(document.querySelector('#view-literature') || document);
    };
  }

  async function processNextReview() {
    await refreshJobs();
    const job = (state.jobs || []).find(j => j.job_type === 'review_paper' && ['pending','failed'].includes(j.status));
    if (!job) { translatedToast(i18n()?.language()==='es'?'No quedan análisis pendientes.':'No pending reviews remain.'); return false; }
    try {
      await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:job.job_id})});
      await loadLibrary();
      await refreshJobs();
      translatedToast(i18n()?.language()==='es'?'Paper analizado.':'Paper reviewed.');
      return true;
    } catch(e) {
      await refreshJobs();
      translatedToast((i18n()?.language()==='es'?'El análisis se detuvo: ':'Review stopped: ')+e.message,true);
      return false;
    }
  }

  async function processReviewQueue() {
    if (queueRunning) { queueRunning=false; return; }
    queueRunning=true;
    const button=document.querySelector('#process-review-queue');
    if(button){button.classList.add('queue-running');button.textContent=i18n()?.language()==='es'?'Detener cola':'Stop queue';}
    try {
      let processed=0;
      while(queueRunning && processed<100) {
        await refreshJobs();
        const pending=(state.jobs||[]).some(j=>j.job_type==='review_paper'&&['pending','failed'].includes(j.status));
        if(!pending) break;
        const ok=await processNextReview();
        if(!ok) break;
        processed++;
      }
      if(processed) translatedToast(i18n()?.language()==='es'?`Procesamiento incremental: ${processed} papers completados.`:`Incremental processing: ${processed} papers completed.`);
    } finally {
      queueRunning=false;
      if(button){button.classList.remove('queue-running');button.textContent=t('process_queue','Procesar cola');}
      updateReviewProgress();
    }
  }

  document.addEventListener('scibrain:languagechange', () => {
    renderFolderContext?.(); renderLibrary?.(); renderSession?.(); renderJobs?.();
    const active = document.querySelector('.nav.active')?.dataset.view || 'overview';
    setView?.(active);
  });

  window.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.open-consent').forEach(b => b.addEventListener('click', () => modal(true,false)));
    document.querySelector('#close-consent')?.addEventListener('click', () => { if(!consentRequired) modal(false); });
    document.querySelector('#cancel-consent')?.addEventListener('click', async () => { if(consentRequired) await signOut?.(); else modal(false); });
    document.querySelector('#accept-consent')?.addEventListener('click', acceptConsent);
    document.querySelector('#process-next-review')?.addEventListener('click', processNextReview);
    document.querySelector('#process-review-queue')?.addEventListener('click', processReviewQueue);
    document.querySelector('#signin-terms')?.addEventListener('change', e => { if(e.target.checked) modal(true,false); });
    document.querySelector('#signup-terms')?.addEventListener('change', e => { if(e.target.checked) modal(true,false); });
    i18n()?.apply(document);
  });
})();
