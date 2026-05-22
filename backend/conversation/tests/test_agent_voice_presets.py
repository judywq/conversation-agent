from backend.conversation.services.names import persona_voice_presets
from backend.conversation.services.names import pick_voice_preset_for_persona


def test_each_persona_has_one_male_and_one_female_voice_preset():
    presets = persona_voice_presets()

    assert set(presets) == {
        "Discussion Driver",
        "Fact Checker",
        "Idea Explorer",
        "Supportive Builder",
        "Tense Skeptic",
    }
    for gender_map in presets.values():
        assert set(gender_map) == {"male", "female"}
        assert gender_map["male"].gender == "male"
        assert gender_map["female"].gender == "female"
        assert gender_map["male"].reference_id
        assert gender_map["female"].reference_id


def test_can_pick_specific_gender_for_persona():
    male = pick_voice_preset_for_persona("Fact Checker", gender="male")
    female = pick_voice_preset_for_persona("Fact Checker", gender="female")

    assert male.name == "Oliver"
    assert male.reference_id == "1d52151a55eb4878a997bd06e816b5f6"
    assert female.name == "Sophia"
    assert female.reference_id == "c2623f0c075b4492ac367989aee1576f"
