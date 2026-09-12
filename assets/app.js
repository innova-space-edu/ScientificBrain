const state = {
  config: null,
  auth: null,
  authUser: null,
  manifest: null,
  health: null,
  session: null,
  artifacts: [],
  jobs: [],
  folders: [],
  selectedFolderId: null,
  library: [],
  researchResults: []
};

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const safeUrl = value => { try { const u = new URL(String(value)); return /^https?:$/.test(u.protocol) ? u.href : ''; } catch { return ''; } };
const prettyName = x => String(x || '').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());

function toast(msg, bad=false) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast show' + (bad ? ' bad' : '');
  clearTimeout(window.__toast);
  window.__toast = setTimeout(() => el.className = 'toast', 3600);
}

function log(label, data) {
  const el = $('#execution-log');
  if (!el) return;
  const ts = new Date().toLocaleTimeString();
  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  el.textContent += `\n\n[${ts}] ${label}\n${text}`;
  el.scrollTop = el.scrollHeight;
}

function authSession() {
  if (state.auth) return state.auth;
  try { return JSON.parse(localStorage.getItem('scibrain_supabase_session') || 'null'); }
  catch { return null; }
}

function saveAuthSession(session) {
  state.auth = session;
  if (session) localStorage.setItem('scibrain_supabase_session', JSON.stringify(session));
  else localStorage.removeItem('scibrain_supabase_session');
}

function accessToken() { return authSession()?.access_token || ''; }

async function loadClientConfig() {
  const res = await fetch('/api/client_config', {cache:'no-store'});
  if (!res.ok) throw new Error('Could not load Supabase client configuration');
  state.config = await res.json();
  if (!state.config.url || !state.config.publishable_key) {
    throw new Error('SUPABASE_PUBLISHABLE_KEY is not configured in Vercel');
  }
}

async function supabaseAuthFetch(path, options={}) {
  const headers = {'apikey': state.config.publishable_key, 'Content-Type':'application/json', ...(options.headers || {})};
  if (accessToken()) headers.Authorization = `Bearer ${accessToken()}`;
  return fetch(state.config.url.replace(/\/$/,'') + path, {...options, headers});
}

async function refreshAuth() {
  const session = authSession();
  if (!session?.refresh_token) return false;
  const res = await supabaseAuthFetch('/auth/v1/token?grant_type=refresh_token', {
    method:'POST', body:JSON.stringify({refresh_token: session.refresh_token})
  });
  if (!res.ok) { saveAuthSession(null); return false; }
  const next = await res.json();
  saveAuthSession(next);
  state.authUser = next.user || state.authUser;
  return true;
}

async function resolveCurrentUser() {
  if (!accessToken()) return false;
  let res = await supabaseAuthFetch('/auth/v1/user');
  if (res.status === 401 && await refreshAuth()) res = await supabaseAuthFetch('/auth/v1/user');
  if (!res.ok) { saveAuthSession(null); state.authUser = null; return false; }
  state.authUser = await res.json();
  return true;
}

async function signIn() {
  const email = $('#signin-email').value.trim();
  const password = $('#signin-password').value;
  if (!email || !password) return setAuthMessage('Email and password are required.', true);
  setAuthMessage('Signing in…');
  const res = await supabaseAuthFetch('/auth/v1/token?grant_type=password', {
    method:'POST', body:JSON.stringify({email,password})
  });
  const payload = await res.json().catch(()=>({}));
  if (!res.ok) return setAuthMessage(payload.msg || payload.error_description || payload.message || 'Sign in failed.', true);
  saveAuthSession(payload);
  state.authUser = payload.user;
  await afterAuthentication();
}

async function signUp() {
  const display_name = $('#signup-name').value.trim();
  const email = $('#signup-email').value.trim();
  const password = $('#signup-password').value;
  if (!email || password.length < 6) return setAuthMessage('Use a valid email and a password of at least 6 characters.', true);
  setAuthMessage('Creating account…');
  const res = await supabaseAuthFetch('/auth/v1/signup', {
    method:'POST', body:JSON.stringify({email,password,data:{display_name}})
  });
  const payload = await res.json().catch(()=>({}));
  if (!res.ok) return setAuthMessage(payload.msg || payload.error_description || payload.message || 'Account creation failed.', true);
  if (payload.access_token) {
    saveAuthSession(payload); state.authUser = payload.user; await afterAuthentication();
  } else {
    setAuthMessage('Account created. Check your email to confirm the account, then sign in.');
    showAuthPane('signin');
    $('#signin-email').value = email;
  }
}

