"""Carried IND-BANK-002 review findings, closed as tests (IB2-R1-1, IB2-R1-3); no behaviour change."""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEED = 3003
STRING_COUNT = 50_000


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IB1 = _load("ind_bank_001_handler_for_carried", "ci/handlers/ind_bank_001.py")
IB2 = _load("ind_bank_002_handler_for_carried", "ci/handlers/ind_bank_002.py")


def _iban_shape(rng: random.Random) -> str:
    """A mod-97-valid IBAN shape computed at run time from an unassigned country code (never a committed literal)."""
    body = "".join(rng.choice("0123456789") for _ in range(rng.randint(11, 20)))
    numeric = "".join(str(int(character, 36)) for character in body + "XX00")
    check = 98 - int(numeric) % 97
    return f"XX{check:02d}{body}"


def _seeded_strings() -> list[str]:
    rng = random.Random(SEED)
    pieces = "0123456789 -ABXYZ"
    strings = []
    for index in range(STRING_COUNT):
        parts = ["".join(rng.choice(pieces) for _ in range(rng.randint(0, 24)))]
        roll = index % 5
        if roll == 1:
            parts.append(IB2.build_luhn_run(rng.randint(13, 19)))
        elif roll == 2:
            run = IB2.build_luhn_run(16)
            parts.append(" ".join(run[position:position + 4] for position in range(0, 16, 4)))
        elif roll == 3:
            parts.append(_iban_shape(rng))
        parts.append("".join(rng.choice(pieces) for _ in range(rng.randint(0, 24))))
        rng.shuffle(parts)
        strings.append(rng.choice(["", " ", "-", "x"]).join(parts))
    return strings


def test_ib2_r1_1_strict_hit_spans_equal_the_strict_loop() -> None:
    """IB2-R1-1 (the C4 equivalence): the span scan behind the raw scan and the strict loop agree on 50 000 strings."""
    strings = _seeded_strings()
    assert len(strings) == STRING_COUNT
    divergences = 0
    hits = 0
    for text in strings:
        spans = sorted({hit for hit, _, _ in IB1._strict_hit_spans(text)})
        strict = IB1.find_disallowed(text)
        hits += bool(strict)
        if spans != strict or IB2.find_disallowed(text) != strict:
            divergences += 1
    assert divergences == 0
    assert hits > STRING_COUNT // 10


def test_ib2_r1_1_the_002_scanner_is_the_001_scanner() -> None:
    assert IB2.PREDECESSOR_MODULE == "ind_bank_001_handler"
    assert IB2.find_disallowed.__module__ == IB2.PREDECESSOR_MODULE
    assert IB2.find_disallowed.__code__.co_code == IB1.find_disallowed.__code__.co_code


def test_ib2_r1_3_main_fails_closed_outside_the_mapped_exceptions(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """IB2-R1-3: main() maps only ValueError, KeyError and TypeError to the refusal; anything else is not swallowed."""

    def broken() -> dict:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(IB2, "run", broken)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        IB2.main(["banking"])
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("error", [ValueError, KeyError, TypeError])
def test_ib2_r1_3_mapped_exceptions_become_the_refusal(error: type[Exception], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def broken() -> dict:
        raise error("synthetic")

    monkeypatch.setattr(IB2, "run", broken)
    with pytest.raises(SystemExit, match="IND-BANK-002 refuses"):
        IB2.main(["banking"])
    assert capsys.readouterr().out == ""
