from scientific_brain.agent_runtime import ConfiguredScientificAgent
from scientific_brain.artifacts import LocalArtifactStore
from scientific_brain.memory import ScientificMemory


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, system, user):
        return self.replies.pop(0)


def test_configured_agent_runs_reflective_cycle_and_persists(tmp_path):
    provider = FakeProvider([
        '{"outputs":{"validated_scope":{"ok":true},"work_plan":[],"decision_log":[]},"evidence_ids":[],"unresolved_issues":[],"assumptions":[],"blocking_issues":[]}',
        "No defect found.",
        '{"outputs":{"validated_scope":{"ok":true},"work_plan":[],"decision_log":[]},"evidence_ids":[],"unresolved_issues":[],"assumptions":[],"blocking_issues":[]}',
        "PASS",
    ])
    agent = ConfiguredScientificAgent("research_director", provider)
    execution = agent.run({"project_definition": {"project_id": "p1"}, "research_state": {}})
    assert execution.review_passed
    assert "validated_scope" in execution.payload.outputs

    memory = ScientificMemory(tmp_path / "brain.db")
    store = LocalArtifactStore(memory)
    records = agent.persist("session-1", execution, store)
    assert records
    assert store.latest("session-1", "validated_scope").accepted
    memory.close()