async function signOut() {
  try { if (accessToken()) await supabaseAuthFetch('/auth/v1/logout', {method:'POST'}); } catch {}
  saveAuthSession(null); state.authUser = null; state.session = null; state.folders = []; state.library = [];
  localStorage.removeItem('scibrain_selected_folder');
  $('#auth-gate').classList.remove('hidden');
  $('#user-box').innerHTML = '<strong>Not signed in</strong><span>Supabase Auth</span>';
  setAuthMessage('Signed out.');
}

function setAuthMessage(text, bad=false) {
  const el = $('#auth-message'); el.textContent = text; el.style.color = bad ? '#b42318' : '#667085';
}

function showAuthPane(name) {
  $('#auth-signin').classList.toggle('active', name === 'signin');
  $('#auth-signup').classList.toggle('active', name === 'signup');
  $('#auth-tab-signin').className = name === 'signin' ? 'primary' : 'ghost';
  $('#auth-tab-signup').className = name === 'signup' ? 'primary' : 'ghost';
}

async function api(url, options={}, retry=true) {
  const headers = {'Content-Type':'application/json', ...(options.headers || {})};
  if (accessToken()) headers.Authorization = `Bearer ${accessToken()}`;
  let res = await fetch(url, {...options, headers});
  if (res.status === 401 && retry && await refreshAuth()) {
    headers.Authorization = `Bearer ${accessToken()}`;
    res = await fetch(url, {...options, headers});
  }
  let payload; try { payload = await res.json(); } catch { payload = {error:`HTTP ${res.status}`}; }
  if (!res.ok) throw new Error(payload.detail || payload.message || payload.error || `HTTP ${res.status}`);
  return payload;
}

function setView(name) {
  $$('.view').forEach(x => x.classList.remove('active'));
  $$('.nav').forEach(x => x.classList.toggle('active', x.dataset.view === name));
  const target = $(`#view-${name}`); if (target) target.classList.add('active');
  $('#page-title').textContent = ({overview:'Overview',workspace:'Workspace',definition:'Project definition',session:'Research session',literature:'Research Agent',protocol:'Protocol',projects:'Projects'})[name] || name;
  if (name === 'projects') loadProjects().catch(()=>{});
  if (name === 'literature') refreshJobs().catch(()=>{});
}

function bind() {
  $$('.nav').forEach(b => b.onclick = () => setView(b.dataset.view));
  $$('[data-jump]').forEach(b => b.onclick = () => setView(b.dataset.jump));
  $('#auth-tab-signin').onclick = () => showAuthPane('signin');
  $('#auth-tab-signup').onclick = () => showAuthPane('signup');
  $('#signin-button').onclick = signIn;
  $('#signup-button').onclick = signUp;
  $('#signout-button').onclick = signOut;
  $('#load-template').onclick = loadTemplate;
  $('#validate-project').onclick = validateProject;
  $('#create-project').onclick = createProject;
  $('#load-session').onclick = () => loadSession($('#session-input').value.trim());
  $('#validate-stage').onclick = validateStage;
  $('#add-artifact').onclick = addArtifact;
  $('#clear-log').onclick = () => $('#execution-log').textContent = '';
  $('#refresh-projects').onclick = loadProjects;
  $('#refresh-jobs').onclick = refreshJobs;
  $('#enqueue-reviews').onclick = enqueueReviews;
  $('#refresh-folders').onclick = loadFolders;
  $('#create-folder').onclick = createFolder;
  $('#rename-folder').onclick = renameFolder;
  $('#edit-folder').onclick = editFolder;
  $('#paper-files').onchange = () => $('#upload-papers').disabled = !selectedFolder() || !$('#paper-files').files.length;
  $('#upload-papers').onclick = uploadPapers;
  $('#research-search').onclick = researchSearch;
}

async function init() {
  bind();
  try { await loadClientConfig(); }
  catch (e) { setAuthMessage(e.message, true); return; }
  if (await resolveCurrentUser()) await afterAuthentication();
  else $('#auth-gate').classList.remove('hidden');
}

