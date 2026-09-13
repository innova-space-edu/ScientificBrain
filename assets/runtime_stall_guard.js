(() => {
  const STARTUP_GET_TIMEOUT_MS = 18000;
  const AUTH_TIMEOUT_MS = 15000;
  const LONG_GET_TIMEOUT_MS = 90000;
  const WRITE_TIMEOUT_MS = 305000;

  function timeoutError(label, ms) {
    const seconds = Math.round(ms / 1000);
    const error = new Error(`${label} tardó más de ${seconds}s. La interfaz seguirá disponible; vuelve a intentarlo.`);
    error.name = 'ScientificBrainTimeout';
    return error;
  }

  async function timedFetch(url, options = {}, timeoutMs = STARTUP_GET_TIMEOUT_MS, label = 'La solicitud') {
    const controller = new AbortController();
    let externalAbort = null;
    if (options.signal) {
      if (options.signal.aborted) controller.abort(options.signal.reason);
      else {
        externalAbort = () => controller.abort(options.signal.reason);
        options.signal.addEventListener('abort', externalAbort, {once:true});
      }
    }
    const timer = setTimeout(() => controller.abort(timeoutError(label, timeoutMs)), timeoutMs);
    try {
      return await window.fetch(url, {...options, signal: controller.signal});
    } catch (error) {
      if (controller.signal.aborted && !(options.signal && options.signal.aborted)) {
        throw timeoutError(label, timeoutMs);
      }
      throw error;
    } finally {
      clearTimeout(timer);
      if (externalAbort && options.signal) options.signal.removeEventListener('abort', externalAbort);
    }
  }

  function isActive(id) {
    return !!document.querySelector(id)?.classList.contains('active');
  }

  function deferredWorkspaceResponse(url) {
    const value = String(url || '');
    if (!isActive('#view-collab')) {
      if (value.includes('/api/science?') && value.includes('op=research_workspace')) {
        return {document:null, corpus:{}, messages:[], agent_roles:[]};
      }
      if (value.includes('/api/collaboration?') && value.includes('op=research_workspace')) {
        return {document:null, corpus:{}, messages:[], intelligence:{}};
      }
    }
    if (!isActive('#view-map') && value.includes('/api/science?')) {
      const graphOps = ['op=graph_summary','op=graph_nodes','op=contradictions','op=hypotheses'];
      if (graphOps.some(op => value.includes(op))) {
        if (value.includes('op=graph_nodes')) return {nodes:[]};
        if (value.includes('op=contradictions')) return {contradictions:[]};
        if (value.includes('op=hypotheses')) return {competitions:[]};
        return {nodes:0, node_types:{}, papers:0};
      }
    }
    return null;
  }

  if (typeof loadClientConfig === 'function') {
    loadClientConfig = async function() {
      const res = await timedFetch('/api/client_config', {cache:'no-store'}, STARTUP_GET_TIMEOUT_MS, 'La configuración inicial');
      if (!res.ok) throw new Error('No se pudo cargar la configuración de Supabase');
      state.config = await res.json();
      if (!state.config.url || !state.config.publishable_key) {
        throw new Error('SUPABASE_PUBLISHABLE_KEY no está configurada en Vercel');
      }
    };
  }

  if (typeof supabaseAuthFetch === 'function') {
    supabaseAuthFetch = async function(path, options={}) {
      const headers = {'apikey': state.config.publishable_key, 'Content-Type':'application/json', ...(options.headers || {})};
      if (typeof accessToken === 'function' && accessToken()) headers.Authorization = `Bearer ${accessToken()}`;
      return timedFetch(
        state.config.url.replace(/\/$/, '') + path,
        {...options, headers},
        AUTH_TIMEOUT_MS,
        'La autenticación'
      );
    };
  }

  if (typeof api === 'function') {
    api = async function(url, options={}, retry=true) {
      const deferred = deferredWorkspaceResponse(url);
      if (deferred) return deferred;

      const headers = {'Content-Type':'application/json', ...(options.headers || {})};
      if (typeof accessToken === 'function' && accessToken()) headers.Authorization = `Bearer ${accessToken()}`;

      const method = String(options.method || 'GET').toUpperCase();
      const value = String(url || '');
      const startupRead =
        method === 'GET' &&
        ['/api/health','/api/manifest','/api/project_template','/api/folders','/api/library','/api/projects','/api/jobs']
          .some(prefix => value.startsWith(prefix));
      const timeoutMs = method === 'GET'
        ? (startupRead ? STARTUP_GET_TIMEOUT_MS : LONG_GET_TIMEOUT_MS)
        : WRITE_TIMEOUT_MS;

      let res = await timedFetch(url, {...options, headers}, timeoutMs, 'La solicitud a ScientificBrain');
      if (res.status === 401 && retry && typeof refreshAuth === 'function' && await refreshAuth()) {
        headers.Authorization = `Bearer ${accessToken()}`;
        res = await timedFetch(url, {...options, headers}, timeoutMs, 'La solicitud a ScientificBrain');
      }
      let payload;
      try { payload = await res.json(); }
      catch { payload = {error:`HTTP ${res.status}`}; }
      if (!res.ok) throw new Error(payload.detail || payload.message || payload.error || `HTTP ${res.status}`);
      return payload;
    };
  }

  if (typeof resolveCurrentUser === 'function') {
    const originalResolveCurrentUser = resolveCurrentUser;
    resolveCurrentUser = async function() {
      try {
        return await originalResolveCurrentUser();
      } catch (error) {
        console.warn('ScientificBrain auth recovery', error);
        if (typeof setAuthMessage === 'function') {
          setAuthMessage('La sesión tardó demasiado en validarse. Puedes intentar ingresar nuevamente.', true);
        }
        return false;
      }
    };
  }

  if (typeof signIn === 'function') {
    const originalSignIn = signIn;
    signIn = async function() {
      try { return await originalSignIn(); }
      catch (error) {
        console.warn('ScientificBrain sign-in timeout', error);
        if (typeof setAuthMessage === 'function') setAuthMessage(error.message || 'No se pudo iniciar sesión.', true);
      }
    };
  }

  if (typeof signUp === 'function') {
    const originalSignUp = signUp;
    signUp = async function() {
      try { return await originalSignUp(); }
      catch (error) {
        console.warn('ScientificBrain sign-up timeout', error);
        if (typeof setAuthMessage === 'function') setAuthMessage(error.message || 'No se pudo crear la cuenta.', true);
      }
    };
  }

  if (typeof afterAuthentication === 'function') {
    afterAuthentication = async function() {
      document.querySelector('#auth-gate')?.classList.add('hidden');
      const email = state.authUser?.email || 'Authenticated user';
      const box = document.querySelector('#user-box');
      if (box) box.innerHTML = `<strong>${typeof esc === 'function' ? esc(email) : email}</strong><span>${typeof esc === 'function' ? esc(state.authUser?.id || '') : (state.authUser?.id || '')}</span>`;

      if (typeof renderAll === 'function') renderAll();

      const tasks = [
        ['health', typeof loadHealth === 'function' ? loadHealth() : Promise.resolve()],
        ['manifest', typeof loadManifest === 'function' ? loadManifest() : Promise.resolve()],
        ['template', typeof loadTemplate === 'function' ? loadTemplate() : Promise.resolve()],
        ['folders', typeof loadFolders === 'function' ? loadFolders() : Promise.resolve()],
      ];
      const settled = await Promise.allSettled(tasks.map(([,promise]) => promise));
      const failures = settled
        .map((result, index) => ({result, name:tasks[index][0]}))
        .filter(item => item.result.status === 'rejected');

      if (typeof renderAll === 'function') renderAll();
      if (failures.length && typeof toast === 'function') {
        toast(`ScientificBrain cargó en modo parcial. No respondieron: ${failures.map(x=>x.name).join(', ')}.`, true);
      }

      const saved = localStorage.getItem('scibrain_session');
      if (saved && typeof loadSession === 'function') {
        const input = document.querySelector('#session-input');
        if (input) input.value = saved;
        loadSession(saved).catch(error => console.warn('ScientificBrain session restore', error));
      }
    };
  }

  window.addEventListener('DOMContentLoaded', () => {
    if (typeof selectFolder === 'function' && typeof state === 'object') {
      selectFolder = async function(id) {
        state.selectedFolderId = id;
        localStorage.setItem('scibrain_selected_folder', id);
        if (typeof renderFolders === 'function') renderFolders();
        state.researchResults = [];
        try {
          if (typeof loadLibrary === 'function') await loadLibrary();
        } catch (error) {
          console.warn('ScientificBrain library switch', error);
          if (typeof toast === 'function') toast(`No se pudo cargar la biblioteca: ${error.message}`, true);
        }
        if (typeof loadProjects === 'function') loadProjects().catch(()=>{});
        if (typeof refreshJobs === 'function') refreshJobs().catch(()=>{});
        document.dispatchEvent(new CustomEvent('scibrain:folderchange', {detail:{folderId:id}}));
        return typeof selectedFolder === 'function' ? selectedFolder() : null;
      };
    }

    setTimeout(() => {
      if (state?.authUser && !state?.health && typeof toast === 'function') {
        toast('La carga inicial está tardando. La interfaz sigue activa; algunos servicios pueden estar iniciando en Vercel.', true);
      }
    }, 12000);
  });
})();
