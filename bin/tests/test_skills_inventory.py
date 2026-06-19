from skill_forge.skills_inventory import list_skills


def test_lists_both_skills_with_names_and_origin(sample_skills_dir):
    skills = list_skills(sample_skills_dir)
    by_name = {s["name"]: s for s in skills}
    assert set(by_name) == {"route-inbox", "compose-shorts"}
    assert by_name["route-inbox"]["origin"] == "authored"
    assert by_name["compose-shorts"]["origin"] == "skill-forge"
    assert by_name["route-inbox"]["description"].startswith("Route inbox")
    assert by_name["route-inbox"]["path"].endswith("SKILL.md")


def test_empty_dir_returns_empty(tmp_path):
    assert list_skills(tmp_path / "nope") == []