async function afterAuthentication() {
  $('#auth-gate').classList.add('hidden');
  const email = state.authUser?.email || 'Authenticated user';
  $('#user-box').innerHTML = `<strong>${esc(email)}</strong><span>${esc(state.authUser?.id || '')}</span>`;
  await Promise.allSettled([loadHealth(), loadManifest(), loadTemplate(), loadFolders()]);
  const saved = localStorage.getItem('scibrain_session');
  if (saved) { $('#session-input').value = saved; await loadSession(saved).catch(()=>{}); }
  renderAll();
}

async function loadHealth() {
  try {
    state.health = await api('/api/health');
    $('#version-badge').textContent = 'v' + state.health.version;
    const providers = state.health.configured_providers || [];
    $('#provider-dot').className = 'dot ' + (providers.length ? 'ok' : 'bad');
    $('#provider-label').textContent = providers.length ? `${providers.length} cloud provider${providers.length>1?'s':''}` : 'No provider configured';
    const p = state.health.persistence || {};
    $('#storage-dot').className = 'dot ' + ((p.persistent || state.config?.url) ? 'ok' : 'bad');
    $('#storage-label').textContent = 'Supabase user storage';
    $('#security-dot').className = 'dot ok';
    $('#security-label').textContent = 'Supabase Auth + RLS';
    renderHealth();
  } catch(e) { toast('Health check failed: ' + e.message, true); }
}

function renderHealth() {
  if (!state.health) return;
  $('#provider-order').innerHTML = (state.health.provider_order || []).map((p,i)=>`<span class="chip">${i+1}. ${esc(prettyName(p))}</span>`).join('');
}

async function loadManifest() {
  try { state.manifest = await api('/api/manifest'); renderManifest(); }
  catch(e) { toast('Protocol manifest failed: '+e.message,true); }
}

function renderManifest() {
  if (!state.manifest) return;
  const m = state.manifest;
  $('#metric-agents').textContent = m.agents.length;
  $('#metric-stages').textContent = m.stages.length;
  $('#metric-rules').textContent = m.hard_rules.length;
  $('#agent-count').textContent = `${m.agents.length} agents`;
  $('#hard-rules').innerHTML = m.hard_rules.slice(0,6).map(r=>`<li>${esc(prettyName(r))}</li>`).join('');
  $('#overview-protocol').innerHTML = m.stages.map((s,i)=>`<div class="timeline-step"><strong>${i+1}. ${esc(prettyName(s.id))}</strong><span>${s.gates.length} gate${s.gates.length!==1?'s':''}</span></div>`).join('');
  $('#protocol-list').innerHTML = m.stages.map((s,i)=>`<div class="protocol-card"><span class="num">STAGE ${String(i+1).padStart(2,'0')}</span><h3>${esc(prettyName(s.id))}</h3><p>${esc(s.completion)}</p><code>Artifacts: ${esc(s.required_artifacts.join(', '))}</code><code>Gates: ${esc(s.gates.join(', '))}</code></div>`).join('');
  $('#agent-registry').innerHTML = m.agents.map(a=>`<div class="agent-table-row"><strong>${esc(prettyName(a.id))}</strong><span>${esc(prettyName(a.stage))}</span><span>${esc(prettyName(a.task))}</span><span>${esc(a.purpose)}</span></div>`).join('');
  renderSession();
}

async function loadTemplate() {
  try { const tpl = await api('/api/project_template'); $('#project-json').value = JSON.stringify(tpl,null,2); $('#validation-status').className='status-box neutral'; $('#validation-status').textContent='Template loaded — not validated'; $('#validation-details').innerHTML=''; }
  catch(e) { toast('Template failed: '+e.message,true); }
}

async function loadFolders() {
  const r = await api('/api/folders');
  state.folders = r.folders || [];
  const saved = localStorage.getItem('scibrain_selected_folder');
  if (!state.selectedFolderId && saved && state.folders.some(f=>f.folder_id===saved)) state.selectedFolderId = saved;
  if (!state.selectedFolderId && state.folders.length) state.selectedFolderId = state.folders[0].folder_id;
  renderFolders();
  if (state.selectedFolderId) await loadLibrary(); else renderFolderContext();
}

function folderDepth(folder) {
  let depth=0, p=folder.parent_id, guard=0;
  while (p && guard++<10) { const parent=state.folders.find(f=>f.folder_id===p); if(!parent)break; depth++; p=parent.parent_id; }
  return Math.min(depth,3);
}

