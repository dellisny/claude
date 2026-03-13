#!/usr/bin/env python3
"""Mastermind — I pick the secret code, you guess it."""

import random
import sys
from itertools import product

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

PEGS       = 4
COLORS     = 6
MAX_GUESSES = 12

COLOR_STYLE = {
    1: ("Red",    "bold red"),
    2: ("Blue",   "bold blue"),
    3: ("Green",  "bold green"),
    4: ("Yellow", "bold yellow"),
    5: ("Orange", "bold magenta"),
    6: ("Purple", "bold bright_cyan"),
}
PEG = "●"


def score(guess: tuple, secret: tuple) -> tuple[int, int]:
    black = sum(g == s for g, s in zip(guess, secret))
    white = sum(min(guess.count(c), secret.count(c)) for c in range(1, COLORS + 1)) - black
    return black, white


def render_pegs(code: tuple) -> str:
    return "  ".join(f"[{COLOR_STYLE[c][1]}]{PEG}[/]" for c in code)


def get_guess() -> tuple | None:
    while True:
        try:
            raw = console.input("\n[bold cyan]Your guess (4 digits 1-6, e.g. 1234): [/]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye.[/]")
            sys.exit(0)
        if raw.lower() in ("q", "quit", "exit"):
            return None
        raw = raw.replace(" ", "")
        if len(raw) == 4 and all(ch in "123456" for ch in raw):
            return tuple(int(ch) for ch in raw)
        console.print("[red]Need exactly 4 digits, each 1–6. Try again.[/]")


def play():
    console.print()
    color_legend = "  ".join(
        f"[{style}]{i}·{name}[/]" for i, (name, style) in COLOR_STYLE.items()
    )
    console.print(Panel(
        f"I've picked a secret 4-peg code — can you crack it?\n\n"
        f"{color_legend}\n\n"
        f"[dim]After each guess: ● = right color & position  ○ = right color, wrong position[/]",
        title="[bold yellow]  MASTERMIND  [/]",
        border_style="yellow",
        padding=(1, 2),
    ))

    secret = tuple(random.randint(1, COLORS) for _ in range(PEGS))

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("#",        style="dim",  width=6)
    table.add_column("Guess",    no_wrap=True, width=22)
    table.add_column("Feedback", no_wrap=True, width=12)

    for g_num in range(1, MAX_GUESSES + 1):
        remaining = MAX_GUESSES - g_num + 1
        bar_color = "green" if remaining > 7 else "yellow" if remaining > 3 else "red"
        console.print(f"\n[{bar_color}]Guess {g_num}/{MAX_GUESSES}[/]  [dim]{remaining} remaining[/]")

        guess = get_guess()
        if guess is None:
            console.print(f"\n[dim]The code was: {render_pegs(secret)}  ({' '.join(map(str, secret))})[/]\n")
            return

        black, white = score(guess, secret)
        feedback = f"[bold]● {black}[/]  [dim]○ {white}[/]"
        table.add_row(f"{g_num:2d}/12", render_pegs(guess), feedback)
        console.print(table)

        if black == PEGS:
            console.print(f"\n[bold green]You cracked it in {g_num} guess{'es' if g_num != 1 else ''}! ✓[/]\n")
            return

    console.print(f"\n[bold red]Out of guesses! The code was:[/]  {render_pegs(secret)}  [dim]({' '.join(map(str, secret))})[/]\n")


if __name__ == "__main__":
    play()
