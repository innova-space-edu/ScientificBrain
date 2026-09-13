(() => {
  const q=s=>document.querySelector(s), es=()=>window.SBI18N?.language?.()!=='en', tr=(a,b)=>es()?a:b;
  const folder=()=>typeof selectedFolder==='function'?selectedFolder():null;
  async function scienceJob(type,payload={},button=null){
    const f=folder();if(!f)throw new Error(tr('Selecciona una carpeta.','Select a folder.'));
    const j=await api('/api/jobs',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,session_id:state.session?.folder_id===f.folder_id?state.session.session_id:null,job_type:type,payload})});
    return window.SBAdaptive.runJob(j.job_id,button,800);
  }
  async function build(button){await scienceJob('build_scientific_graph',{full_text_only:true},button);q('#map-refresh')?.click();toast?.(tr('Mapa científico actualizado.','Scientific map updated.'));}
  async function contradictions(button){
    const f=folder();if(!f)return;const s=await api('/api/science?op=graph_summary&folder_id='+encodeURIComponent(f.folder_id)).catch(()=>({nodes:0}));
    if(!s.nodes)await scienceJob('build_scientific_graph',{full_text_only:true});
    await scienceJob('detect_contradictions',{},button);q('#map-refresh')?.click();toast?.(tr('Contradicciones analizadas.','Contradictions analyzed.'));
  }
  async function hypotheses(button){
    const f=folder(),question=q('#collab-topic')?.value?.trim()||state.session?.question||'';if(!f||!question)throw new Error(tr('Define una pregunta primero.','Define a question first.'));
    let c=await api('/api/science?op=contradictions&folder_id='+encodeURIComponent(f.folder_id)+'&limit=1').catch(()=>({contradictions:[]}));
    if(!(c.contradictions||[]).length)await contradictions(null);
    await scienceJob('generate_competing_hypotheses',{question},button);q('#map-refresh')?.click();toast?.(tr('Hipótesis competidoras generadas.','Competing hypotheses generated.'));
  }
  async function collab(op,payload,button){
    if(button){button.disabled=true;button.dataset.sbText||=button.textContent;}
    try{return await api('/api/collaboration?op='+op,{method:'POST',body:JSON.stringify(payload)});}
    finally{if(button){button.disabled=false;button.textContent=button.dataset.sbText;}}
  }
  document.addEventListener('click',async e=>{
    const b=e.target.closest('button');if(!b)return;
    try{
      if(b.id==='map-build'){e.preventDefault();e.stopImmediatePropagation();await build(b);}
      else if(b.id==='map-contr'){e.preventDefault();e.stopImmediatePropagation();await contradictions(b);}
      else if(b.id==='map-hyp'){e.preventDefault();e.stopImmediatePropagation();await hypotheses(b);}
      else if(b.id==='collab-generate'){
        e.preventDefault();e.stopImmediatePropagation();const f=folder(),topic=q('#collab-topic')?.value?.trim();if(!f||!topic)throw new Error(tr('Selecciona carpeta e indica un tema.','Select a folder and enter a topic.'));
        await collab('generate_draft',{folder_id:f.folder_id,topic,language:window.SBI18N?.language?.()||'es'},b);q('#collab-refresh')?.click();toast?.(tr('Borrador generado con cobertura adaptativa del corpus.','Draft generated with adaptive corpus coverage.'));
      } else if(b.id==='collab-send'){
        e.preventDefault();e.stopImmediatePropagation();const f=folder(),message=q('#collab-message')?.value?.trim();if(!f||!message)return;
        await collab('discuss',{folder_id:f.folder_id,message,agent_id:q('#collab-agent')?.value||'critical_reviewer',section_key:q('#collab-section')?.value||null,language:window.SBI18N?.language?.()||'es'},b);if(q('#collab-message'))q('#collab-message').value='';q('#collab-refresh')?.click();
      } else if(b.matches('.review-section')){
        e.preventDefault();e.stopImmediatePropagation();const f=folder();if(!f)return;await collab('review_section',{folder_id:f.folder_id,section_key:b.dataset.k,agent_id:q('#collab-agent')?.value||'critical_reviewer',language:window.SBI18N?.language?.()||'es'},b);q('#collab-refresh')?.click();
      }
    }catch(err){toast?.(err.message||String(err),true);}
  },true);
})();
