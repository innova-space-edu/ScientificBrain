from pathlib import Path


def test_resume_api_reconstructs_only_from_persistent_project():
    text = Path('api/resume.py').read_text(encoding='utf-8')
    assert 'scibrain_states' in text
    assert 'DefinedProjectService' in text
    assert 'snapshot.load_project' in text
    assert 'reconstruct' in text
    assert 'scibrain_research_documents' in text


def test_frontend_restores_context_after_authentication_and_folder_change():
    text = Path('assets/ux_flow.js').read_text(encoding='utf-8')
    assert "api('/api/resume'" in text
    assert 'restorePersistentContext' in text
    assert 'restoreWithDeadline' in text
    assert '__SB_PERSISTENT_FOLDER_HOOK__' in text
    assert "localStorage.setItem('scibrain_session'" in text
