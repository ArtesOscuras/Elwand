"""Temporary username generation from the People inventory.

Uses DICMA's ``users`` mode to derive possible usernames for every registered
person. The result is only used in memory for a brute-force run; it is never
written to the dictionaries directory.
"""


def usernames_from_people():
    """Return the deduplicated possible usernames for all people, sorted."""
    try:
        from src.machines.people_db import load_people
        from src.tools.dicma import engine as dicma
    except Exception:
        return []
    try:
        people = load_people()
    except Exception:
        return []

    prev_light = getattr(dicma, "LIGHT_MODE", False)
    dicma.LIGHT_MODE = False
    out = []
    seen = set()
    try:
        for person in people:
            full = (f"{person.get('first_name', '')} "
                    f"{person.get('last_name', '')}").strip()
            if not full:
                full = (person.get("username") or "").strip()
            if not full:
                continue
            try:
                names = dicma.generate_usernames(full)
            except Exception:
                continue
            for name in names:
                name = (name or "").strip()
                key = name.lower()
                if name and key not in seen:
                    seen.add(key)
                    out.append(name)
    finally:
        dicma.LIGHT_MODE = prev_light

    out.sort(key=str.lower)
    return out