function renderFolders() {
  const box = $('#folder-list');
  $('#folder-parent').innerHTML = '<option value="">Root</option>' + state.folders.map(f=>`<option value="${esc(f.folder_id)}">${'— '.repeat(folderDepth(f))}${esc(f.name)}</option>`).join('');
  if (!state.folders.length) { box.className='folder-list empty'; box.textContent='Create your first research folder.'; renderFolderContext(); return; }
  box.className='folder-list';
  box.innerHTML = state.folders.map(f=>`<div class="folder-item folder-depth-${folderDepth(f)} ${f.folder_id===state.selectedFolderId?'active':''}" data-folder="${esc(f.folder_id)}"><div><strong>${esc(f.name)}</strong><small>${esc([f.year,f.research_line,f.area].filter(Boolean).join(' · ') || 'Unclassified')}</small></div><span class="pill">${f.paper_target||100}</span></div>`).join('');
  $$('.folder-item').forEach(el=>el.onclick=()=>selectFolder(el.dataset.folder));
  renderFolderContext();
}

function selectedFolder() { return state.folders.find(f=>f.folder_id===state.selectedFolderId) || null; }

async function selectFolder(id) {
  state.selectedFolderId = id;
  localStorage.setItem('scibrain_selected_folder', id);
  renderFolders();
  await loadLibrary();
  loadProjects().catch(()=>{});
  refreshJobs().catch(()=>{});
}

function renderFolderContext() {
  const folder = selectedFolder();
  const text = folder ? `${folder.name}${folder.year?' · '+folder.year:''}${folder.research_line?' · '+folder.research_line:''}${folder.area?' · '+folder.area:''}` : 'No research folder selected';
  $('#active-folder-badge').textContent = text;
  ['overview-folder-context','definition-folder-context','research-folder-context','projects-folder-context'].forEach(id=>{ const el=$('#'+id); if(el) el.textContent = folder ? `Active folder: ${text}. Scientific context is restricted to this folder.` : 'Select a research folder before working.'; });
  $('#selected-folder-title').textContent = folder?.name || 'Select a folder';
  $('#selected-folder-meta').textContent = folder ? [folder.year,folder.research_line,folder.area].filter(Boolean).join(' · ') || 'No metadata' : 'A folder defines the active scientific context.';
  $('#rename-folder').disabled = !folder;
  $('#edit-folder').disabled = !folder;
  $('#research-search').disabled = !folder;
  $('#create-project').disabled = !folder;
  $('#upload-papers').disabled = !folder || !$('#paper-files').files.length;
}

async function createFolder() {
  const payload = {
    name: $('#folder-name').value.trim(),
    year: $('#folder-year').value ? Number($('#folder-year').value) : null,
    research_line: $('#folder-line').value.trim() || null,
    area: $('#folder-area').value.trim() || null,
    parent_id: $('#folder-parent').value || null,
    paper_target: Number($('#folder-target').value || 100)
  };
  try { const r=await api('/api/folders',{method:'POST',body:JSON.stringify(payload)}); state.selectedFolderId=r.folder.folder_id; localStorage.setItem('scibrain_selected_folder',state.selectedFolderId); toast('Folder created'); await loadFolders(); }
  catch(e){ toast('Create folder failed: '+e.message,true); }
}

async function renameFolder() {
  const folder=selectedFolder(); if(!folder)return;
  const name=prompt('New folder name',folder.name); if(!name||!name.trim())return;
  try{await api('/api/folders?folder_id='+encodeURIComponent(folder.folder_id),{method:'PATCH',body:JSON.stringify({name:name.trim()})});toast('Folder renamed');await loadFolders();}catch(e){toast('Rename failed: '+e.message,true)}
}

async function editFolder() {
  const folder=selectedFolder(); if(!folder)return;
  const year=prompt('Year (blank for none)',folder.year||''); if(year===null)return;
  const research_line=prompt('Research line',folder.research_line||''); if(research_line===null)return;
  const area=prompt('Area',folder.area||''); if(area===null)return;
  const paper_target=prompt('Paper target',folder.paper_target||100); if(paper_target===null)return;
  try{await api('/api/folders?folder_id='+encodeURIComponent(folder.folder_id),{method:'PATCH',body:JSON.stringify({year:year?Number(year):null,research_line:research_line||null,area:area||null,paper_target:Number(paper_target||100)})});toast('Folder metadata updated');await loadFolders();}catch(e){toast('Update failed: '+e.message,true)}
}

