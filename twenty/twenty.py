#!/usr/bin/env python3
"""20 Questions — AI-powered CLI guessing game."""

import json
import os
import re
import sys
import time

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

MAX_QUESTIONS = 20

SYSTEM_PROMPT = """\
You are playing 20 Questions. The human has secretly chosen something — it could be \
an animal, vegetable, mineral, a specific person, a place, an abstract concept, or \
anything else.

Your goal is to identify it by asking strategic yes/no questions, then guess.

Strategy:
- Start broad to establish category (living/non-living, natural/man-made, etc.)
- Use answers to binary-search down rapidly
- Never repeat information already established
- When confidence is high (roughly 85%+), stop asking and guess
- You may guess before using all questions — do so as soon as you're confident

Respond with ONLY a JSON object — no other text, no markdown fences.

To ask a question:
{"action": "ask", "question": "Is it a living thing?"}

To make a guess:
{"action": "guess", "guess": "a grand piano", "reasoning": "It's large, man-made, found indoors, makes music, and has black and white keys."}

If you've used all your questions, always respond with a guess, never a question.\
"""


def _extract_json(text: str) -> dict:
    """Extract a JSON object from text using multiple fallback strategies."""
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences robustly
    stripped = re.sub(r"^```(?:json)?\s*", "", text)
    stripped = re.sub(r"\s*```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 3: find the first {...} block in the text
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in response: {text!r}")


def call_claude(history: list[dict], questions_left: int, _attempt: int = 0) -> dict:
    """Ask Claude for the next move; returns a parsed action dict.
    Retries up to 3 times on parse failures before giving up gracefully."""
    client = anthropic.Anthropic()

    if not history:
        user_msg = (
            f"I've thought of something. You have {MAX_QUESTIONS} questions. "
            "Ask your first question."
        )
    else:
        lines = [f"Q{i}: {h['question']} → {h['answer']}" for i, h in enumerate(history, 1)]
        summary = "\n".join(lines)
        if questions_left == 0:
            user_msg = (
                f"Here is everything we know:\n{summary}\n\n"
                "You have no questions left. Make your best guess now."
            )
        else:
            user_msg = (
                f"Here is everything we know:\n{summary}\n\n"
                f"You have {questions_left} question(s) left. What is your next move?"
            )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    try:
        return _extract_json(text)
    except ValueError:
        if _attempt < 2:
            time.sleep(1)
            return call_claude(history, questions_left, _attempt + 1)
        # All retries exhausted — synthesise a safe fallback
        if questions_left == 0:
            return {"action": "guess", "guess": "I'm not sure", "reasoning": ""}
        return {"action": "ask", "question": "Is it something you can physically touch?"}


def color_for_answer(answer: str) -> str:
    a = answer.lower()
    if a in ("yes", "y", "correct", "true"):
        return "bold green"
    if a in ("no", "n", "nope", "false", "never"):
        return "bold red"
    return "bold yellow"


def show_history(history: list[dict]):
    if not history:
        return
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("#", style="dim", width=3)
    t.add_column("Question", style="white")
    t.add_column("Answer")
    for i, h in enumerate(history, 1):
        c = color_for_answer(h["answer"])
        t.add_row(f"{i}.", h["question"], f"[{c}]{h['answer']}[/]")
    console.print(t)


def prompt_answer() -> str:
    while True:
        ans = console.input("[bold cyan]> [/]").strip()
        if ans:
            return ans
        console.print("[dim]Please enter an answer.[/]")


def show_guess_panel(guess: str, reasoning: str, q_used: int):
    body = f"[bold bright_yellow]{guess}[/]"
    if reasoning:
        body += f"\n\n[dim]{reasoning}[/]"
    console.print()
    console.print(Panel(body, title=f"[bold]My guess  (after {q_used} question(s))[/]", border_style="bright_yellow"))


def play():
    console.print()
    console.print(
        Panel(
            "[bold]Think of anything[/] — a person, animal, object, place, idea, whatever.\n"
            "Keep it secret. I'll ask up to [bold]20 yes/no questions[/] to figure it out.\n\n"
            "[dim]Answer freely: yes · no · sometimes · kind of · not really · unknown[/]",
            title="[bold bright_yellow]  20 QUESTIONS  [/]",
            border_style="bright_yellow",
            padding=(1, 2),
        )
    )

    console.input("\n[dim]Got something in mind? Press Enter to start…[/] ")
    console.clear()

    history: list[dict] = []

    for q_num in range(1, MAX_QUESTIONS + 1):
        questions_left = MAX_QUESTIONS - q_num  # after this one is asked

        # Header
        remaining = MAX_QUESTIONS - q_num + 1
        bar_color = "green" if remaining > 10 else "yellow" if remaining > 5 else "red"
        console.print(f"\n[{bar_color}]Question {q_num} / {MAX_QUESTIONS}[/]  [dim]{remaining} remaining[/]")

        with console.status("[dim]Thinking…[/]"):
            move = call_claude(history, MAX_QUESTIONS - q_num + 1)

        if move["action"] == "guess":
            show_guess_panel(move["guess"], move.get("reasoning", ""), q_num - 1)
            correct = console.input("\n[bold cyan]Did I get it? (yes/no):[/] ").strip().lower()
            if correct.startswith("y"):
                console.print(f"\n[bold green]Got it in {q_num - 1} question(s)![/]")
            else:
                console.print("\n[bold red]I give up — what were you thinking of?[/] ", end="")
                reveal = console.input("").strip()
                console.print(f"\n[dim]'{reveal}' — well played![/]")
            break

        # It's a question — print and get answer
        console.print(f"\n[bold white]{move['question']}[/]\n")
        answer = prompt_answer()
        history.append({"question": move["question"], "answer": answer})

    else:
        # All 20 questions used; force a final guess
        console.print("\n[dim]That's 20 questions — making my final guess…[/]")
        with console.status("[dim]Thinking…[/]"):
            move = call_claude(history, 0)

        guess = move.get("guess") or "I'm not sure"
        show_guess_panel(guess, move.get("reasoning", ""), MAX_QUESTIONS)
        correct = console.input("\n[bold cyan]Did I get it? (yes/no):[/] ").strip().lower()
        if correct.startswith("y"):
            console.print("\n[bold green]Got it on the last question![/]")
        else:
            console.print("\n[bold red]You win! What were you thinking of?[/] ", end="")
            reveal = console.input("").strip()
            console.print(f"\n[dim]'{reveal}' — I'll get it next time![/]")

    # Summary
    if history:
        console.print()
        console.print("[bold dim]── Game summary ──[/]")
        show_history(history)

    console.print()


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY is not set.[/]")
        sys.exit(1)
    play()
