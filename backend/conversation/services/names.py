import random


_ENGLISH_NAMES = [
    "Alex",
    "Ava",
    "Ben",
    "Chloe",
    "Daniel",
    "Ella",
    "Ethan",
    "Grace",
    "Hannah",
    "Henry",
    "Isla",
    "Jack",
    "James",
    "Liam",
    "Lily",
    "Lucas",
    "Mia",
    "Noah",
    "Oliver",
    "Sophie",
    "Theo",
    "Zoe",
]


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

