(() => {
  const modules = [
    '/assets/runtime_stall_guard.js',
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

  let started = false;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = false;
      script.dataset.scibrainModule = src;
      script.onload = () => resolve(src);
      script.onerror = () => reject(new Error(`No se pudo cargar ${src}`));
      document.body.appendChild(script);
    });
  }

  async function loadEnhancements() {
    if (started) return;
    started = true;
    const failures = [];
    for (const src of modules) {
      try {
        await loadScript(src);
      } catch (error) {
        failures.push({src, error: error?.message || String(error)});
        console.error('ScientificBrain module load failed', src, error);
      }
    }
    window.__SCIBRAIN_MODULES_READY__ = failures.length === 0;
    window.__SCIBRAIN_MODULE_FAILURES__ = failures;
    document.dispatchEvent(new CustomEvent('scibrain:modulesready', {detail:{failures}}));
    if (failures.length && typeof toast === 'function') {
      toast(`ScientificBrain cargó parcialmente. Fallaron ${failures.length} módulo(s).`, true);
    }
  }

  function startAfterBaseApp() {
    setTimeout(() => loadEnhancements().catch(error => console.error('ScientificBrain enhancement loader', error)), 0);
  }

  if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', startAfterBaseApp, {once:true});
  } else {
    startAfterBaseApp();
  }
})();
