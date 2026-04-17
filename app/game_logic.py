"""Math mini-game helpers for the kiosk UI."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class MathRound:
    expression: str
    correct_answer: int
    options: list[int]
    operator: str


class MathGameGenerator:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def build_round(self, option_count: int, streak: int = 0) -> MathRound:
        option_count = max(2, int(option_count))
        operator = self._pick_operator(streak)

        if operator == "+":
            left, right, answer = self._addition_question()
        elif operator == "-":
            left, right, answer = self._subtraction_question()
        elif operator == "*":
            left, right, answer = self._multiplication_question()
        else:
            left, right, answer = self._division_question()

        options = self._build_options(answer, option_count, operator)
        self._rng.shuffle(options)
        return MathRound(
            expression=f"{left} {operator} {right} = ?",
            correct_answer=answer,
            options=options,
            operator=operator,
        )

    def _pick_operator(self, streak: int) -> str:
        # As streak grows, include more * and / questions.
        if streak >= 8:
            weighted = ["+", "-", "*", "*", "/", "/"]
        elif streak >= 4:
            weighted = ["+", "-", "*", "/"]
        else:
            weighted = ["+", "-", "*", "/"]
        return self._rng.choice(weighted)

    def _addition_question(self) -> tuple[int, int, int]:
        left = self._rng.randint(1, 99)
        right = self._rng.randint(1, 100 - left)
        return left, right, left + right

    def _subtraction_question(self) -> tuple[int, int, int]:
        left = self._rng.randint(1, 100)
        right = self._rng.randint(1, left)
        return left, right, left - right

    def _multiplication_question(self) -> tuple[int, int, int]:
        while True:
            left = self._rng.randint(2, 12)
            right = self._rng.randint(2, 12)
            answer = left * right
            if answer <= 100:
                return left, right, answer

    def _division_question(self) -> tuple[int, int, int]:
        while True:
            divisor = self._rng.randint(2, 12)
            quotient = self._rng.randint(1, 12)
            dividend = divisor * quotient
            if dividend <= 100 and quotient != 0:
                return dividend, divisor, quotient

    def _build_options(self, answer: int, option_count: int, operator: str) -> list[int]:
        values = {int(answer)}
        spread = max(4, min(25, abs(int(answer)) + 5))

        while len(values) < option_count:
            delta = self._rng.randint(1, spread)
            sign = 1 if self._rng.random() < 0.5 else -1
            candidate = int(answer) + sign * delta

            # Keep results practical for kiosk buttons.
            if operator in ("+", "-", "*", "/"):
                candidate = max(0, candidate)

            if candidate not in values:
                values.add(candidate)

        return list(values)
