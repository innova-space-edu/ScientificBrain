(() => {
  const modules = [
    '/assets/ux_flow_base.js',
    '/assets/adaptive_jobs.js',
    '/assets/adaptive_science.js',
    '/assets/adaptive_agents.js',
    '/assets/runtime_repair.js',
    '/assets/research_workspace_v11.js',
    '/assets/research_workspace_v12.js',
    '/assets/research_workspace_v14.js',
    '/assets/research_workspace_v15.js',
    '/assets/research_workspace_v16.js',
    '/assets/research_workspace_v17.js',
    '/assets/research_flow_v18.js',
  ];

  const NativeMutationObserver = window.MutationObserver;
  let started = false;
  let finished = false;
  let restoringFolderId = null;

  function isAuthenticated() {
    try {
      return typeof accessToken === 'function' && !!accessToken() && typeof state !== 'undefined' && !!state.authUser;
    } catch (_) {
      return false;
    }
  }

  function consentIsBlocking() {
    const modal = document.querySelector('#consent-modal');
    return !!modal && !modal.classList.contains('hidden');
  }

  async function readSupabaseRows(path) {
    if (typeof supabaseAuthFetch !== 'function') return [];
    let response = await supabaseAuthFetch(path, {method:'GET'});
    if (response.status === 401 && typeof refreshAuth === 'function' && await refreshAuth()) {
      response = await supabaseAuthFetch(path, {method:'GET'});
    }
    if (!response.ok) throw new Error(`Supabase recovery HTTP ${response.status}`);
    const rows = await response.json();
    return Array.isArray(rows) ? rows : [];
  }

  async function latestContextRows(folderId=null) {
    const owner = typeof state !== 'undefined' ? state.authUser?.id : null;
    const ownerFilter = owner ? `&owner_id=eq.${encodeURIComponent(owner)}` : '';
    const folderFilter = folderId ? `&folder_id=eq.${encodeURIComponent(folderId)}` : '';
    const [sessions, projects, documents] = await Promise.all([
      readSupabaseRows(`/rest/v1/scibrain_states?select=session_id,folder_id,updated_at${ownerFilter}${folderFilter}&order=updated_at.desc&limit=1`),
      readSupabaseRows(`/rest/v1/scibrain_projects?select=project_id,folder_id,definition,updated_at${ownerFilter}${folderFilter}&order=updated_at.desc&limit=1`),
      readSupabaseRows(`/rest/v1/scibrain_research_documents?select=document_id,folder_id,topic,status,revision,updated_at${ownerFilter}${folderFilter}&order=updated_at.desc&limit=1`),
    ]);
    return {session:sessions[0] || null, project:projects[0] || null, document:documents[0] || null};
  }

  function newestFolderFromContext(context) {
    const candidates = [context?.session, context?.project, context?.document]
      .filter(row => row?.folder_id)
      .map(row => ({folder_id:row.folder_id, timestamp:Date.parse(row.updated_at || 0) || 0}));
    candidates.sort((a,b) => b.timestamp - a.timestamp);
    return candidates[0]?.folder_id || null;
  }

  async function activateFolderForRecovery(folderId) {
    if (!folderId || typeof state === 'undefined' || !Array.isArray(state.folders)) return false;
    if (!state.folders.some(folder => folder.folder_id === folderId)) return false;
    if (state.selectedFolderId === folderId) return true;
    state.selectedFolderId = folderId;
    localStorage.setItem('scibrain_selected_folder', folderId);
    if (typeof renderFolders === 'function') renderFolders();
    if (typeof loadLibrary === 'function') await loadLibrary();
    return true;
  }

  async function restorePersistentContext({allowFolderSwitch=false}={}) {
    if (!isAuthenticated() || typeof selectedFolder !== 'function') return null;
    let folder = selectedFolder();
    if (!folder?.folder_id) return null;
    try {
      if (typeof state !== 'undefined' && state.session?.folder_id === folder.folder_id) {
        return {restored:false, already_active:true};
      }
    } catch (_) {}
    if (restoringFolderId === folder.folder_id) return null;
    restoringFolderId = folder.folder_id;
    try {
      if (allowFolderSwitch && !localStorage.getItem('scibrain_selected_folder')) {
        const globalContext = await latestContextRows(null);
        const recoveryFolderId = newestFolderFromContext(globalContext);
        if (recoveryFolderId && recoveryFolderId !== folder.folder_id) {
          await activateFolderForRecovery(recoveryFolderId);
          folder = selectedFolder();
        }
      }

      if (!folder?.folder_id) return null;
      const context = await latestContextRows(folder.folder_id);
      window.__SCIBRAIN_RESUME_CONTEXT__ = context;
      if (context.document) window.__SCIBRAIN_RECOVERED_DOCUMENT__ = context.document;

      if (context.session?.session_id && typeof loadSession === 'function') {
        await loadSession(context.session.session_id);
        if (typeof toast === 'function') toast('Sesión recuperada desde Supabase.');
        return {...context, restored:true, reconstructed:false};
      }

      if (context.project?.definition && typeof api === 'function') {
        const paperIds = Array.isArray(state.library)
          ? state.library.map(paper => paper.canonical_id).filter(Boolean)
          : [];
        const created = await api('/api/projects', {
          method:'POST',
          body:JSON.stringify({
            project:context.project.definition,
            folder_id:folder.folder_id,
            paper_ids:paperIds,
          }),
        });
        if (created?.session_id && typeof loadSession === 'function') {
          await loadSession(created.session_id);
          if (typeof toast === 'function') toast('Sesión reconstruida desde el proyecto persistente de Supabase.');
          return {...context, restored:true, reconstructed:true, session_id:created.session_id};
        }
      }

      return {...context, restored:!!context.document, reconstructed:false};
    } catch (error) {
      console.warn('ScientificBrain persistent context recovery failed', error);
      return null;
    } finally {
      restoringFolderId = null;
    }
  }

  function restoreWithDeadline(options={}, timeoutMs=7000) {
    return Promise.race([
      restorePersistentContext(options),
      new Promise(resolve => setTimeout(() => resolve(null), timeoutMs)),
    ]);
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[data-scibrain-module="${src}"]`)) return resolve(src);
      const script = document.createElement('script');
      script.src = src;
      script.async = false;
      script.dataset.scibrainModule = src;
      script.onload = () => resolve(src);
      script.onerror = () => reject(new Error(`No se pudo cargar ${src}`));
      document.body.appendChild(script);
    });
  }

  function suppressBroadBodyObservers() {
    if (!NativeMutationObserver || window.MutationObserver !== NativeMutationObserver) return () => {};
    class ScientificBrainScopedObserver extends NativeMutationObserver {
      observe(target, options = {}) {
        if (target === document.body && options.childList && options.subtree) {
          console.warn('ScientificBrain bloqueó un observer global para evitar ciclos de renderizado.');
          return;
        }
        return super.observe(target, options);
      }
    }
    window.MutationObserver = ScientificBrainScopedObserver;
    return () => { window.MutationObserver = NativeMutationObserver; };
  }

  async function loadEnhancements() {
    if (started || finished || !isAuthenticated() || consentIsBlocking()) return;
    started = true;
    const failures = [];
    const restoreObserver = suppressBroadBodyObservers();
    try {
      for (const src of modules) {
        try {
          await loadScript(src);
        } catch (error) {
          failures.push({src, error: error?.message || String(error)});
          console.error('ScientificBrain module load failed', src, error);
        }
      }
    } finally {
      restoreObserver();
      started = false;
      finished = true;
    }
    window.__SCIBRAIN_MODULES_READY__ = failures.length === 0;
    window.__SCIBRAIN_MODULE_FAILURES__ = failures;
    document.dispatchEvent(new CustomEvent('scibrain:modulesready', {detail:{failures}}));
    if (failures.length && typeof toast === 'function') {
      toast(`ScientificBrain cargó parcialmente. Fallaron ${failures.length} módulo(s).`, true);
    }
  }

  function requestEnhancements() {
    if (!isAuthenticated() || consentIsBlocking()) return;
    setTimeout(() => loadEnhancements().catch(error => console.error('ScientificBrain enhancement loader', error)), 0);
  }

  function installFolderResumeHook() {
    if (typeof selectFolder !== 'function' || window.__SB_PERSISTENT_FOLDER_HOOK__) return;
    window.__SB_PERSISTENT_FOLDER_HOOK__ = true;
    const baseSelectFolder = selectFolder;
    selectFolder = async function(...args) {
      const result = await baseSelectFolder.apply(this, args);
      await restoreWithDeadline({allowFolderSwitch:false});
      return result;
    };
  }

  installFolderResumeHook();

  if (typeof afterAuthentication === 'function' && !window.__SB_ADVANCED_AUTH_HOOK__) {
    window.__SB_ADVANCED_AUTH_HOOK__ = true;
    const baseAfterAuthentication = afterAuthentication;
    afterAuthentication = async function(...args) {
      const hadSavedFolder = !!localStorage.getItem('scibrain_selected_folder');
      const result = await baseAfterAuthentication.apply(this, args);
      await restoreWithDeadline({allowFolderSwitch:!hadSavedFolder});
      requestEnhancements();
      return result;
    };
  }

  function installConsentWatcher() {
    const modal = document.querySelector('#consent-modal');
    if (!modal || !NativeMutationObserver) return;
    const observer = new NativeMutationObserver(() => {
      if (modal.classList.contains('hidden')) {
        restoreWithDeadline({allowFolderSwitch:false}).finally(requestEnhancements);
      }
    });
    observer.observe(modal, {attributes:true, attributeFilter:['class']});
  }

  function boot() {
    installConsentWatcher();
    if (isAuthenticated() && !consentIsBlocking()) {
      restoreWithDeadline({allowFolderSwitch:false}).finally(requestEnhancements);
    }
  }

  if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', boot, {once:true});
  } else {
    boot();
  }
})();