async function loadLibrary() {
  const folder=selectedFolder(); if(!folder){state.library=[];renderLibrary();return;}
  const r=await api('/api/library?folder_id='+encodeURIComponent(folder.folder_id));
  state.library=r.papers||[];
  renderLibrary(); renderFolderContext();
}

function renderLibrary() {
  const folder=selectedFolder(); const count=state.library.length; const target=folder?.paper_target||100;
  $('#library-count').textContent=count;
  $('#metric-folder-papers').textContent=count;
  $('#metric-folder-target').textContent=`target ${target}`;
  $('#paper-progress-label').textContent=`${count} / ${target} papers`;
  $('#paper-progress-bar').style.width=Math.min(100,(count/Math.max(1,target))*100)+'%';
  const box=$('#paper-list');
  if(!count){box.className='paper-table empty';box.textContent='No papers in this folder.';return;}
  box.className='paper-table';
  box.innerHTML=state.library.map(p=>{const url=safeUrl(p.pdf_url||p.source_url);return `<div class="paper-row"><div><strong>${esc(p.title)}</strong><div class="paper-meta">${esc([p.publication_date?.slice?.(0,4),p.journal,p.doi].filter(Boolean).join(' · '))}</div><div class="paper-meta">${esc(prettyName(p.review_depth))} · ${esc(prettyName(p.access_status))}</div></div><div class="paper-actions">${url?`<a class="secondary linklike" target="_blank" rel="noopener" href="${esc(url)}">Open</a>`:''}<button class="ghost delete-paper" data-item="${esc(p.item_id)}">Remove</button></div></div>`}).join('');
  $$('.delete-paper').forEach(b=>b.onclick=()=>removePaper(b.dataset.item));
}

async function removePaper(itemId){if(!confirm('Remove this paper from the selected folder?'))return;try{await api('/api/library?item_id='+encodeURIComponent(itemId),{method:'DELETE'});toast('Paper removed from folder');await loadLibrary();}catch(e){toast('Remove failed: '+e.message,true)}}

