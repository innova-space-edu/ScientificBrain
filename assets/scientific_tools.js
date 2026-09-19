(() => {
  const $ = s => document.querySelector(s);
  const state = {config:null,status:null,toolkit:null};

  function authSession(){try{return JSON.parse(localStorage.getItem('scibrain_supabase_session')||'null')}catch{return null}}
  function saveSession(v){if(v)localStorage.setItem('scibrain_supabase_session',JSON.stringify(v));else localStorage.removeItem('scibrain_supabase_session')}
  function token(){return authSession()?.access_token||''}

  async function loadConfig(){
    const r=await fetch('/api/client_config',{cache:'no-store'});
    if(!r.ok)throw new Error('No se pudo cargar la configuración de ScientificBrain');
    state.config=await r.json();
  }
  async function refresh(){
    const s=authSession(); if(!s?.refresh_token||!state.config?.url)return false;
    const r=await fetch(state.config.url.replace(/\/$/,'')+'/auth/v1/token?grant_type=refresh_token',{
      method:'POST',headers:{apikey:state.config.publishable_key,'Content-Type':'application/json'},
      body:JSON.stringify({refresh_token:s.refresh_token})
    });
    if(!r.ok){saveSession(null);return false}
    saveSession(await r.json()); return true;
  }
  async function api(url,options={},retry=true){
    const headers={'Content-Type':'application/json',...(options.headers||{})};
    if(token())headers.Authorization='Bearer '+token();
    let r=await fetch(url,{...options,headers});
    if(r.status===401&&retry&&await refresh()){headers.Authorization='Bearer '+token();r=await fetch(url,{...options,headers})}
    let payload;try{payload=await r.json()}catch{payload={error:'HTTP '+r.status}}
    if(!r.ok)throw new Error(payload.detail||payload.error||payload.message||('HTTP '+r.status));
    return payload;
  }
  function out(label,data){
    const el=$('#tools-output'); const ts=new Date().toLocaleTimeString();
    el.textContent+='\n\n['+ts+'] '+label+'\n'+(typeof data==='string'?data:JSON.stringify(data,null,2));
    el.scrollTop=el.scrollHeight;
  }
  function boolRow(label,value){
    return '<div class="status-row"><span>'+label+'</span><strong class="'+(value?'status-good':'status-warn')+'">'+(value?'Configurado':'No configurado')+'</strong></div>';
  }
  function render(){
    const s=state.status||{};
    $('#nvidia-status').innerHTML=
      boolRow('API alojada',s.hosted_api_configured)+
      boolRow('Clave NGC',s.ngc_key_configured)+
      boolRow('NIM local/remoto',s.local_nim_configured)+
      '<div class="status-row"><span>Capacidades</span><strong>'+(s.capabilities||[]).length+'</strong></div>';
    $('#api-state').textContent=s.hosted_api_configured?'API NVIDIA configurada':'NVIDIA_API_KEY pendiente';
    $('#api-state').className=s.hosted_api_configured?'status-good':'status-warn';

    const caps=s.capabilities||[];
    const physics=caps.some(x=>String(x.domain).toLowerCase().includes('physics'));
    const bio=caps.some(x=>String(x.domain).toLowerCase().includes('bio'));
    $('#physicsnemo-state').textContent=physics?'PhysicsNeMo endpoint configurado':'Endpoint PhysicsNeMo por configurar';
    $('#physicsnemo-state').className=physics?'status-good':'status-warn';
    $('#bionemo-state').textContent=bio?'BioNeMo endpoint configurado':'Endpoint BioNeMo por configurar';
    $('#bionemo-state').className=bio?'status-good':'status-warn';

    const select=$('#capability-select');
    select.innerHTML=caps.filter(x=>x.name!=='nvidia-chat').map(x=>'<option value="'+x.name+'">'+x.name+' · '+x.domain+'</option>').join('')||'<option value="">Sin capacidades científicas configuradas</option>';
    const planned=state.toolkit?.planned_extensions||s.physics_toolkit?.planned_extensions||[];
    $('#future-extensions').innerHTML=planned.map(x=>'<span>'+x+'</span>').join('');
  }
  async function load(){
    await loadConfig();
    if(!token()){
      $('#nvidia-status').innerHTML='<div class="status-warn">Inicia sesión en ScientificBrain para usar las herramientas.</div>';
      $('#run-nvidia-chat').disabled=true; $('#run-capability').disabled=true; return;
    }
    const health=await api('/api/health'); $('#tools-version').textContent='v'+health.version;
    const [status,toolkit]=await Promise.all([
      api('/api/science?op=nvidia_status'),
      api('/api/science?op=physics_toolkit')
    ]);
    state.status=status; state.toolkit=toolkit; render();
  }
  async function runChat(){
    try{
      const prompt=$('#nvidia-prompt').value.trim(); if(!prompt)throw new Error('Escribe una consulta');
      out('NVIDIA API','Ejecutando…');
      const r=await api('/api/science?op=nvidia_invoke',{method:'POST',body:JSON.stringify({capability:'nvidia-chat',input:{prompt}})});
      out('NVIDIA API resultado',r);
    }catch(e){out('Error',e.message)}
  }
  async function runCapability(){
    try{
      const capability=$('#capability-select').value;if(!capability)throw new Error('No hay una capacidad seleccionada');
      let input={}; try{input=JSON.parse($('#capability-input').value||'{}')}catch{throw new Error('Entrada JSON inválida')}
      out(capability,'Ejecutando…');
      const r=await api('/api/science?op=nvidia_invoke',{method:'POST',body:JSON.stringify({capability,input})});
      out(capability+' resultado',r);
    }catch(e){out('Error',e.message)}
  }
  window.addEventListener('DOMContentLoaded',()=>{
    $('#run-nvidia-chat').addEventListener('click',runChat);
    $('#run-capability').addEventListener('click',runCapability);
    $('#clear-tools-output').addEventListener('click',()=>$('#tools-output').textContent='ScientificBrain Tools listo.');
    load().catch(e=>out('Inicialización',e.message));
  });
})();