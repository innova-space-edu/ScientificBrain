(() => {
  const q=s=>document.querySelector(s), es=()=>window.SBI18N?.language?.()!=='en', tr=(a,b)=>es()?a:b;
  let automatic=false;
  async function runAgent(role,button=null){
    if(!state.session)throw new Error(tr('Carga una sesión primero.','Load a session first.'));
    if(button){button.disabled=true;button.dataset.sbText||=button.textContent;button.textContent=tr('Ejecutando…','Running…');}
    try{const r=await api('/api/orchestrate?op=run_agent',{method:'POST',body:JSON.stringify({session_id:state.session.session_id,role_id:role})});await loadSession(state.session.session_id);return r;}
    finally{if(button){button.disabled=false;button.textContent=button.dataset.sbText;}}
  }
  async function validate(button=null){
    if(!state.session)throw new Error(tr('Carga una sesión primero.','Load a session first.'));
    if(button){button.disabled=true;button.dataset.sbText||=button.textContent;button.textContent=tr('Validando…','Validating…');}
    try{const r=await api('/api/orchestrate?op=validate_stage',{method:'POST',body:JSON.stringify({session_id:state.session.session_id})});await loadSession(state.session.session_id);return r;}
    finally{if(button){button.disabled=false;button.textContent=button.dataset.sbText;}}
  }
  function accepted(agent){return (agent.outputs||[]).every(o=>{const rows=(state.artifacts||[]).filter(x=>x.artifact_type===o).sort((a,b)=>(b.revision||0)-(a.revision||0));return rows[0]?.accepted;});}
  async function auto(button){
    if(automatic){automatic=false;button.textContent=tr('Ejecutar etapa automáticamente','Run stage automatically');return;}
    if(!state.session||!state.manifest)throw new Error(tr('Carga una sesión y manifiesto primero.','Load a session and manifest first.'));
    automatic=true;button.textContent=tr('Detener automatización','Stop automation');
    try{
      for(let n=0;n<16&&automatic;n++){
        const stage=state.session.protocol_stage, agents=(state.manifest.agents||[]).filter(a=>a.stage===stage);
        if(!agents.length){toast?.(tr(`La etapa ${stage} requiere datos o artefactos externos.`,`Stage ${stage} requires external data or artifacts.`));break;}
        for(const a of agents){if(!automatic)break;if(!accepted(a)){toast?.(`${tr('Ejecutando agente','Running agent')} ${a.id}…`);await runAgent(a.id);}}
        if(!automatic)break;
        const v=await validate();
        if(!v.decision?.passed){toast?.(tr('Etapa bloqueada por gates científicos.','Stage blocked by scientific gates.'),true);break;}
        if(!v.next_stage){toast?.(tr('Protocolo científico completado.','Scientific protocol completed.'));break;}
      }
    } finally {automatic=false;button.textContent=tr('Ejecutar etapa automáticamente','Run stage automatically');}
  }
  function inject(){const v=q('#validate-stage');if(!v||q('#auto-stage'))return;const b=document.createElement('button');b.id='auto-stage';b.className='secondary';b.textContent=tr('Ejecutar etapa automáticamente','Run stage automatically');v.before(b);}
  document.addEventListener('click',async e=>{
    const b=e.target.closest('button');if(!b)return;
    try{
      if(b.matches('.run-agent')){e.preventDefault();e.stopImmediatePropagation();await runAgent(b.dataset.role,b);toast?.(tr('Agente completado.','Agent completed.'));}
      else if(b.id==='validate-stage'){e.preventDefault();e.stopImmediatePropagation();const r=await validate(b);toast?.(r.decision?.passed?tr('Etapa aprobada.','Stage passed.'):tr('Etapa bloqueada por gates.','Stage blocked by gates.'),!r.decision?.passed);}
      else if(b.id==='auto-stage'){e.preventDefault();e.stopImmediatePropagation();await auto(b);}
    }catch(err){toast?.(err.message||String(err),true);}
  },true);
  window.addEventListener('DOMContentLoaded',()=>{inject();const box=q('#stage-agents');if(box)new MutationObserver(inject).observe(box,{childList:true,subtree:true});});
})();