async function uploadPapers() {
  const folder=selectedFolder(); const files=[...$('#paper-files').files];
  if(!folder||!files.length)return;
  const button=$('#upload-papers');button.disabled=true;button.textContent='Uploading…';
  try{
    for(const file of files){
      if(file.type!=='application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) throw new Error(`${file.name} is not a PDF`);
      if(file.size>100*1024*1024) throw new Error(`${file.name} exceeds 100 MB`);
      const safe=file.name.replace(/[^a-zA-Z0-9._-]+/g,'_');
      const storagePath=`${state.authUser.id}/${folder.folder_id}/${crypto.randomUUID()}-${safe}`;
      const encoded=storagePath.split('/').map(encodeURIComponent).join('/');
      const upload=await fetch(`${state.config.url.replace(/\/$/,'')}/storage/v1/object/scibrain-papers/${encoded}`,{method:'POST',headers:{apikey:state.config.publishable_key,Authorization:`Bearer ${accessToken()}`,'Content-Type':'application/pdf','x-upsert':'false'},body:file});
      if(!upload.ok){const err=await upload.text();throw new Error(`Storage upload failed for ${file.name}: ${err}`)}
      await api('/api/library',{method:'POST',body:JSON.stringify({folder_id:folder.folder_id,title:file.name.replace(/\.pdf$/i,''),source_type:'upload',access_status:'uploaded',manual_lookup_required:false,storage_path:storagePath,original_filename:file.name,mime_type:'application/pdf',file_size_bytes:file.size})});
      toast(`Uploaded ${file.name}`);
    }
    $('#paper-files').value=''; await loadLibrary();
  }catch(e){toast(e.message,true);log('Upload error',e.message)}finally{button.textContent='Upload selected PDFs';button.disabled=!selectedFolder()||!$('#paper-files').files.length}
}

async function validateProject(){let payload;try{payload=JSON.parse($('#project-json').value)}catch(e){return showValidation(false,[{msg:'Invalid JSON: '+e.message}])}try{const r=await api('/api/validate_project',{method:'POST',body:JSON.stringify(payload)});showValidation(r.valid,r.gate?[{msg:`Definition gate score: ${(r.gate.score*100).toFixed(0)}%`}]:[]);log('Project validation',r)}catch(e){showValidation(false,[{msg:e.message}]);log('Project validation error',e.message)}}
function showValidation(ok,items=[]){const box=$('#validation-status');box.className='status-box '+(ok?'ok':'bad');box.textContent=ok?'Definition is structurally valid':'Definition requires correction';$('#validation-details').innerHTML=items.map(i=>`<div class="validation-item">${esc(i.msg||JSON.stringify(i))}</div>`).join('')}

async function createProject(){const folder=selectedFolder();if(!folder){toast('Select a research folder first',true);return}let project;try{project=JSON.parse($('#project-json').value)}catch{toast('Invalid project JSON',true);return}try{const r=await api('/api/projects',{method:'POST',body:JSON.stringify({project,folder_id:folder.folder_id,paper_ids:state.library.map(p=>p.canonical_id).filter(Boolean)})});toast('Project created in selected folder');localStorage.setItem('scibrain_session',r.session_id);$('#session-input').value=r.session_id;setView('session');await loadSession(r.session_id);log('Project created',r)}catch(e){toast('Create project failed: '+e.message,true);log('Create project error',e.message)}}

async function loadSession(id){if(!id)return;const r=await api('/api/session?session_id='+encodeURIComponent(id));state.session=r.state;state.artifacts=r.artifacts||[];localStorage.setItem('scibrain_session',id);$('#session-input').value=id;if(state.session.folder_id && state.folders.some(f=>f.folder_id===state.session.folder_id) && state.selectedFolderId!==state.session.folder_id){state.selectedFolderId=state.session.folder_id;localStorage.setItem('scibrain_selected_folder',state.selectedFolderId);await loadLibrary()}renderSession();toast('Session loaded');return r}

function renderSession(){const s=state.session;const has=!!s;$('#enqueue-reviews').disabled=!has;$('#stage-badge').textContent=has?prettyName(s.protocol_stage):'No active session';if(!s){$('#session-id-label').textContent='No session loaded';return}$('#session-id-label').textContent=s.session_id;$('#session-summary').className='';$('#session-summary').innerHTML=`<div class="chips"><span class="chip">Project: ${esc(s.project_id||'—')}</span><span class="chip">Folder: ${esc(selectedFolder()?.name||s.folder_id||'—')}</span><span class="chip">Protocol: ${esc(prettyName(s.protocol_stage))}</span><span class="chip">State: ${esc(prettyName(s.stage))}</span><span class="chip">Candidates: ${(s.candidate_paper_ids||[]).length}</span><span class="chip">Selected: ${(s.selected_paper_ids||[]).length}</span></div><p class="muted">${esc(s.question)}</p>${s.blocked_stage?`<div class="status-box bad">Blocked at ${esc(prettyName(s.blocked_stage))}. Inspect gates and rerun the responsible agent/artifact.</div>`:''}`;$('#validate-stage').disabled=false;$('#add-artifact').disabled=false;renderStageAgents();renderArtifacts()}

function renderStageAgents(){const box=$('#stage-agents');if(!state.session||!state.manifest){box.className='agent-list empty';box.textContent='No active stage.';return}const stage=state.session.protocol_stage;const agents=state.manifest.agents.filter(a=>a.stage===stage);if(!agents.length){box.className='agent-list empty';box.textContent=stage==='execution'?'Execution stage expects external data/run artifacts rather than an AI agent.':'No agents defined for this stage.';return}box.className='agent-list';box.innerHTML=agents.map(a=>{const accepted=a.outputs.every(o=>{const candidates=state.artifacts.filter(x=>x.artifact_type===o);const last=candidates.sort((x,y)=>(y.revision||0)-(x.revision||0))[0];return last&&last.accepted});return `<div class="agent-row"><div><strong>${esc(prettyName(a.id))}</strong><span>${esc(a.purpose)}</span></div><div><span class="agent-state">${accepted?'accepted':'pending'}</span><button class="${accepted?'ghost':'secondary'} run-agent" data-role="${esc(a.id)}">${accepted?'Rerun':'Run'}</button></div></div>`}).join('');$$('.run-agent').forEach(b=>b.onclick=()=>runAgent(b.dataset.role,b))}

async function runAgent(role,button){if(!state.session)return;button.disabled=true;button.textContent='Running…';try{const r=await api('/api/run_agent',{method:'POST',body:JSON.stringify({session_id:state.session.session_id,role_id:role})});log(`Agent ${role}`,r);toast(`${prettyName(role)} completed`);await loadSession(state.session.session_id)}catch(e){toast(`${prettyName(role)} failed: ${e.message}`,true);log(`Agent ${role} error`,e.message)}finally{button.disabled=false}}
async function validateStage(){if(!state.session)return;const b=$('#validate-stage');b.disabled=true;b.textContent='Validating…';try{const r=await api('/api/validate_stage',{method:'POST',body:JSON.stringify({session_id:state.session.session_id})});log('Stage validation',r);toast(r.decision.passed?`Stage passed → ${r.next_stage||'complete'}`:'Stage blocked — inspect gates',!r.decision.passed);await loadSession(state.session.session_id)}catch(e){toast('Stage validation failed: '+e.message,true);log('Stage validation error',e.message)}finally{b.disabled=false;b.textContent='Validate stage'}}
async function addArtifact(){if(!state.session)return;const type=$('#artifact-type').value.trim();if(!type){toast('Artifact type is required',true);return}let payload;try{payload=JSON.parse($('#artifact-payload').value)}catch{toast('Artifact payload is invalid JSON',true);return}try{const r=await api('/api/artifact',{method:'POST',body:JSON.stringify({session_id:state.session.session_id,artifact_type:type,payload})});log('External artifact',r);toast('Artifact added');await loadSession(state.session.session_id)}catch(e){toast('Artifact failed: '+e.message,true)}}
function renderArtifacts(){const box=$('#artifact-list');$('#artifact-count').textContent=state.artifacts.length;const sorted=[...state.artifacts].sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)));if(!sorted.length){box.className='artifact-list empty';box.textContent='No artifacts loaded.';return}box.className='artifact-list';box.innerHTML=sorted.map(a=>`<div class="artifact"><strong>${esc(prettyName(a.artifact_type))} · r${a.revision}</strong><small>${esc(prettyName(a.producer_agent))} · ${esc(prettyName(a.stage))} · ${a.accepted?'accepted':'unaccepted'}</small></div>`).join('')}

