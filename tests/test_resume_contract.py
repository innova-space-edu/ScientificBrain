from pathlib import Path


def test_frontend_recovers_persistent_session_without_new_serverless_function():
    text = Path('assets/ux_flow.js').read_text(encoding='utf-8')
    assert 'scibrain_states' in text
    assert 'scibrain_projects' in text
    assert 'scibrain_research_documents' in text
    assert "api('/api/projects'" in text
    assert 'restorePersistentContext' in text
    assert 'restoreWithDeadline' in text
    assert '__SB_PERSISTENT_FOLDER_HOOK__' in text


def test_recovery_is_bounded_and_owner_scoped():
    text = Path('assets/ux_flow.js').read_text(encoding='utf-8')
    assert 'owner_id=eq.' in text
    assert 'timeoutMs=7000' in text
    assert 'allowFolderSwitch' in text
