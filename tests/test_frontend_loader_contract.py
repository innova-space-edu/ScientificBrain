from pathlib import Path


def test_ux_flow_does_not_block_domcontentloaded():
    text = Path('assets/ux_flow.js').read_text(encoding='utf-8')
    assert 'document.write' not in text
    assert 'DOMContentLoaded' in text
    assert 'createElement(\'script\')' in text or 'createElement("script")' in text


def test_loader_keeps_scientific_modules_ordered():
    text = Path('assets/ux_flow.js').read_text(encoding='utf-8')
    names = [
        'ux_flow_base.js',
        'adaptive_jobs.js',
        'adaptive_science.js',
        'adaptive_agents.js',
        'runtime_repair.js',
        'research_workspace_v11.js',
        'research_workspace_v12.js',
        'research_workspace_v14.js',
        'research_workspace_v15.js',
        'research_workspace_v16.js',
        'research_workspace_v17.js',
    ]
    positions = [text.index(name) for name in names]
    assert positions == sorted(positions)
