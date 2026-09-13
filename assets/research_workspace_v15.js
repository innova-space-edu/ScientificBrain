(() => {
  const q = s => document.querySelector(s);
  const h = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const lang = () => window.SBI18N?.language?.() || 'es';
  const tr = (es, en) => lang() === 'en' ? en : es;
  const currentFolder = () => typeof selectedFolder === 'function' ? selectedFolder() : null;
  const notify = (text, bad=false) => typeof toast === 'function' ? toast(text, bad) : console[bad?'error':'log'](text);
  let busy = false;

  function ensureStyle() {
    if (q('#v15-evidence-style')) return;
    const s = document.createElement('style');
    s.id = 'v15-evidence-style';
    s.textContent = `
      .v15-audit{margin:12px 0;padding:11px 13px;border:1px solid #d0d5dd;border-radius:12px;background:#fcfcfd;display:flex;align-items:flex-start;justify-content:space-between;gap:10px;flex-wrap:wrap}
      .v15-audit.ok{border-color:#abefc6;background:#ecfdf3}.v15-audit.warn{border-color:#fedf89;background:#fffaeb}.v15-audit.partial{border-color:#b2ccff;background:#eff8ff}
      .v15-audit strong{font-size:11px}.v15-audit p{font-size:10px;color:#475467;margin:3px 0 0;line-height:1.45}.v15-audit .v15-tags{display:flex;gap:5px;flex-wrap:wrap}.v15-audit .v15-tag{font-size:9px;border-radius:999px;padding:4px 7px;background:#fff;border:1px solid #e4e7ec}
      .v15-stale{margin-top:8px;font-size:10px;color:#b54708}
    `;
    document.head.appendChild(s);
  }

  function folderOrNull() {
    const f = currentFolder();
    return f?.folder_id ? f : null;
  }

  async function workspace() {
    const f = folderOrNull();
    if (!f) return null;
    return api(`/api/collaboration?op=research_workspace&folder_id=${encodeURIComponent(f.folder_id)}`);
  }

  function auditCounts(audit) {
    const checks = Object.values(audit?.sections || {});
    const failed = checks.filter(x => x && x.passed === false).length;
    const adversarial = Object.values(audit?.adversarial?.sections || {});
    return {failed, total: checks.length, adversarial: adversarial.length};
  }

  function renderAudit(ws) {
    const root = q('#v15-audit-banner');
    if (!root) return;
    const doc = ws?.document || {};
    const intel = ws?.intelligence || {};
    const audit = intel.evidence_audit || doc?.evidence_manifest?.evidence_audit || {};
    const stale = intel.requires_novelty_reassessment;
    if (!audit.generated_at && !stale) {
      root.className = 'v15-audit partial';
      root.innerHTML = `<div><strong>${h(tr('Gate de evidencia listo','Evidence gate ready'))}</strong><p>${h(tr('Genera el borrador o ejecuta una auditoría para comprobar citas y respaldo full-text por sección.','Generate the draft or run an audit to check citations and full-text support section by section.'))}</p></div>`;
      return;
    }
    const counts = auditCounts(audit);
    const cls = audit.status === 'evidence_gate_partial' ? 'partial' : audit.passed ? 'ok' : 'warn';
    const title = audit.passed ? tr('Evidencia verificada','Evidence verified') : audit.status === 'evidence_gate_partial' ? tr('Auditoría parcial','Partial audit') : tr('Revisión de evidencia requerida','Evidence review required');
    const retrieval = audit.targeted_retrieval || {};
    root.className = `v15-audit ${cls}`;
    root.innerHTML = `<div><strong>${h(title)}</strong><p>${h(tr('El gate no modifica tu texto: comprueba referencias, afirmaciones sin respaldo, sobreafirmaciones y recuperación dirigida del corpus.','The gate does not modify your text: it checks references, unsupported claims, overstatements, and targeted corpus retrieval.'))}</p>${stale?`<div class="v15-stale">${h(tr('Hay literatura externa nueva: la novedad debe reevaluarse.','New external literature exists: novelty must be reassessed.'))}</div>`:''}</div><div class="v15-tags"><span class="v15-tag">${h(counts.failed)} ${h(tr('secciones con alerta','sections flagged'))}</span><span class="v15-tag">${h(retrieval.evidence_count||0)} chunks</span><span class="v15-tag">${h(retrieval.semantic_enabled?tr('semántico','semantic'):tr('léxico/fallback','lexical/fallback'))}</span></div>`;
  }

  function ensureControls() {
    const view = q('#view-collab');
    if (!view) return;
    ensureStyle();
    const actions = q('#v11-generate')?.closest('.v11-actions');
    if (actions && !q('#v15-verify')) {
      const b = document.createElement('button');
      b.id = 'v15-verify'; b.className = 'ghost';
      b.textContent = tr('Auditar evidencia y citas','Audit evidence and citations');
      b.onclick = verifyNow;
      actions.appendChild(b);
    }
    if (!q('#v15-audit-banner')) {
      const banner = document.createElement('div');
      banner.id = 'v15-audit-banner'; banner.className = 'v15-audit partial';
      const sections = q('#v11-sections');
      if (sections) sections.parentNode.insertBefore(banner, sections);
      else view.appendChild(banner);
    }
  }

  async function verifyNow() {
    const f = folderOrNull(); if (!f || busy) return;
    busy = true;
    const b = q('#v15-verify'); if (b) b.disabled = true;
    try {
      const r = await api('/api/collaboration?op=verify_document', {
        method:'POST',
        body:JSON.stringify({folder_id:f.folder_id, language:lang()})
      });
      renderAudit({document:r.document, intelligence:{evidence_audit:r.evidence_audit}});
      notify(r.evidence_audit?.passed ? tr('Auditoría de evidencia aprobada.','Evidence audit passed.') : tr('La auditoría detectó puntos que requieren revisión.','The audit found points requiring review.'));
      setTimeout(() => q('#v11-refresh')?.click(), 80);
    } catch (e) { notify(e.message, true); }
    finally { busy=false; if (b) b.disabled=false; }
  }

  async function autoReassessIfStale() {
    const f = folderOrNull(); if (!f || busy) return;
    try {
      const ws = await workspace();
      ensureControls(); renderAudit(ws);
      const intel = ws?.intelligence || {};
      const brief = ws?.document?.research_brief || {};
      if (!intel.requires_novelty_reassessment || !(brief.questions || []).length) return;
      const reason = String(intel.stale_reason || 'stale');
      const key = `scibrain:v15:reassessed:${f.folder_id}:${reason}`;
      if (sessionStorage.getItem(key) === '1') return;
      busy = true;
      await api('/api/collaboration?op=assess_brief', {
        method:'POST', body:JSON.stringify({folder_id:f.folder_id, language:lang()})
      });
      sessionStorage.setItem(key, '1');
      notify(tr('Novedad y brechas reevaluadas con la nueva literatura detectada.','Novelty and gaps reassessed against newly detected literature.'));
      setTimeout(() => q('#v11-refresh')?.click(), 80);
      const fresh = await workspace(); renderAudit(fresh);
    } catch (e) {
      console.warn('v0.15 automatic reassessment', e);
    } finally { busy=false; }
  }

  async function refreshAuditOnly() {
    try { ensureControls(); const ws = await workspace(); if (ws) renderAudit(ws); }
    catch (_) {}
  }

  function boot() {
    ensureControls();
    document.addEventListener('click', e => {
      if (e.target?.closest?.('[data-view="collab"]')) setTimeout(autoReassessIfStale, 180);
      if (e.target?.closest?.('#v11-refresh,#v11-generate,#v11-assess')) setTimeout(refreshAuditOnly, 800);
    });
    if (q('#view-collab')?.classList.contains('active')) setTimeout(autoReassessIfStale, 200);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
