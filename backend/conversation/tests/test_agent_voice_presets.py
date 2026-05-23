from django.test import override_settings

from backend.conversation.services.names import AGENT_VOICE_PRESETS
from backend.conversation.services.names import CEFR_LEVEL_VOICE_PRESET_NAMES
from backend.conversation.services.names import cefr_tts_voice_for_level
from backend.conversation.services.names import persona_voice_presets
from backend.conversation.services.names import pick_voice_preset_for_persona
from backend.conversation.services.names import provider_voice_id


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
        assert gender_map["male"].elevenlabs_voice_id
        assert gender_map["female"].elevenlabs_voice_id


def test_can_pick_specific_gender_for_persona():
    male = pick_voice_preset_for_persona("Fact Checker", gender="male")
    female = pick_voice_preset_for_persona("Fact Checker", gender="female")

    assert male.name == "Oliver"
    assert male.reference_id == "1d52151a55eb4878a997bd06e816b5f6"
    assert male.elevenlabs_voice_id == "scOwDtmlUjD3prqpp97I"
    assert female.name == "Sophia"
    assert female.reference_id == "c2623f0c075b4492ac367989aee1576f"
    assert female.elevenlabs_voice_id == "Z3R5wn05IrDiVCyEkUrK"


def test_all_voice_presets_have_elevenlabs_voice_ids():
    assert len(AGENT_VOICE_PRESETS) == 10
    for preset in AGENT_VOICE_PRESETS:
        assert preset.elevenlabs_voice_id


@override_settings(TTS_PROVIDER="elevenlabs")
def test_provider_voice_id_returns_elevenlabs_id():
    preset = pick_voice_preset_for_persona("Fact Checker", gender="male")
    assert provider_voice_id(preset) == "scOwDtmlUjD3prqpp97I"


@override_settings(TTS_PROVIDER="fish")
def test_provider_voice_id_returns_fish_reference_id():
    preset = pick_voice_preset_for_persona("Fact Checker", gender="male")
    assert provider_voice_id(preset) == "1d52151a55eb4878a997bd06e816b5f6"


@override_settings(TTS_PROVIDER="openai")
def test_provider_voice_id_returns_empty_for_openai():
    preset = pick_voice_preset_for_persona("Fact Checker", gender="male")
    assert provider_voice_id(preset) == ""


def test_cefr_level_voice_preset_names_cover_all_levels():
    assert set(CEFR_LEVEL_VOICE_PRESET_NAMES) == {"A1", "A2", "B1", "B2", "C1", "C2"}


@override_settings(TTS_PROVIDER="elevenlabs", ELEVENLABS_DEFAULT_VOICE_ID="")
def test_cefr_tts_voice_for_level_returns_elevenlabs_ids() -> None:
    assert cefr_tts_voice_for_level("A1") == "tnSpp4vdxKPjI9w0GnoV"
    assert cefr_tts_voice_for_level("A2") == "5l5f8iK3YPeGga21rQIX"
    assert cefr_tts_voice_for_level("B1") == "BIvP0GN1cAtSRTxNHnWS"
    assert cefr_tts_voice_for_level("B2") == "Z3R5wn05IrDiVCyEkUrK"
    assert cefr_tts_voice_for_level("C1") == "BZgkqPqms7Kj9ulSkVzn"
    assert cefr_tts_voice_for_level("C2") == "scOwDtmlUjD3prqpp97I"


@override_settings(TTS_PROVIDER="openai", OPENAI_TTS_VOICE="nova")
def test_cefr_tts_voice_for_level_returns_openai_voice() -> None:
    assert cefr_tts_voice_for_level("B2") == "nova"
