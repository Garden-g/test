#!/usr/bin/env python3
"""Validate Alibaba.com-style product titles for mechanical issues.

This script is intentionally conservative. It does not decide whether a title is
commercially good; it only catches repeatable issues such as overlong titles,
over-repeated words, obvious banned phrases, and unsupported symbols.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_BANNED_PHRASES = (
    "amazon",
    "aliexpress",
    "temu",
    "best",
    "top",
    "no.1",
    "no 1",
    "perfect",
    "guaranteed",
    "original",
    "buy now",
)


@dataclass
class TitleIssue:
    """A single validation issue found in one generated title.

    Attributes:
        severity: Either "error" or "warning". Errors should be fixed before
            delivery; warnings require human review.
        code: A short machine-readable issue code.
        message: A human-readable explanation of what is wrong and why it
            matters for international-station title quality.
    """

    severity: str
    code: str
    message: str


@dataclass
class TitleCheckResult:
    """Validation result for one title.

    Attributes:
        index: One-based position of the title in the input file.
        title: The original title text.
        char_count: Number of Unicode characters in the title.
        repeated_words: Words that appear more than the allowed limit.
        issues: Detailed issues found for this title.
    """

    index: int
    title: str
    char_count: int
    repeated_words: dict[str, int]
    issues: list[TitleIssue]


def read_titles(input_path: Path, title_column: str) -> list[str]:
    """Read titles from a text, CSV, TSV, or JSON file.

    Args:
        input_path: Path to the file that contains generated titles.
        title_column: Column/key name to use when reading structured files.

    Returns:
        A list of non-empty title strings in their original order.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If the file format is unsupported or a structured file does
            not contain the requested title column/key.
        json.JSONDecodeError: If a JSON file is malformed.
    """

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    suffix = input_path.suffix.lower()
    if suffix in {".txt", ""}:
        return [line.strip() for line in input_path.read_text().splitlines() if line.strip()]

    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with input_path.open(newline="") as file_obj:
            reader = csv.DictReader(file_obj, delimiter=delimiter)
            if not reader.fieldnames or title_column not in reader.fieldnames:
                raise ValueError(f"Column '{title_column}' not found in {input_path}")
            return [str(row.get(title_column, "")).strip() for row in reader if row.get(title_column)]

    if suffix == ".json":
        data = json.loads(input_path.read_text())
        if isinstance(data, list) and all(isinstance(item, str) for item in data):
            return [item.strip() for item in data if item.strip()]
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            missing = [i + 1 for i, item in enumerate(data) if title_column not in item]
            if missing:
                raise ValueError(f"Key '{title_column}' missing in JSON rows: {missing[:10]}")
            return [str(item[title_column]).strip() for item in data if str(item[title_column]).strip()]
        raise ValueError("JSON input must be a list of strings or a list of objects.")

    raise ValueError(f"Unsupported input format: {input_path.suffix}")


def normalize_words(title: str) -> list[str]:
    """Convert a title into lowercase words for repeat checking.

    Args:
        title: The product title to split into words.

    Returns:
        Lowercase alphanumeric words. Punctuation is ignored so that
        "water-proof" and "water proof" are both counted as words.
    """

    return re.findall(r"[A-Za-z0-9]+", title.lower())


def find_repeated_words(words: Sequence[str], max_repeat: int) -> dict[str, int]:
    """Find words that exceed the allowed repetition limit.

    Args:
        words: Normalized title words.
        max_repeat: Maximum allowed count for one word.

    Returns:
        A dictionary mapping repeated word to its count.
    """

    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    return {word: count for word, count in counts.items() if count > max_repeat}


def find_banned_phrases(title: str, banned_phrases: Iterable[str]) -> list[str]:
    """Find banned phrases in a title using case-insensitive matching.

    Args:
        title: The title text to inspect.
        banned_phrases: Phrases that should not appear in the title.

    Returns:
        Banned phrases that were found. The returned values use the configured
        phrase text so the user can edit the banned list predictably.
    """

    lowered = title.lower()
    found: list[str] = []
    for phrase in banned_phrases:
        # Word boundaries prevent short bans such as "top" from matching
        # legitimate words such as "desktop" or "tabletop".
        pattern = rf"(?<![A-Za-z0-9]){re.escape(phrase.lower())}(?![A-Za-z0-9])"
        if re.search(pattern, lowered):
            found.append(phrase)
    return found


def has_unsupported_symbols(title: str) -> bool:
    """Check whether a title contains symbols that usually break upload quality.

    Args:
        title: The title text to inspect.

    Returns:
        True when the title contains symbols outside the conservative set of
        letters, numbers, spaces, hyphens, slashes, ampersands, commas, dots,
        parentheses, quotation marks, plus signs, and multiplication markers.
    """

    return re.search(r"[^A-Za-z0-9\s\-\/&,.'\"()+xX*]", title) is not None


def check_title(
    index: int,
    title: str,
    max_chars: int,
    max_repeat: int,
    banned_phrases: Sequence[str],
) -> TitleCheckResult:
    """Validate one title and return all mechanical issues.

    Args:
        index: One-based input position for reporting.
        title: Product title to validate.
        max_chars: Maximum allowed character count.
        max_repeat: Maximum allowed repeated word count.
        banned_phrases: Phrases that should not appear in titles.

    Returns:
        A TitleCheckResult containing character count, repeated words, and
        issue details. The function never mutates the title.
    """

    issues: list[TitleIssue] = []
    char_count = len(title)

    if char_count > max_chars:
        issues.append(
            TitleIssue(
                severity="error",
                code="too_long",
                message=f"Title has {char_count} characters, above the {max_chars} character limit.",
            )
        )

    words = normalize_words(title)
    repeated_words = find_repeated_words(words, max_repeat)
    if repeated_words:
        detail = ", ".join(f"{word}={count}" for word, count in sorted(repeated_words.items()))
        issues.append(
            TitleIssue(
                severity="error",
                code="word_repeated_too_often",
                message=f"Some words appear more than {max_repeat} times: {detail}.",
            )
        )

    banned_found = find_banned_phrases(title, banned_phrases)
    if banned_found:
        issues.append(
            TitleIssue(
                severity="warning",
                code="banned_phrase_found",
                message="Review or remove banned/risky phrases: " + ", ".join(banned_found),
            )
        )

    if has_unsupported_symbols(title):
        issues.append(
            TitleIssue(
                severity="warning",
                code="unsupported_symbol",
                message="Title contains symbols outside the conservative upload-safe character set.",
            )
        )

    if not words:
        issues.append(
            TitleIssue(
                severity="error",
                code="empty_title",
                message="Title is empty or has no searchable words.",
            )
        )

    return TitleCheckResult(
        index=index,
        title=title,
        char_count=char_count,
        repeated_words=repeated_words,
        issues=issues,
    )


def result_to_dict(result: TitleCheckResult) -> dict[str, object]:
    """Convert one validation result into JSON-serializable data.

    Args:
        result: Validation result object returned by check_title().

    Returns:
        A plain dictionary suitable for json.dumps().
    """

    return {
        "index": result.index,
        "title": result.title,
        "char_count": result.char_count,
        "repeated_words": result.repeated_words,
        "issues": [issue.__dict__ for issue in result.issues],
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments for title validation.

    Args:
        argv: Command-line arguments excluding the executable name.

    Returns:
        Parsed argparse Namespace.
    """

    parser = argparse.ArgumentParser(description="Validate generated Alibaba product titles.")
    parser.add_argument("--input", required=True, help="Input .txt, .csv, .tsv, or .json file.")
    parser.add_argument("--title-column", default="title", help="CSV/TSV/JSON object field containing titles.")
    parser.add_argument("--max-chars", type=int, default=128, help="Maximum allowed title characters.")
    parser.add_argument("--max-repeat", type=int, default=3, help="Maximum times one word may appear.")
    parser.add_argument(
        "--banned",
        action="append",
        default=[],
        help="Additional banned phrase. Repeat this flag for multiple phrases.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the title validator and print a JSON report.

    Args:
        argv: Optional argument list for testing. When omitted, sys.argv is used.

    Returns:
        Process exit code. Returns 1 when any error-level issue is found so the
        script can be used in automated checks.

    Raises:
        FileNotFoundError: If the input path does not exist.
        ValueError: If the input file cannot be interpreted.
        json.JSONDecodeError: If JSON input is malformed.
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    titles = read_titles(Path(args.input), args.title_column)
    banned_phrases = tuple(DEFAULT_BANNED_PHRASES) + tuple(args.banned)

    results = [
        check_title(
            index=index,
            title=title,
            max_chars=args.max_chars,
            max_repeat=args.max_repeat,
            banned_phrases=banned_phrases,
        )
        for index, title in enumerate(titles, start=1)
    ]

    error_count = sum(
        1 for result in results for issue in result.issues if issue.severity == "error"
    )
    warning_count = sum(
        1 for result in results for issue in result.issues if issue.severity == "warning"
    )

    report = {
        "title_count": len(results),
        "error_count": error_count,
        "warning_count": warning_count,
        "results": [result_to_dict(result) for result in results],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if error_count else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
