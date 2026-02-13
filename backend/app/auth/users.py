from __future__ import annotations

import bcrypt


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


USERS: dict[str, dict] = {
    "analyst1": {
        "username": "analyst1",
        "password_hash": _hash_pw("analyst123"),
        "display_name": "Alice Chen",
        "role": "Research Analyst",
        "email": "kevintdonadio@gmail.com",
    },
    "analyst2": {
        "username": "analyst2",
        "password_hash": _hash_pw("analyst456"),
        "display_name": "Bob Martinez",
        "role": "Research Analyst",
        "email": "kevintdonadio@gmail.com",
    },
    "pm1": {
        "username": "pm1",
        "password_hash": _hash_pw("pm789"),
        "display_name": "Carol Wu",
        "role": "Portfolio Manager",
        "email": "kevintdonadio@gmail.com",
    },
}
