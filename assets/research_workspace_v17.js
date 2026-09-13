(() => {
  const q=s=>document.querySelector(s), qa=s=>[...document.querySelectorAll(s)];
  const lang=()=>window.SBI18N?.language?.()||'es';
  const tr=(es,en)=>lang()==='en'?en:es;
  const folder=()=>typeof selectedFolder==='function'?selectedFolder():null;
  const notify=(t,b=false)=>typeof toast==='function'?toast(t,b):console[b?'error':'log'](t);
  function bytesFromBase64(value){const raw=atob(value||'');const out=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)out[i]=raw.charCodeAt(i);return out;}
  async function exportFile(format){
    const f=folder(); if(!f?.folder_id)return;
    try{
      const r=await api(`/api/collaboration?op=export&folder_id=${encodeURIComponent(f.folder_id)}&format=${encodeURIComponent(format)}`);
      const data=r.encoding==='base64'?bytesFromBase64(r.content_base64):r.content||'';
      const blob=new Blob([data],{type:r.mime||'application/octet-stream'}),url=URL.createObjectURL(blob),a=document.createElement('a');
      a.href=url;a.download=r.filename||`scientificbrain.${format}`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);
      notify(tr('Exportación científica preparada.','Scientific export prepared.'));
    }catch(e){notify(e.message,true)}
  }
  function install(){
    const actions=q('#v12-research-tools .v12-panel-actions'); if(!actions||q('#v17-pdf'))return;
    const defs=[['pdf','PDF'],['docx','Word'],['ris','RIS'],['package',tr('Paquete reproducible','Reproducible package')]];
    defs.forEach(([fmt,label])=>{const b=document.createElement('button');b.className='ghost';b.id=`v17-${fmt}`;b.textContent=label;b.onclick=()=>exportFile(fmt);actions.appendChild(b);});
  }
  const obs=new MutationObserver(install);
  function boot(){install();obs.observe(document.body,{childList:true,subtree:true});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
