from scientific_brain.graph_models import EpistemicState, GraphNodeType, ScientificGraphNode
from scientific_brain.graph_service import ScientificGraphService


def _claim(node_id: str, label: str) -> ScientificGraphNode:
    return ScientificGraphNode(
        node_id=node_id,
        node_type=GraphNodeType.CLAIM,
        label=label,
        paper_id=f"paper:{node_id}",
        epistemic_state=EpistemicState.SUPPORTED,
    )


def test_open_question_claim_selection_prioritizes_relevant_validated_claims():
    service = ScientificGraphService(
        snapshot_store=None,  # type: ignore[arg-type]
        workspace_store=None,  # type: ignore[arg-type]
        graph_store=None,  # type: ignore[arg-type]
        provider=None,
    )
    claims = [
        _claim("c1", "Impulse bit increases with discharge current in the measured regime."),
        _claim("c2", "Optical plume expansion was measured by fast imaging."),
        _claim("c3", "Thermal drift affects a separate diagnostic."),
    ]

    selected = service._claims_for_open_question(
        "How does discharge current affect impulse bit?",
        claims,
        limit=3,
    )

    assert selected[0].node_id == "c1"
    assert {node.node_id for node in selected} == {"c1", "c2", "c3"}


def test_open_question_selection_is_bounded_when_no_lexical_match_exists():
    service = ScientificGraphService(
        snapshot_store=None,  # type: ignore[arg-type]
        workspace_store=None,  # type: ignore[arg-type]
        graph_store=None,  # type: ignore[arg-type]
        provider=None,
    )
    claims = [_claim(f"c{i}", f"Validated claim {i}") for i in range(10)]

    selected = service._claims_for_open_question("unrelated astrophysical question", claims, limit=4)

    assert len(selected) == 4
