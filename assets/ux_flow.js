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
  ];

  const NativeMutationObserver = window.MutationObserver;
  let started = false;
  let finished = false;

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

  if (typeof afterAuthentication === 'function' && !window.__SB_ADVANCED_AUTH_HOOK__) {
    window.__SB_ADVANCED_AUTH_HOOK__ = true;
    const baseAfterAuthentication = afterAuthentication;
    afterAuthentication = async function(...args) {
      const result = await baseAfterAuthentication.apply(this, args);
      requestEnhancements();
      return result;
    };
  }

  function installConsentWatcher() {
    const modal = document.querySelector('#consent-modal');
    if (!modal || !NativeMutationObserver) return;
    const observer = new NativeMutationObserver(() => {
      if (modal.classList.contains('hidden')) requestEnhancements();
    });
    observer.observe(modal, {attributes:true, attributeFilter:['class']});
  }

  function boot() {
    installConsentWatcher();
    requestEnhancements();
  }

  if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', boot, {once:true});
  } else {
    boot();
  }
})();
