import random
from dataclasses import dataclass


_ENGLISH_NAMES = [
    "Ava",
    "Ethan",
    "Emma",
    "Isabella",
    "Liam",
    "Lucas",
    "Mia",
    "Noah",
    "Oliver",
    "Sophia",
]


@dataclass(frozen=True)
class AgentVoicePreset:
    name: str
    chinese_name: str
    gender: str
    title: str
    reference_id: str
    note: str


AGENT_VOICE_PRESETS = [
    AgentVoicePreset(
        name="Liam",
        chinese_name="利亚姆",
        gender="male",
        title="Energetic Male",
        reference_id="802e3bc2b27e49c2995d23ef70e6ac89",
        note="young, clear, energetic English male voice",
    ),
    AgentVoicePreset(
        name="Ethan",
        chinese_name="伊森",
        gender="male",
        title="ELITE",
        reference_id="d8a1340984ee4b63ad1ffae27a6a4339",
        note="confident sports-commentary style English male voice",
    ),
    AgentVoicePreset(
        name="Noah",
        chinese_name="诺亚",
        gender="male",
        title="ALEX_CHIKNA",
        reference_id="52e0660e03fe4f9a8d2336f67cab5440",
        note="fast, enthusiastic English male voice",
    ),
    AgentVoicePreset(
        name="Oliver",
        chinese_name="奥利弗",
        gender="male",
        title="id-alex",
        reference_id="1d52151a55eb4878a997bd06e816b5f6",
        note=(
            "A professional and calm middle-aged male voice with a clear, articulate delivery. "
            "This voice features a smooth, medium-pitched tone, making it well-suited for "
            "storytelling and narration."
        ),
    ),
    AgentVoicePreset(
        name="Lucas",
        chinese_name="卢卡斯",
        gender="male",
        title="id-Ethan",
        reference_id="536d3a5e000945adb7038665781a4aca",
        note="deep, cinematic character-style English male voice",
    ),
    AgentVoicePreset(
        name="Emma",
        chinese_name="艾玛",
        gender="female",
        title="id-ss",
        reference_id="1954744f560e4a0fa316bd6ec8a6b055",
        note="A cute e-girl to chat with you.",
    ),
    AgentVoicePreset(
        name="Sophia",
        chinese_name="索菲亚",
        gender="female",
        title="id-Paula",
        reference_id="c2623f0c075b4492ac367989aee1576f",
        note=(
            "A professional and clear female voice with a middle-aged tone. This voice is ideal "
            "for educational content and professional presentations, characterized by its "
            "confident and friendly delivery."
        ),
    ),
    AgentVoicePreset(
        name="Ava",
        chinese_name="艾娃",
        gender="female",
        title="id-Friendly Women",
        reference_id="b545c585f631496c914815291da4e893",
        note=(
            "A bright and energetic female voice with a youthful, professional tone. Her "
            "delivery is clear and enthusiastic, making it highly engaging for a variety of media."
        ),
    ),
    AgentVoicePreset(
        name="Isabella",
        chinese_name="伊莎贝拉",
        gender="female",
        title="id-Ogechi old women",
        reference_id="edb42faa2d0e4cd5aa6aa1ae67de2e86",
        note="cute character-style female voice",
    ),
    AgentVoicePreset(
        name="Mia",
        chinese_name="米娅",
        gender="female",
        title="id-Female Voice",
        reference_id="2a9605eeafe84974b5b20628d42c0060",
        note=(
            "A young female voice with a calm, reflective tone and a smooth, measured pace. "
            "She sounds thoughtful and authentic, making this voice suitable for personal "
            "narratives or social media content."
        ),
    ),
]

_VOICE_PRESETS_BY_NAME = {preset.name: preset for preset in AGENT_VOICE_PRESETS}
_VOICE_PRESETS_BY_PERSONA = {
    "Discussion Driver": {
        "male": _VOICE_PRESETS_BY_NAME["Liam"],
        "female": _VOICE_PRESETS_BY_NAME["Ava"],
    },
    "Fact Checker": {
        "male": _VOICE_PRESETS_BY_NAME["Oliver"],
        "female": _VOICE_PRESETS_BY_NAME["Sophia"],
    },
    "Idea Explorer": {
        "male": _VOICE_PRESETS_BY_NAME["Noah"],
        "female": _VOICE_PRESETS_BY_NAME["Mia"],
    },
    "Supportive Builder": {
        "male": _VOICE_PRESETS_BY_NAME["Ethan"],
        "female": _VOICE_PRESETS_BY_NAME["Emma"],
    },
    "Tense Skeptic": {
        "male": _VOICE_PRESETS_BY_NAME["Lucas"],
        "female": _VOICE_PRESETS_BY_NAME["Isabella"],
    },
}


def pick_unique_names(count: int, *, rng: random.Random | None = None) -> list[str]:
    r = rng or random
    pool = list(_ENGLISH_NAMES)
    r.shuffle(pool)
    if count <= 0:
        return []
    if count <= len(pool):
        return pool[:count]
    # Fallback: allow repeats with suffixes if we ever exceed the pool size.
    out: list[str] = []
    i = 0
    while len(out) < count:
        base = pool[i % len(pool)]
        suffix = (i // len(pool)) + 1
        out.append(f"{base}{suffix}")
        i += 1
    return out


def voice_reference_id_for_name(name: str) -> str:
    preset = _VOICE_PRESETS_BY_NAME.get(name.strip())
    return preset.reference_id if preset else ""


def pick_voice_preset_for_persona(
    persona_name: str,
    *,
    gender: str | None = None,
    rng: random.Random | None = None,
) -> AgentVoicePreset:
    presets = _VOICE_PRESETS_BY_PERSONA.get(persona_name.strip())
    if presets:
        requested_gender = str(gender or "").strip().lower()
        if requested_gender in presets:
            return presets[requested_gender]
        r = rng or random
        return presets[r.choice(["male", "female"])]

    r = rng or random
    return r.choice(AGENT_VOICE_PRESETS)


def persona_voice_presets() -> dict[str, dict[str, AgentVoicePreset]]:
    return {persona: dict(gender_map) for persona, gender_map in _VOICE_PRESETS_BY_PERSONA.items()}