async function researchSearch(){const folder=selectedFolder();if(!folder)return;const query=$('#research-query').value.trim();if(!query){toast('Enter a scientific search query',true);return}const b=$('#research-search');b.disabled=true;b.textContent='Searching…';try{const r=await api('/api/research_search',{method:'POST',body:JSON.stringify({folder_id:folder.folder_id,project_id:state.session?.project_id||null,query,from_year:Number($('#research-year').value||1900),max_results:Number($('#research-max').value||40),include_web:true,resolve_open_access:true})});state.researchResults=r.results||[];$('#research-source-summary').textContent=`${state.researchResults.length} results · sources: ${(r.sources||[]).join(', ')||'none'}${r.general_web_enabled?' · general web enabled':' · web API optional'}`;renderResearchResults();log('Research Agent search',{query:r.query,sources:r.sources,errors:r.errors,count:state.researchResults.length})}catch(e){toast('Research search failed: '+e.message,true);log('Research search error',e.message)}finally{b.disabled=false;b.textContent='Search information'}}

function renderResearchResults(){const box=$('#research-results');if(!state.researchResults.length){box.className='result-list empty';box.textContent='No results.';return}box.className='result-list';box.innerHTML=state.researchResults.map((r,i)=>{const url=safeUrl(r.pdf_url||r.url);const access=r.pdf_url?'Open full text':r.manual_lookup_required?'Manual retrieval':'Source';return `<div class="result-card"><h3>${esc(r.title)}</h3><div class="source-line"><span>${esc(prettyName(r.source))}</span><span>${esc(r.publication_date||'')}</span>${r.doi?`<span>DOI ${esc(r.doi)}</span>`:''}<span class="${r.pdf_url?'access-open':'access-manual'}">${esc(access)}</span></div>${r.abstract?`<p>${esc(r.abstract.replace(/<[^>]+>/g,' '))}</p>`:''}${r.manual_lookup_message?`<div class="manual-note">${esc(r.manual_lookup_message)}</div>`:''}<div class="row" style="margin-top:9px">${url?`<a class="secondary linklike" target="_blank" rel="noopener" href="${esc(url)}">${r.pdf_url?'Open PDF':'Open source'}</a>`:''}<button class="primary add-result" data-index="${i}">Add to folder</button></div></div>`}).join('');$$('.add-result').forEach(b=>b.onclick=()=>addResearchResult(Number(b.dataset.index),b))}

