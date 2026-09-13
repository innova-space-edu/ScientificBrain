from scientific_brain.autonomous_jobs import _v012_specialist_agents
from scientific_brain.models import PaperKind, SpecialistReview


class DummyProvider:
    def for_task(self, task):
        return self


def roles(kind):
    return [getattr(agent, "role", "") for agent in _v012_specialist_agents(DummyProvider(), kind)]


def test_specialist_review_accepts_math_and_statistics_roles():
    Mathematical = SpecialistReview(paper_id="p", role="mathematical")
    Statistical = SpecialistReview(paper_id="p", role="statistical")
    assert Mathematical.role == "mathematical"
    assert Statistical.role == "statistical"


def test_experimental_pipeline_adds_math_and_statistics_before_final_audits():
    result = roles(PaperKind.EXPERIMENTAL)
    assert "mathematical" in result
    assert "statistical" in result
    assert result[-2:] == ["adversarial", "reproducibility"]


def test_theoretical_pipeline_adds_math_but_not_statistics():
    result = roles(PaperKind.THEORETICAL)
    assert "mathematical" in result
    assert "statistical" not in result
