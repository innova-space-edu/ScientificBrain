(() => {
  // Supabase refresh tokens rotate. Simultaneous 401 responses must share one refresh.
  if (typeof refreshAuth === 'function' && !window.__sbRefreshGuardInstalled) {
    window.__sbRefreshGuardInstalled = true;
    const originalRefresh = refreshAuth;
    let inFlight = null;
    refreshAuth = function () {
      if (inFlight) return inFlight;
      inFlight = Promise.resolve().then(() => originalRefresh()).finally(() => { inFlight = null; });
      return inFlight;
    };
  }

  const clearFolderScopedViews = () => {
    const topic = document.querySelector('#collab-topic');
    if (topic) topic.value = '';
    ['#draft-sections','#collab-evidence','#collab-gaps','#collab-chat-log','#map-metrics','#map-nodes','#map-contr-list','#map-hyp-list']
      .forEach(selector => { const node=document.querySelector(selector); if(node) node.innerHTML=''; });
  };

  if (typeof selectFolder === 'function' && !window.__sbFolderGuardInstalled) {
    window.__sbFolderGuardInstalled = true;
    const originalSelectFolder = selectFolder;
    selectFolder = async function (...args) {
      clearFolderScopedViews();
      if (window.state) { state.jobs=[]; state.researchResults=[]; }
      return originalSelectFolder.apply(this, args);
    };
  }
})();
