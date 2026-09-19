(() => {
  const $=s=>document.querySelector(s);
  const state={config:null,status:null,toolkit:null,workers:null};
  function authSession(){try{return JSON.parse(localStorage.getItem('scibrain_supabase_session')||'null')}catch{return null}}
  function saveSession(v){if(v)localStorage.setItem('scibrain_supabase_session',JSON.stringify(v));else localStorage.removeItem('scibrain_supabase_session')}
  function token(){return authSession()?.access_token||''}
  async function loadConfig(){const r=await fetch('/api/client_config',{cache:'no-store'});if(!r.ok)throw new Error('No se pudo cargar la configuración');state.config=await r.json()}
  async function refresh(){const s=authSession();if(!s?.refresh_token||!state.config?.url)return false;const r=await fetch(state.config.url.replace(/\/$/,'')+'/auth/v1/token?grant_type=refresh_token',{method:'POST',headers:{apikey:state.config.publishable_key,'Content-Type':'application/json'},body:JSON.stringify({refresh_token:s.refresh_token})});if(!r.ok){saveSession(null);return false}saveSession(await r.json());return true}
  async function api(url,options={},retry=true){const headers={'Content-Type':'application/json',...(options.headers||{})};if(token())headers.Authorization='Bearer '+token();let r=await fetch(url,{...options,headers});if(r.status===401&&retry&&await refresh()){headers.Authorization='Bearer '+token();r=await fetch(url,{...options,headers})}let payload;try{payload=await r.json()}catch{payload={error:'HTTP '+r.status}}if(!r.ok)throw new Error(payload.detail||payload.error||payload.message||('HTTP '+r.status));return payload}
  function out(label,data){const el=$('#tools-output'),ts=new Date().toLocaleTimeString();el.textContent+='\n\n['+ts+'] '+label+'\n'+(typeof data==='string'?data:JSON.stringify(data,null,2));el.scrollTop=el.scrollHeight}
  function boolRow(label,value){return '<div class="status-row"><span>'+label+'</span><strong class="'+(value?'status-good':'status-warn')+'">'+(value?'Configurado':'No configurado')+'</strong></div>'}
  function render(){
    const s=state.status||{};
    $('#nvidia-status').innerHTML=boolRow('API NVIDIA',s.hosted_api_configured)+boolRow('Clave NGC',s.ngc_key_configured)+boolRow('NIM local/remoto',s.local_nim_configured)+'<div class="status-row"><span>Capacidades NVIDIA</span><strong>'+(s.capabilities||[]).length+'</strong></div>';
    $('#api-state').textContent=s.hosted_api_configured?'API NVIDIA configurada':'NVIDIA_API_KEY pendiente';$('#api-state').className=s.hosted_api_configured?'status-good':'status-warn';
    const caps=s.capabilities||[], physics=caps.some(x=>String(x.domain).toLowerCase().includes('physics')), bio=caps.some(x=>String(x.domain).toLowerCase().includes('bio'));
    $('#physicsnemo-state').textContent=physics?'PhysicsNeMo endpoint configurado':'Runtime/endpoint PhysicsNeMo por configurar';$('#physicsnemo-state').className=physics?'status-good':'status-warn';
    $('#bionemo-state').textContent=bio?'BioNeMo endpoint configurado':'Endpoint BioNeMo por configurar';$('#bionemo-state').className=bio?'status-good':'status-warn';
    const select=$('#capability-select');select.innerHTML=caps.filter(x=>x.name!=='nvidia-chat').map(x=>'<option value="'+x.name+'">'+x.name+' · '+x.domain+'</option>').join('')||'<option value="">Sin capacidades NVIDIA configuradas</option>';
    const implemented=state.toolkit?.implemented_extensions||[];$('#implemented-extensions').innerHTML=implemented.map(x=>'<span>'+x+'</span>').join('');
    const workers=state.workers?.workers||[];$('#worker-status').innerHTML='<div class="status-row"><span>Workers/HPC</span><strong class="'+(workers.length?'status-good':'status-warn')+'">'+workers.length+'</strong></div>';
    $('#workers-list').innerHTML=workers.length?workers.map(w=>'<div class="capability-item"><strong>'+w.name+'</strong><div class="tools-note">'+(w.description||'Worker científico')+'</div><div>'+((w.solvers||[]).join(' · ')||'sin solver declarado')+'</div></div>').join(''):'<div class="status-warn">Aún no hay workers/HPC configurados.</div>';
  }
  async function load(){
    await loadConfig();
    if(!token()){out('Autenticación','Inicia sesión en ScientificBrain para usar las herramientas.');$('#run-nvidia-chat').disabled=true;$('#run-capability').disabled=true;return}
    const health=await api('/api/health');$('#tools-version').textContent='v'+health.version;
    const [status,toolkit,workers]=await Promise.all([api('/api/science?op=nvidia_status'),api('/api/science?op=physics_toolkit'),api('/api/science?op=physics_workers')]);
    state.status=status;state.toolkit=toolkit;state.workers=workers;render();
  }
  function num(id){const v=$(id).value.trim();return v===''?null:Number(v)}
  async function prepareJob(){
    try{
      let parameters;try{parameters=JSON.parse($('#job-parameters').value||'{}')}catch{throw new Error('Parámetros JSON inválidos')}
      const payload={solver:$('#job-solver').value,action:$('#job-action').value,model:$('#job-model').value.trim(),input_artifact:$('#job-input').value.trim(),parameters,resources:{gpus:Number($('#job-gpus').value||0),cpus:4,nodes:1,memory_gb:8,wall_minutes:60}};
      const r=await api('/api/science?op=physics_prepare_job',{method:'POST',body:JSON.stringify(payload)});out('Job científico preparado',r);
    }catch(e){out('Error job',e.message)}
  }
  async function runRouter(){
    try{
      const payload={ne:num('#r-ne'),B:num('#r-B'),Te_ev:num('#r-Te'),Ti_ev:num('#r-Ti'),L:num('#r-L'),U:num('#r-U'),A:num('#r-A'),Z:num('#r-Z'),mfp:num('#r-mfp'),needs_electron_kinetics:$('#r-electron').checked,low_temperature_2d:$('#r-lowt').checked,particle_through_matter:$('#r-matter').checked};
      const r=await api('/api/science?op=physics_route',{method:'POST',body:JSON.stringify(payload)});out('Router físico',r);
    }catch(e){out('Error router',e.message)}
  }
  async function runMonteCarlo(){
    try{let distributions;try{distributions=JSON.parse($('#mc-spec').value||'{}')}catch{throw new Error('Distribuciones JSON inválidas')}
      const r=await api('/api/science?op=physics_monte_carlo',{method:'POST',body:JSON.stringify({distributions,n:Number($('#mc-n').value),seed:Number($('#mc-seed').value)})});
      const preview={...r,samples:r.samples.slice(0,20),preview_only:r.samples.length>20};out('Monte Carlo',preview);
    }catch(e){out('Error Monte Carlo',e.message)}
  }
  async function runChat(){try{const prompt=$('#nvidia-prompt').value.trim();if(!prompt)throw new Error('Escribe una consulta');const r=await api('/api/science?op=nvidia_invoke',{method:'POST',body:JSON.stringify({capability:'nvidia-chat',input:{prompt}})});out('NVIDIA API',r)}catch(e){out('Error NVIDIA',e.message)}}
  async function runCapability(){try{const capability=$('#capability-select').value;if(!capability)throw new Error('No hay capacidad seleccionada');let input;try{input=JSON.parse($('#capability-input').value||'{}')}catch{throw new Error('Entrada JSON inválida')}const r=await api('/api/science?op=nvidia_invoke',{method:'POST',body:JSON.stringify({capability,input})});out(capability,r)}catch(e){out('Error capacidad',e.message)}}
  window.addEventListener('DOMContentLoaded',()=>{$('#prepare-physics-job').addEventListener('click',prepareJob);$('#run-physics-router').addEventListener('click',runRouter);$('#run-monte-carlo').addEventListener('click',runMonteCarlo);$('#run-nvidia-chat').addEventListener('click',runChat);$('#run-capability').addEventListener('click',runCapability);$('#clear-tools-output').addEventListener('click',()=>$('#tools-output').textContent='ScientificBrain Physics Tools listo.');load().catch(e=>out('Inicialización',e.message))});
})();