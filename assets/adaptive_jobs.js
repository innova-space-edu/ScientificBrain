(() => {
  const q=s=>document.querySelector(s), sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const es=()=>window.SBI18N?.language?.()!=='en';
  const tr=(a,b)=>es()?a:b;
  const folder=()=>typeof selectedFolder==='function'?selectedFolder():null;
  let queueRunning=false;

  async function fetchJobs(){
    const f=folder(); if(!f) return [];
    const p=new URLSearchParams({folder_id:f.folder_id,limit:'500'});
    if(state.session?.folder_id===f.folder_id)p.set('session_id',state.session.session_id);
    const r=await api('/api/jobs?'+p); state.jobs=r.jobs||[]; return state.jobs;
  }
  function phase(j){
    const p=j.progress||{}, x=p.phase||j.status;
    if(x==='extract')return `${tr('Extracción','Extraction')} ${p.chunk_index||0}/${(p.chunk_ranges||[]).length}${p.current_pages?` · p. ${p.current_pages[0]}–${p.current_pages[1]}`:''}`;
    const names={prepare:['Preparando PDF','Preparing PDF'],consolidate:['Consolidando evidencia','Consolidating evidence'],critique:['Crítica independiente','Independent critique'],specialists:['Revisores especializados','Specialist reviewers'],finalize:['Validando gates','Validating gates'],completed:['✓ Completado','✓ Completed']};
    if(x==='specialists')return `${tr(...names.specialists)} ${p.specialist_index||0}/${(p.specialist_roles||[]).length}`;
    return names[x]?tr(...names[x]):x;
  }
  function compact(){
    const jobs=(state.jobs||[]).filter(j=>j.job_type==='review_paper');
    [...document.querySelectorAll('#jobs-list .agent-row')].forEach((row,i)=>{
      const j=jobs[i]; if(!j)return;
      const d=row.querySelector('div:first-child span'), text=`${j.payload?.paper_id||''}\n${phase(j)}`;
      if(d&&d.textContent!==text)d.textContent=text;
    });
    const s=q('#review-progress-summary'), n=(state.library||[]).length;
    if(s){
      const mode=n<=5?tr('profundización por paper','deep per-paper'):n<=25?tr('corpus balanceado','balanced corpus'):n<=100?tr('por lotes','batched'):tr('síntesis jerárquica','hierarchical');
      const base=s.textContent.split(' · modo ')[0].split(' · mode ')[0], text=`${base} · ${tr('modo','mode')} ${mode}`;
      if(s.textContent!==text)s.textContent=text;
    }
  }
  async function runJob(jobId,button=null,max=500){
    if(button){button.disabled=true;button.dataset.sbText||=button.textContent;}
    try{
      for(let i=0;i<max;i++){
        if(button)button.textContent=`${tr('Procesando','Processing')}… ${i+1}`;
        const j=await api('/api/run_job',{method:'POST',body:JSON.stringify({job_id:jobId})});
        const k=(state.jobs||[]).findIndex(x=>x.job_id===jobId); if(k>=0)state.jobs[k]=j; else state.jobs.unshift(j);
        compact();
        if(j.status==='completed')return j;
        if(j.status==='failed')throw new Error(j.last_error||tr('El trabajo falló','Job failed'));
        if(j.status==='pending'&&j.progress?.reason==='soft_timeout'){
          throw new Error(tr('El análisis alcanzó el límite seguro de esta ejecución. El progreso quedó guardado; vuelve a ejecutarlo para continuar.','The analysis reached this run’s safe deadline. Progress was saved; run it again to continue.'));
        }
        await sleep(120);
      }
      throw new Error(tr('Límite de pasos alcanzado; el progreso quedó guardado.','Step limit reached; progress was saved.'));
    } finally {if(button){button.disabled=false;button.textContent=button.dataset.sbText||tr('Ejecutar','Run');}}
  }
  async function refresh(){if(typeof loadLibrary==='function')await loadLibrary().catch(()=>{});await fetchJobs().catch(()=>[]);compact();}
  async function ensurePaperJob(button){
    const row=button.closest('.paper-row'), item=row?.querySelector('.delete-paper')?.dataset.item, p=(state.library||[]).find(x=>x.item_id===item), f=folder();
    if(!p||!f)return null; await fetchJobs();
    let j=(state.jobs||[]).find(x=>x.job_type==='review_paper'&&x.payload?.paper_id===p.canonical_id&&x.status!=='completed');
    if(!j)j=await api('/api/jobs',{method:'POST',body:JSON.stringify({folder_id:f.folder_id,session_id:state.session?.folder_id===f.folder_id?state.session.session_id:null,job_type:'review_paper',payload:{paper_id:p.canonical_id,pdf_url:p.pdf_url||null}})});
    return j;
  }
  async function next(button){await fetchJobs();const j=(state.jobs||[]).find(x=>x.job_type==='review_paper'&&['pending','running','failed'].includes(x.status));if(!j){toast?.(tr('No quedan análisis pendientes.','No pending analyses.'));return;}try{await runJob(j.job_id,button);await refresh();toast?.(tr('Paper analizado completamente.','Paper fully reviewed.'));}catch(e){await refresh();toast?.(e.message,true);}}
  async function queue(button){
    if(queueRunning){queueRunning=false;button.textContent=tr('Procesar cola','Process queue');return;}
    queueRunning=true;button.textContent=tr('Detener cola','Stop queue');let done=0;
    try{while(queueRunning){await fetchJobs();const j=(state.jobs||[]).find(x=>x.job_type==='review_paper'&&['pending','running','failed'].includes(x.status));if(!j)break;await runJob(j.job_id);done++;await refresh();}}
    catch(e){toast?.(`${tr('Cola detenida','Queue stopped')}: ${e.message}`,true);}
    finally{queueRunning=false;button.textContent=tr('Procesar cola','Process queue');await refresh();if(done)toast?.(`${done} ${tr('papers completados','papers completed')}`);}
  }
  document.addEventListener('click',async e=>{
    const b=e.target.closest('button');if(!b)return;
    try{
      if(b.matches('.run-v09')){e.preventDefault();e.stopImmediatePropagation();await runJob(b.dataset.job,b);await refresh();}
      else if(b.id==='process-next-review'){e.preventDefault();e.stopImmediatePropagation();await next(b);}
      else if(b.id==='process-review-queue'){e.preventDefault();e.stopImmediatePropagation();await queue(b);}
      else if(b.matches('.analyze-v09')){e.preventDefault();e.stopImmediatePropagation();const j=await ensurePaperJob(b);if(j){await runJob(j.job_id,b);await refresh();}}
    }catch(err){toast?.(err.message||String(err),true);}
  },true);
  window.SBAdaptive={...(window.SBAdaptive||{}),runJob,fetchJobs,refresh};
  window.addEventListener('DOMContentLoaded',()=>setTimeout(async()=>{await fetchJobs().catch(()=>[]);compact();},250));
})();
