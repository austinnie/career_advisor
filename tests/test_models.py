# tests/test_models.py
def test_occupation_accepts_core_tasks():
    from career_advisor.models import Occupation
    occ = Occupation(
        occupation_id="X", preferred_name="X", occupation_family="工程与制造",
        core_tasks=[{"task_id": "t", "task_statement": "描述", "source": "CN_DADIAN"}],
    )
    assert occ.core_tasks[0]["task_statement"] == "描述"