async function addResearchResult(index,button){const folder=selectedFolder(),r=state.researchResults[index];if(!folder||!r)return;button.disabled=true;try{await api('/api/library',{method:'POST',body:JSON.stringify({folder_id:folder.folder_id,canonical_id:r.canonical_id,title:r.title,authors:r.authors||[],publication_date:r.publication_date||null,journal:r.journal||null,doi:r.doi||null,arxiv_id:r.arxiv_id||null,source_type:r.source||'web',source_url:r.url||null,pdf_url:r.pdf_url||null,access_status:r.access_status||'metadata_only',manual_lookup_required:!!r.manual_lookup_required,abstract:r.abstract||'',cited_by_count:r.cited_by_count||0})});button.textContent='Added';toast('Source added to selected folder');await loadLibrary()}catch(e){toast('Could not add source: '+e.message,true);button.disabled=false}}

async function enqueueReviews(){if(!state.session)return;const paperIds=state.library.map(p=>p.canonical_id).filter(Boolean);try{const job=await api('/api/jobs',{method:'POST',body:JSON.stringify({session_id:state.session.session_id,job_type:'enqueue_selected_reviews',payload:{limit:100,paper_ids:paperIds}})});toast('Deep-review jobs queued');log('Review enqueue job',job);await refreshJobs()}catch(e){toast('Queue reviews failed: '+e.message,true)}}
async function refreshJobs(){const box=$('#jobs-list');if(!state.session){box.className='jobs-list empty';box.textContent='Load a research session first.';return}try{const r=await api('/api/jobs?session_id='+encodeURIComponent(state.session.session_id));state.jobs=r.jobs||[];renderJobs()}catch(e){box.className='jobs-list empty';box.textContent='Jobs unavailable: '+e.message}}
function renderJobs(){const box=$('#jobs-list');if(!state.jobs.length){box.className='jobs-list empty';box.textContent='No jobs queued.';return}box.className='artifact-list';box.innerHTML=state.jobs.map(j=>`<div class="agent-row"><div><strong>${esc(prettyName(j.job_type))}</strong><span>${esc(j.job_id)}<br>${esc(j.last_error||JSON.stringify(j.progress||{}))}</span></div><div><span class="agent-state">${esc(j.status)}</span>${j.status!=='completed'?`<button class="secondary run-job" data-job="${esc(j.job_id)}">Run step</button>`:''}</div></div>`).join('');$$('.run-job').forEach(b=>b.onclick=()=>runJob(b.dataset.job,b))}
async function runJob(jobId,button){button.disabled=true;button.textContent='Running…';try{const r=await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:jobId})});log(`Job ${jobId}`,r);toast(`Job ${r.status||'completed'}`,r.status==='failed');if(state.session)await loadSession(state.session.session_id);await loadLibrary();await refreshJobs()}catch(e){toast('Job failed: '+e.message,true);log(`Job ${jobId} error`,e.message);await refreshJobs()}finally{button.disabled=false}}

async function loadProjects(){const box=$('#projects-list');try{const folder=selectedFolder();const url='/api/projects'+(folder?'?folder_id='+encodeURIComponent(folder.folder_id):'');const r=await api(url);const rows=r.projects||[];if(!rows.length){box.className='projects-table empty';box.textContent='No projects in the selected folder.';return}box.className='projects-table';box.innerHTML=rows.map(p=>`<div class="project-row"><strong>${esc(p.title)}</strong><span>${esc(p.project_id)}</span><span>${esc(p.status)}</span><span>${new Date(p.updated_at).toLocaleString()}</span></div>`).join('')}catch(e){box.className='projects-table empty';box.textContent='Projects unavailable: '+e.message;toast('Project list failed: '+e.message,true)}}

function renderAll(){renderHealth();renderManifest();renderFolders();renderLibrary();renderSession();}
window.addEventListener('DOMContentLoaded',init);
