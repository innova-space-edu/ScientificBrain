from scientific_brain.reflective import ReflectiveAgentRunner


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, system, user):
        return self.replies.pop(0)


def test_reflective_runner_revises_and_reviews():
    primary = FakeProvider([
        "draft output",
        "missing uncertainty",
        "revised output with uncertainty",
    ])
    independent = FakeProvider(["PASS"])
    result = ReflectiveAgentRunner(primary, independent).run(
        "theory",
        "produce analysis",
        "context",
    )
    assert result.draft == "draft output"
    assert "missing uncertainty" in result.self_critique
    assert result.revised == "revised output with uncertainty"
    assert result.review_passed
