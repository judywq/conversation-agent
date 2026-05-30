from backend.conversation.services.audio_tags import audio_tag_allowlist
from backend.conversation.services.audio_tags import filter_to_valid_audio_tags
from backend.conversation.services.audio_tags import format_audio_tags_for_prompt
from backend.conversation.services.audio_tags import strip_audio_tags


def test_elevenlabs_allowlist_size_matches_four_categories():
    # Narrator(9) + Emotional(22) + Delivery(11) + Human Reactions(24) = 66
    assert len(audio_tag_allowlist(provider="elevenlabs")) == 66


def test_fish_allowlist_size_matches_three_categories():
    # Basic(24) + Advanced(25) + Tone Markers(5) = 54
    assert len(audio_tag_allowlist(provider="fish")) == 54


def test_unknown_provider_falls_back_to_elevenlabs():
    assert audio_tag_allowlist(provider="openai") == audio_tag_allowlist(provider="elevenlabs")


def test_format_elevenlabs_categories_and_tags():
    rendered = format_audio_tags_for_prompt(provider="elevenlabs")
    assert "Narrator Point of View:" in rendered
    assert "Emotional State:" in rendered
    assert "Delivery Control:" in rendered
    assert "Human Reactions and Non-Verbal:" in rendered
    assert "[reflective]" in rendered
    assert "[deadpan]" in rendered
    assert "[rushed]" in rendered
    assert "[clears throat]" in rendered


def test_format_fish_categories_and_tags():
    rendered = format_audio_tags_for_prompt(provider="fish")
    assert "Basic Emotions:" in rendered
    assert "Advanced Emotions:" in rendered
    assert "Tone Markers:" in rendered
    assert "[curious]" in rendered
    assert "[soft tone]" in rendered


def test_filter_preserves_elevenlabs_tag_under_elevenlabs_provider():
    out = filter_to_valid_audio_tags("[reflective] Hmm, I'm not sure.", provider="elevenlabs")
    assert out == "[reflective] Hmm, I'm not sure."


def test_filter_drops_elevenlabs_tag_under_fish_provider():
    # [reflective] is ElevenLabs-only; under Fish it is unknown and should be stripped.
    out = filter_to_valid_audio_tags("[reflective] Hmm.", provider="fish")
    assert "reflective" not in out
    assert "Hmm." in out


def test_filter_preserves_fish_tag_under_fish_provider():
    out = filter_to_valid_audio_tags("[curious] Hmm.", provider="fish")
    assert out == "[curious] Hmm."


def test_filter_preserves_multiword_tag():
    out = filter_to_valid_audio_tags("[clears throat] Listen closely.", provider="elevenlabs")
    assert out == "[clears throat] Listen closely."


def test_filter_drops_unknown_bracket_content():
    out = filter_to_valid_audio_tags("[meta] Hmm. [agent_2]", provider="elevenlabs")
    assert "meta" not in out
    assert "agent_2" not in out
    assert "Hmm" in out


def test_filter_drops_parenthetical_content_even_when_valid_tag_present():
    out = filter_to_valid_audio_tags("[reflective] Hmm (as agent_2).", provider="elevenlabs")
    assert "[reflective]" in out
    assert "agent_2" not in out


def test_filter_normalises_case_and_inner_whitespace():
    out = filter_to_valid_audio_tags("[ Reflective ] Hmm.", provider="elevenlabs")
    assert out == "[reflective] Hmm."


def test_filter_keeps_multiple_valid_tags_drops_invalid_in_same_text():
    out = filter_to_valid_audio_tags(
        "[reflective] One. [meta] Two. [deliberate] Three.",
        provider="elevenlabs",
    )
    assert "[reflective]" in out
    assert "[deliberate]" in out
    assert "meta" not in out


def test_strip_removes_valid_and_invalid_brackets_and_parens():
    out = strip_audio_tags("[reflective] Hmm. [meta] (as agent_2).")
    assert "reflective" not in out
    assert "meta" not in out
    assert "agent_2" not in out
    assert out.startswith("Hmm")


def test_strip_collapses_whitespace_and_punctuation_spacing():
    out = strip_audio_tags("[reflective]  Hmm , I'm not sure .")
    assert "  " not in out
    assert " ," not in out
    assert " ." not in out
    assert "Hmm, I'm not sure." in out


def test_strip_handles_empty_input():
    assert strip_audio_tags("") == ""


def test_filter_handles_empty_input():
    assert filter_to_valid_audio_tags("", provider="elevenlabs") == ""
