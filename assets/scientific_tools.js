(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  const state = {
    config: null,
    status: null,
    toolkit: null,
    workers: null,
    gcp: null,
    gcpSetup: null,
    nvidiaModels: null,
    modelCatalog: null,
    lastPreparedJob: null,
    errors: {},
    currentView: "overview",
  };

  const VIEW_META = {
    overview: ["Estado general", "Resumen científico"],
    router: ["Análisis de régimen", "Router físico"],
    montecarlo: ["Incertidumbre", "Monte Carlo / UQ"],
    nvidia: ["IA científica", "NVIDIA"],
    prepare: ["Physics Job", "Preparar simulación"],
    solvers: ["Motores científicos", "Simuladores"],
    google: ["Cloud compute", "Google Cloud"],
    results: ["Ingesta", "Resultados"],
    skills: ["Toolkit", "Physics Skills"],
    diagnostics: ["Avanzado", "Diagnóstico"],
  };

  function authSession() {
    try { return JSON.parse(localStorage.getItem("scibrain_supabase_session") || "null"); }
    catch { return null; }
  }
  function saveSession(v) {
    if (v) localStorage.setItem("scibrain_supabase_session", JSON.stringify(v));
    else localStorage.removeItem("scibrain_supabase_session");
  }
  function token() { return authSession()?.access_token || ""; }

  async function loadConfig() {
    const r = await fetch("/api/client_config", { cache: "no-store" });
    if (!r.ok) throw new Error("No se pudo cargar la configuración");
    state.config = await r.json();
  }

  async function refresh() {
    const s = authSession();
    if (!s?.refresh_token || !state.config?.url) return false;
    const r = await fetch(
      state.config.url.replace(/\/$/, "") + "/auth/v1/token?grant_type=refresh_token",
      {
        method: "POST",
        headers: { apikey: state.config.publishable_key, "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: s.refresh_token }),
      }
    );
    if (!r.ok) { saveSession(null); return false; }
    saveSession(await r.json());
    return true;
  }

  async function api(url, options = {}, retry = true) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (token()) headers.Authorization = "Bearer " + token();
    let r = await fetch(url, { ...options, headers });
    if (r.status === 401 && retry && await refresh()) {
      headers.Authorization = "Bearer " + token();
      r = await fetch(url, { ...options, headers });
    }
    let payload;
    try { payload = await r.json(); } catch { payload = { error: "HTTP " + r.status }; }
    if (!r.ok) throw new Error(payload.detail || payload.error || payload.message || ("HTTP " + r.status));
    return payload;
  }

  function setView(name, updateHash = true) {
    if (!VIEW_META[name]) name = "overview";
    state.currentView = name;
    $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
    $$(".science-view").forEach((panel) => panel.classList.toggle("active", panel.dataset.viewPanel === name));
    const [eyebrow, title] = VIEW_META[name];
    $("#view-eyebrow").textContent = eyebrow;
    $("#view-title").textContent = title;
    localStorage.setItem("scibrain_science_view", name);
    if (updateHash) history.replaceState(null, "", "#" + name);
    $(".content-scroll")?.scrollTo({ top: 0, behavior: "smooth" });
  }

  function setSummary(el, text, kind = "neutral") {
    if (!el) return;
    el.textContent = text;
    el.className = "summary-state " + kind;
  }

  function statePill(el, text, kind = "neutral") {
    if (!el) return;
    el.textContent = text;
    el.className = "state-pill " + kind;
  }

  function row(label, value, kind = "neutral") {
    return '<div class="status-row"><span>' + label + '</span><strong class="mini-state ' + kind + '">' + value + '</strong></div>';
  }

  function showResult(title, data) {
    const card = $("#result-card");
    const pre = $("#tools-output");
    if (!card || !pre) return;
    $("#result-title").textContent = title;
    pre.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    card.hidden = false;
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function hideResult() {
    const card = $("#result-card");
    if (card) card.hidden = true;
  }

  function prettyError(e) { return e?.message || String(e || "Error desconocido"); }

  function renderNvidia() {
    const s = state.status || {};
    const modelState = state.nvidiaModels || {};
    const connected = !!s.hosted_api_configured;
    const warnings = s.configuration_warnings || [];
    const caps = s.capabilities || [];
    const env = s.runtime_environment || modelState.runtime_environment || "local";

    setSummary($("#summary-nvidia"), connected ? "Conectado" : "No disponible aquí", connected ? "good" : "warn");
    $("#summary-nvidia-detail").textContent = connected ? ("Modelo activo: " + (s.text_model || "—")) : ("NVIDIA_API_KEY no disponible en " + env);
    statePill($("#nvidia-view-state"), connected ? "Conectado" : "Sin API key en este entorno", connected ? "good" : "warn");
    $("#run-nvidia-chat").disabled = !connected;
    $("#nav-nvidia-dot").className = "nav-dot " + (connected ? "good" : "warn");

    const models = modelState.models || (s.text_model ? [s.text_model] : []);
    const modelSelect = $("#nvidia-model-select");
    modelSelect.innerHTML = models.length
      ? models.map((m) => '<option value="' + m + '"' + (m === (modelState.current_model || s.text_model) ? " selected" : "") + ">" + m + "</option>").join("")
      : '<option value="">Sin modelos disponibles en este deployment</option>';
    modelSelect.disabled = !connected;

    const customCaps = caps.filter((x) => !["nvidia-chat","local-nim-chat"].includes(x.name));
    const select = $("#capability-select");
    select.innerHTML = customCaps.length
      ? customCaps.map((x) => '<option value="' + x.name + '">' + x.name + " · " + x.domain + "</option>").join("")
      : '<option value="">Sin endpoints científicos adicionales</option>';
    $("#run-capability").disabled = !customCaps.length;

    const summaries = s.capability_summary || [];
    $("#nvidia-capability-cards").innerHTML = summaries.map((item) =>
      '<article class="capability-card ' + (item.enabled ? "enabled" : "disabled") + '"><div><strong>' + item.label + '</strong><span>' + (item.enabled ? "Disponible" : "No configurado") + '</span></div><p>' + item.description + '</p></article>'
    ).join("");
    $("#nvidia-runtime-note").innerHTML = connected
      ? '<strong>API alojada activa.</strong> El selector de modelos se carga desde <code>/v1/models</code> cuando NVIDIA lo expone.'
      : '<strong>Este deployment no ve NVIDIA_API_KEY.</strong> Si la clave está en Production, un Preview seguirá apareciendo pendiente hasta asignarla también al entorno Preview.';

    $("#nvidia-status").innerHTML = [
      row("Entorno", env, "neutral"),
      row("API NVIDIA", connected ? "Conectada" : "Sin clave en este entorno", connected ? "good" : "warn"),
      row("Modelo configurado", s.text_model || modelState.current_model || "—", "neutral"),
      row("Modelos visibles", String(models.length), models.length ? "good" : "neutral"),
      row("NGC", s.ngc_key_configured ? "Configurado" : "Opcional", s.ngc_key_configured ? "good" : "neutral"),
      row("NIM local/remoto", s.local_nim_configured ? "Configurado" : "Opcional", s.local_nim_configured ? "good" : "neutral"),
      row("Endpoints científicos registrados", String(customCaps.length), customCaps.length ? "good" : "neutral"),
    ].join("");

    $("#nvidia-warnings").innerHTML = warnings.length
      ? "<strong>Advertencias de capacidades</strong><ul>" + warnings.map((w) => "<li>" + w + "</li>").join("") + "</ul>"
      : "Sin advertencias de configuración.";
  }

  function renderGoogle() {
    const setup = state.gcpSetup || {};
    const wif = setup.workload_identity || {};
    const gcp = state.gcp || {};
    const profiles = gcp.profiles || [];
    const runtimeEnv = setup.runtime_environment || "local";
    const primaryVarsReady = (setup.variables || []).slice(0, 3).every((v) => v.configured);
    const profileNames = new Set(profiles.map((p) => p.name));
    const total = 6;
    const count = profiles.length;

    if (wif.available) {
      setSummary($("#summary-google"), "Autenticado", "good");
      $("#summary-google-detail").textContent = "Vercel OIDC → Google WIF";
      statePill($("#google-view-state"), "Autenticado", "good");
      $("#nav-google-dot").className = "nav-dot good";
    } else if (wif.configured) {
      setSummary($("#summary-google"), "WIF configurado", "warn");
      $("#summary-google-detail").textContent = "Esperando token OIDC de runtime";
      statePill($("#google-view-state"), "Esperando token", "warn");
      $("#nav-google-dot").className = "nav-dot warn";
    } else {
      setSummary($("#summary-google"), "Pendiente", "warn");
      $("#summary-google-detail").textContent = "Falta completar WIF";
      statePill($("#google-view-state"), "Pendiente", "warn");
      $("#nav-google-dot").className = "nav-dot warn";
    }

    setSummary($("#summary-execution"), count + "/" + total + " perfiles", count === total ? "good" : count ? "warn" : "neutral");
    $("#summary-execution-detail").textContent = count === total ? "Solvers listos para Batch" : "Imágenes/perfiles por crear";

    $$(".solver-card").forEach((card) => {
      const ready = profileNames.has(card.dataset.solver);
      const badge = card.querySelector(".solver-status");
      badge.textContent = ready ? "Cloud listo" : "Imagen pendiente";
      badge.className = "solver-status " + (ready ? "good" : "pending");
      card.classList.toggle("cloud-ready", ready);
    });

    $("#preview-gcp-job").disabled = !profiles.length;
    $("#submit-gcp-job").disabled = !gcp.configured;
    $("#job-cloud-note").textContent = profiles.length
      ? "Hay perfiles cloud disponibles. La ejecución depende del solver seleccionado."
      : "Todavía no hay imágenes/perfiles de solver en Artifact Registry. Puedes preparar el manifiesto, pero no enviarlo aún.";

    $("#gcp-status").innerHTML = [
      row("Entorno Vercel", runtimeEnv, "neutral"),
      row("Integración Batch", gcp.configured ? "Lista" : "Pendiente", gcp.configured ? "good" : "warn"),
      row("Región", gcp.region || "—", "neutral"),
      row("Perfiles de solver", String(count), count ? "good" : "neutral"),
      row("Autenticación", gcp.auth_mode || "—", wif.available ? "good" : "neutral"),
    ].join("");

    const setupVars = setup.variables || [];
    $("#gcp-setup-plan").innerHTML =
      setupVars.map((v) => row(v.name, v.configured ? "Configurado" : "Pendiente", v.configured ? "good" : "warn")).join("") +
      row("Vercel OIDC / WIF", wif.available ? "Disponible" : (wif.configured ? "Esperando token" : "Pendiente"), wif.available ? "good" : "warn") +
      row("FLASH privado", "Soportado", "good");

    $("#gcp-env-note").innerHTML = runtimeEnv === "preview"
      ? '<strong>Entorno Preview.</strong> Las variables de Production no se copian automáticamente. Este Preview necesita las mismas variables no secretas asignadas a Preview y un subject WIF autorizado para <code>environment:preview</code>.'
      : '<strong>Entorno ' + runtimeEnv + '.</strong> La identidad OIDC se valida específicamente para este entorno.';

    const steps = [
      { done: primaryVarsReady, title: "Variables Google Cloud", text: primaryVarsReady ? "Proyecto, bucket y service account están visibles en este entorno." : (runtimeEnv === "preview" ? "Asignar las variables SCIBRAIN_GCP_* también al entorno Preview de Vercel." : "Completar las variables SCIBRAIN_GCP_* del deployment.") },
      { done: !!wif.available, title: "Vercel → Google WIF", text: wif.available ? "Autenticación temporal funcionando." : (wif.configured ? "La configuración WIF existe; falta token/autorización para el subject de este entorno." : "Completar Workload Identity Federation para este entorno.") },
      { done: count === total, title: "Imágenes de ejecución", text: count === total ? "Los seis motores tienen perfil cloud." : "Crear FLASH, WarpX, PIConGPU, EDIPIC-2D, Geant4 y PhysicsNeMo en Artifact Registry." },
      { done: !!gcp.configured, title: "Google Batch", text: gcp.configured ? "Ejecución cloud habilitada." : "Activar Batch después de crear los perfiles." },
    ];

    $("#setup-steps").innerHTML = steps.map((s, i) =>
      '<div class="setup-step ' + (s.done ? "done" : "todo") + '">' +
        '<span class="step-number">' + (s.done ? "✓" : i + 1) + "</span>" +
        "<div><strong>" + s.title + "</strong><p>" + s.text + "</p></div>" +
      "</div>"
    ).join("");

    const next = steps.find((s) => !s.done) || { title: "Sistema listo", text: "Puedes ejecutar campañas científicas desde ScientificBrain." };
    $("#next-milestone").textContent = next.title;
    $("#next-milestone-detail").textContent = next.text;
  }

  function renderModelCatalog() {
    const catalog = state.modelCatalog?.solvers || {};
    $$(".solver-card").forEach((card) => {
      const spec = catalog[card.dataset.solver];
      const target = card.querySelector(".solver-models");
      if (!target) return;
      target.innerHTML = spec?.models?.length
        ? spec.models.map((m) => '<span title="' + m.description.replace(/"/g, "&quot;") + '">' + m.label + "</span>").join("")
        : '<span>Catálogo pendiente</span>';
    });
    updateJobModelOptions();
  }

  function updateJobModelOptions() {
    const solver = $("#job-solver")?.value;
    const spec = state.modelCatalog?.solvers?.[solver];
    if (!spec) return;
    const modelSelect = $("#job-model");
    modelSelect.innerHTML = spec.models.map((m) => '<option value="' + m.id + '">' + m.label + "</option>").join("");
    modelSelect.value = spec.default_model;
    const actionSelect = $("#job-action");
    const previousAction = actionSelect.value;
    actionSelect.innerHTML = (spec.actions || []).map((a) => '<option value="' + a + '">' + a + "</option>").join("");
    if ((spec.actions || []).includes(previousAction)) actionSelect.value = previousAction;
    const selected = spec.models.find((m) => m.id === modelSelect.value);
    $("#job-model-help").textContent = selected?.description || "";
    state.lastPreparedJob = null;
  }

  function updateJobModelHelp() {
    const solver = $("#job-solver")?.value;
    const spec = state.modelCatalog?.solvers?.[solver];
    const selected = spec?.models?.find((m) => m.id === $("#job-model")?.value);
    $("#job-model-help").textContent = selected?.description || "";
    state.lastPreparedJob = null;
  }

  function renderSkills() {
    const implemented = state.toolkit?.implemented_extensions || [];
    $("#implemented-extensions").innerHTML = implemented.map((x) => "<span>" + x + "</span>").join("") || "<span>Toolkit no cargado</span>";

    const workers = state.workers?.workers || [];
    $("#worker-status").innerHTML = row("Workers conectados", String(workers.length), workers.length ? "good" : "neutral");
    $("#workers-list").innerHTML = workers.length
      ? workers.map((w) =>
          '<article class="worker-card"><strong>' + w.name + "</strong><p>" +
          (w.description || "Worker científico") + "</p><small>" +
          ((w.solvers || []).join(" · ") || "sin solver declarado") + "</small></article>"
        ).join("")
      : '<div class="empty-state">Sin workers externos configurados. Google Batch será el backend principal cuando las imágenes estén listas.</div>';
  }

  function renderErrors() {
    const entries = Object.entries(state.errors).filter(([, v]) => v);
    $("#load-errors").innerHTML = entries.length
      ? "<ul>" + entries.map(([k, v]) => "<li><strong>" + k + ":</strong> " + v + "</li>").join("") + "</ul>"
      : "Sin errores de carga.";
  }

  function render() {
    renderNvidia();
    renderGoogle();
    renderModelCatalog();
    renderSkills();
    renderErrors();
  }

  async function loadStatus() {
    const requests = [
      ["nvidia", "/api/science?op=nvidia_status"],
      ["toolkit", "/api/science?op=physics_toolkit"],
      ["workers", "/api/science?op=physics_workers"],
      ["gcp", "/api/science?op=gcp_batch_status"],
      ["gcpSetup", "/api/science?op=gcp_setup_plan"],
      ["nvidiaModels", "/api/science?op=nvidia_models"],
      ["modelCatalog", "/api/science?op=physics_model_catalog"],
    ];

    const results = await Promise.allSettled(requests.map(([, url]) => api(url)));
    results.forEach((result, i) => {
      const key = requests[i][0];
      if (result.status === "fulfilled") {
        state.errors[key] = null;
        if (key === "nvidia") state.status = result.value;
        else state[key] = result.value;
      } else {
        state.errors[key] = prettyError(result.reason);
        if (key === "nvidia") state.status = { capabilities: [], configuration_warnings: [prettyError(result.reason)] };
        else if (key === "toolkit") state.toolkit = { implemented_extensions: [] };
        else if (key === "workers") state.workers = { workers: [] };
        else if (key === "modelCatalog") state.modelCatalog = { solvers: {} };
        else if (key === "nvidiaModels") state.nvidiaModels = { models: [] };
        else state[key] = {};
      }
    });
    render();
  }

  async function load() {
    await loadConfig();
    const hashView = location.hash.replace("#", "");
    const savedView = localStorage.getItem("scibrain_science_view");
    setView(VIEW_META[hashView] ? hashView : (VIEW_META[savedView] ? savedView : "overview"), false);

    if (!token()) {
      $("#next-milestone").textContent = "Inicia sesión";
      $("#next-milestone-detail").textContent = "Las herramientas científicas requieren una sesión de ScientificBrain.";
      return;
    }

    try {
      const health = await api("/api/health");
      $("#tools-version").textContent = "v" + health.version;
    } catch {}

    await loadStatus();
  }

  const MC_PARAM_SCHEMAS = {
    normal: [["mean","Media"],["sd","Desv. estándar"]],
    uniform: [["low","Mínimo"],["high","Máximo"]],
    lognormal: [["mu","μ log"],["sigma","σ log"]],
    triangular: [["low","Mínimo"],["high","Máximo"],["mode","Moda"]],
    fixed: [["value","Valor fijo"]],
  };

  function renderMcParams(row, values = {}) {
    const dist = row.querySelector(".mc-dist").value;
    const target = row.querySelector(".mc-params");
    target.innerHTML = (MC_PARAM_SCHEMAS[dist] || []).map(([key,label]) =>
      '<label>' + label + '<input class="mc-param" data-key="' + key + '" type="number" step="any" value="' + (values[key] ?? "") + '"/></label>'
    ).join("");
  }

  function addMcVariable(initial = {}) {
    const row = document.createElement("div");
    row.className = "mc-variable-row";
    row.innerHTML = '<label>Variable<input class="mc-name" value="' + (initial.name || "") + '" placeholder="Ej. B, Te, ne"/></label>' +
      '<label>Distribución<select class="mc-dist"><option value="normal">Normal</option><option value="uniform">Uniforme</option><option value="lognormal">Lognormal</option><option value="triangular">Triangular</option><option value="fixed">Fija</option></select></label>' +
      '<div class="mc-params"></div><button type="button" class="mc-remove ghost" title="Eliminar variable">Eliminar</button>';
    $("#mc-variables").appendChild(row);
    row.querySelector(".mc-dist").value = initial.dist || "normal";
    renderMcParams(row, initial);
    row.querySelector(".mc-dist").addEventListener("change", () => renderMcParams(row));
    row.querySelector(".mc-remove").addEventListener("click", () => row.remove());
  }

  function collectMonteCarloDistributions() {
    const distributions = {};
    $$(".mc-variable-row").forEach((row) => {
      const name = row.querySelector(".mc-name").value.trim();
      if (!name) throw new Error("Cada variable Monte Carlo necesita un nombre");
      if (distributions[name]) throw new Error("Variable Monte Carlo repetida: " + name);
      const spec = { dist: row.querySelector(".mc-dist").value };
      row.querySelectorAll(".mc-param").forEach((input) => {
        if (input.value.trim() === "") throw new Error("Falta " + input.dataset.key + " para " + name);
        spec[input.dataset.key] = Number(input.value);
      });
      distributions[name] = spec;
    });
    if (!Object.keys(distributions).length) throw new Error("Agrega al menos una variable Monte Carlo");
    return distributions;
  }

  function syncMonteCarloJson() {
    try { $("#mc-spec").value = JSON.stringify(collectMonteCarloDistributions(), null, 2); }
    catch (e) { showResult("Monte Carlo", prettyError(e)); }
  }

  function initMonteCarloBuilder() {
    if ($("#mc-variables")?.children.length) return;
    addMcVariable({name:"B",dist:"normal",mean:2.0,sd:0.1});
    addMcVariable({name:"Te",dist:"uniform",low:8,high:12});
    syncMonteCarloJson();
  }

  function num(id) {
    const v = $(id).value.trim();
    return v === "" ? null : Number(v);
  }

  async function prepareJob() {
    try {
      let parameters;
      try { parameters = JSON.parse($("#job-parameters").value || "{}"); }
      catch { throw new Error("Parámetros JSON inválidos"); }

      const payload = {
        solver: $("#job-solver").value,
        action: $("#job-action").value,
        model: $("#job-model").value.trim(),
        input_artifact: $("#job-input").value.trim(),
        parameters,
        resources: { gpus: Number($("#job-gpus").value || 0), cpus: 4, nodes: 1, memory_gb: 8, wall_minutes: 60 },
      };

      const result = await api("/api/science?op=physics_prepare_job", { method: "POST", body: JSON.stringify(payload) });
      state.lastPreparedJob = result;
      $("#result-job-id").value = result.job_id || "";
      showResult("Job científico preparado", result);
    } catch (e) { showResult("Error al preparar job", prettyError(e)); }
  }

  async function ensurePreparedJob() {
    if (state.lastPreparedJob) return state.lastPreparedJob;
    await prepareJob();
    if (!state.lastPreparedJob) throw new Error("Primero prepara un job científico");
    return state.lastPreparedJob;
  }

  async function runRouter() {
    try {
      const payload = {
        ne: num("#r-ne"), B: num("#r-B"), Te_ev: num("#r-Te"), Ti_ev: num("#r-Ti"),
        L: num("#r-L"), U: num("#r-U"), A: num("#r-A"), Z: num("#r-Z"), mfp: num("#r-mfp"),
        needs_electron_kinetics: $("#r-electron").checked,
        low_temperature_2d: $("#r-lowt").checked,
        particle_through_matter: $("#r-matter").checked,
      };
      showResult("Router físico", await api("/api/science?op=physics_route", { method: "POST", body: JSON.stringify(payload) }));
    } catch (e) { showResult("Error del router", prettyError(e)); }
  }

  async function runMonteCarlo() {
    try {
      let distributions;
      if ($("#mc-use-json").checked) {
        try { distributions = JSON.parse($("#mc-spec").value || "{}"); }
        catch { throw new Error("JSON avanzado inválido"); }
      } else {
        distributions = collectMonteCarloDistributions();
        $("#mc-spec").value = JSON.stringify(distributions, null, 2);
      }
      const result = await api("/api/science?op=physics_monte_carlo", {
        method: "POST",
        body: JSON.stringify({ distributions, n: Number($("#mc-n").value), seed: Number($("#mc-seed").value) }),
      });
      showResult("Monte Carlo / UQ", { ...result, samples: result.samples.slice(0, 20), preview_only: result.samples.length > 20 });
    } catch (e) { showResult("Error Monte Carlo", prettyError(e)); }
  }

  async function runNvidia() {
    try {
      const prompt = $("#nvidia-prompt").value.trim();
      if (!prompt) throw new Error("Escribe una consulta");
      showResult("NVIDIA", await api("/api/science?op=nvidia_invoke", {
        method: "POST",
        body: JSON.stringify({ capability: "nvidia-chat", input: { prompt, model: $("#nvidia-model-select").value } }),
      }));
    } catch (e) { showResult("Error NVIDIA", prettyError(e)); }
  }

  async function runCapability() {
    try {
      const capability = $("#capability-select").value;
      if (!capability) throw new Error("No hay una capacidad adicional seleccionada");
      let input;
      try { input = JSON.parse($("#capability-input").value || "{}"); }
      catch { throw new Error("Entrada JSON inválida"); }
      showResult(capability, await api("/api/science?op=nvidia_invoke", {
        method: "POST",
        body: JSON.stringify({ capability, input }),
      }));
    } catch (e) { showResult("Error de capacidad NVIDIA", prettyError(e)); }
  }

  async function testGcpAuth() {
    try {
      const result = await api("/api/science?op=gcp_auth_probe");
      showResult("Prueba Vercel → Google WIF", result);
      await loadStatus();
    } catch (e) { showResult("Error Google WIF", prettyError(e)); }
  }

  async function previewGcp() {
    try {
      const job = await ensurePreparedJob();
      showResult("Vista previa Google Batch", await api("/api/science?op=gcp_batch_preview", {
        method: "POST", body: JSON.stringify({ job }),
      }));
    } catch (e) { showResult("Google Batch", prettyError(e)); }
  }

  async function submitGcp() {
    try {
      const job = await ensurePreparedJob();
      showResult("Job enviado a Google Cloud", await api("/api/science?op=gcp_batch_submit", {
        method: "POST", body: JSON.stringify({ job }),
      }));
    } catch (e) { showResult("Error Google Cloud", prettyError(e)); }
  }

  async function resultJobId() {
    const id = $("#result-job-id")?.value.trim() || state.lastPreparedJob?.job_id || "";
    if (!id) throw new Error("Falta ScientificBrain job ID");
    return id;
  }

  async function listOutputs() {
    try {
      const id = await resultJobId();
      showResult("Archivos del job", await api("/api/science?op=gcp_output_list&scientific_job_id=" + encodeURIComponent(id)));
    } catch (e) { showResult("Error de resultados", prettyError(e)); }
  }

  async function getManifest() {
    try {
      const id = await resultJobId();
      showResult("Manifiesto científico", await api("/api/science?op=gcp_output_manifest&scientific_job_id=" + encodeURIComponent(id)));
    } catch (e) { showResult("Error de manifiesto", prettyError(e)); }
  }

  function bind() {
    $$(".nav-item").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
    $$("[data-nav-target]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.navTarget)));

    const actions = {
      "#refresh-status": loadStatus,
      "#run-physics-router": runRouter,
      "#run-monte-carlo": runMonteCarlo,
      "#mc-add-variable": () => addMcVariable({dist:"normal"}),
      "#mc-sync-json": syncMonteCarloJson,
      "#run-nvidia-chat": runNvidia,
      "#run-capability": runCapability,
      "#prepare-physics-job": prepareJob,
      "#test-gcp-auth": testGcpAuth,
      "#preview-gcp-job": previewGcp,
      "#submit-gcp-job": submitGcp,
      "#list-gcp-outputs": listOutputs,
      "#get-gcp-manifest": getManifest,
    };
    Object.entries(actions).forEach(([selector, fn]) => $(selector)?.addEventListener("click", fn));

    $("#job-solver")?.addEventListener("change", updateJobModelOptions);
    $("#job-model")?.addEventListener("change", updateJobModelHelp);
    initMonteCarloBuilder();

    $("#clear-tools-output")?.addEventListener("click", () => {
      $("#tools-output").textContent = "";
      hideResult();
    });
    $("#close-result")?.addEventListener("click", hideResult);
    window.addEventListener("hashchange", () => {
      const view = location.hash.replace("#", "");
      if (VIEW_META[view]) setView(view, false);
    });
  }

  window.addEventListener("DOMContentLoaded", () => {
    bind();
    load().catch((e) => showResult("Inicialización", prettyError(e)));
  });
})();