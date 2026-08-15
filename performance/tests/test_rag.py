from rag import rag_pipeline


def _mock_raw_results():
    return [
        {
            "rank": 1,
            "filename": "case_0001.txt",
            "text": (
                "Case 1\n"
                "Cause of Delay : Labour shortage\n"
                "Corrective Action Taken:\n"
                "  Crew reallocated from nearby site\n"
                "Construction Status:\n"
                "  Completed with minor delay\n"
            ),
            "score": 0.11,
        },
        {
            "rank": 2,
            "filename": "case_0002.txt",
            "text": (
                "Case 2\n"
                "Cause of Delay : Material shortage\n"
                "Corrective Action Taken:\n"
                "  Early bulk procurement arranged\n"
                "Construction Status:\n"
                "  Recovered after two weeks\n"
            ),
            "score": 0.22,
        },
        {
            "rank": 3,
            "filename": "case_0003.txt",
            "text": (
                "Case 3\n"
                "Cause of Delay : Heavy rain\n"
                "Corrective Action Taken:\n"
                "  Drainage and pumping setup installed\n"
                "Construction Status:\n"
                "  Stabilized after weather improved\n"
            ),
            "score": 0.33,
        },
    ]


def _retrieve_cases(monkeypatch):
    monkeypatch.setattr(rag_pipeline, "embed_texts", lambda texts: [[0.0]])
    monkeypatch.setattr(
        rag_pipeline,
        "search",
        lambda query_embedding, top_k=3: _mock_raw_results()[:top_k],
    )
    return rag_pipeline.retrieve_similar_cases(
        district="Colombo",
        phase_group="Foundations",
        delay_category="Labour",
        top_k=3,
    )


def test_returns_three_similar_cases(monkeypatch):
    cases = _retrieve_cases(monkeypatch)
    assert len(cases) == 3


def test_each_case_has_structured_fields(monkeypatch):
    cases = _retrieve_cases(monkeypatch)
    assert all("cause_of_delay" in case for case in cases)
    assert all("corrective_action_taken" in case for case in cases)
    assert all("construction_status" in case for case in cases)
