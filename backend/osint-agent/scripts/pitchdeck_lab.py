#!/usr/bin/env python3
"""Pitch deck experiments: split decks, tune on train, run the model, evaluate on held-out decks.

Everything stays in data/pitchdeck/lab, which Git ignores.

    pitchdeck_lab.py split --decks DIR
    pitchdeck_lab.py run --decks DIR --split train --model qwen2.5vl:7b --mode text+image
    pitchdeck_lab.py flags --decks DIR --split test --model qwen2.5vl:7b --mode text+image
    pitchdeck_lab.py eval --model qwen2.5vl:7b --mode text+image --split test
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import time
import unicodedata
from pathlib import Path

from osint_agent.pitchdeck.evaluation import GoldFact, Score, score_deck
from osint_agent.pitchdeck.extract import MIN_TEXT_LAYER, extract_slide, should_analyze, verify_fact
from osint_agent.pitchdeck.ingest import DeckReadError, read_deck
from osint_agent.pitchdeck.llm import LocalLLMError, OllamaClient
from osint_agent.pitchdeck.models import DeckFact, Slide, Verdict
from osint_agent.pitchdeck.red_flags import detect_red_flags

LAB = Path("data/pitchdeck/lab")
OLLAMA = "http://127.0.0.1:11434"
TEST_SHARE = 0.25
SEED = 20261030


GOLD_ONLY = False


def run_dir(model: str, mode: str) -> Path:
    suffix = "__goldonly" if GOLD_ONLY else ""
    return LAB / "runs" / f"{model.replace(':', '_').replace('/', '_')}__{mode.replace('+', '_')}{suffix}"


def load_split() -> dict:
    return json.loads((LAB / "split.json").read_text(encoding="utf-8"))


def cmd_split(args: argparse.Namespace) -> None:
    """Split unique decks by file hash. Decks already seen during prompt work stay in train."""
    # macOS may store Cyrillic names decomposed, so compare them in one Unicode form
    seen_names = {unicodedata.normalize("NFC", n) for n in args.seen or []}
    decks: dict[str, str] = {}
    duplicates = []
    for path in sorted(Path(args.decks).iterdir()):
        if path.suffix.lower() not in {".pdf", ".pptx"}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        if digest in decks:
            duplicates.append(path.name)
        else:
            decks[digest] = path.name
    forced = [h for h, n in decks.items() if unicodedata.normalize("NFC", n) in seen_names]
    free = sorted(h for h in decks if h not in forced)
    random.Random(SEED).shuffle(free)
    test_size = round(len(decks) * TEST_SHARE)
    test = free[:test_size]
    train = free[test_size:] + forced
    LAB.mkdir(parents=True, exist_ok=True)
    payload = {
        "seed": SEED,
        "decks": decks,
        "train": sorted(train),
        "test": sorted(test),
        "duplicates": duplicates,
        "forced_train": forced,
    }
    (LAB / "split.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"decks {len(decks)}, train {len(train)}, test {len(test)}, duplicates {duplicates}")


async def _run(args: argparse.Namespace) -> None:
    split = load_split()
    hashes = split[args.split] if args.split in {"train", "test"} else list(split["decks"])
    if GOLD_ONLY:
        hashes = [h for h in hashes if _load_gold(h)]
    if args.limit:
        hashes = hashes[: args.limit]
    out = run_dir(args.model, args.mode)
    out.mkdir(parents=True, exist_ok=True)
    client = OllamaClient(OLLAMA, args.model, timeout=600)
    try:
        for number, digest in enumerate(hashes, 1):
            target = out / f"{digest}.json"
            if target.exists():
                continue
            name = split["decks"][digest]
            started = time.time()
            try:
                raws = read_deck(Path(args.decks) / name)
            except DeckReadError as exc:
                print(f"[{number}/{len(hashes)}] {digest} unreadable: {exc}", flush=True)
                continue
            slides = []
            only = set(_load_gold(digest)["slides"]) if GOLD_ONLY else None
            for raw in raws:
                if only is not None and raw.number not in only:
                    continue
                entry = {"slide": raw.number, "chars": len(raw.text), "error": None, "facts": []}
                if should_analyze(raw.text, raw.image_png is not None):
                    try:
                        facts = await extract_slide(client, raw.number, raw.text, raw.image_png, args.mode)
                        for fact in facts:
                            fact.verdict = await verify_fact(client, fact, raw.text, raw.image_png, args.mode)
                        entry["facts"] = [f.model_dump(mode="json") for f in facts]
                    except LocalLLMError as exc:
                        if exc.code == "llm_unavailable":
                            raise
                        entry["error"] = exc.code
                slides.append(entry)
            target.write_text(json.dumps({"deck": digest, "slides": slides}, ensure_ascii=False), encoding="utf-8")
            count = sum(len(s["facts"]) for s in slides)
            print(f"[{number}/{len(hashes)}] {digest} slides {len(slides)} facts {count} {time.time() - started:.0f}s", flush=True)
    finally:
        await client.aclose()


def _load_run(model: str, mode: str, digest: str) -> dict | None:
    path = run_dir(model, mode) / f"{digest}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _load_gold(digest: str) -> dict | None:
    path = LAB / "gold" / f"{digest}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _predictions(run: dict, gold: dict, threshold_fn=None) -> list[dict]:
    annotated = set(gold["slides"])
    preds = []
    for slide in run["slides"]:
        if slide["slide"] not in annotated:
            continue
        for fact in slide["facts"]:
            if threshold_fn is None or threshold_fn(fact, slide):
                preds.append(fact)
    return preds


def cmd_eval(args: argparse.Namespace) -> None:
    split = load_split()
    totals = {"strict_all": Score(), "relaxed_all": Score(), "strict_trusted": Score(), "relaxed_trusted": Score()}
    per_deck = {}
    for digest in split[args.split]:
        run, gold = _load_run(args.model, args.mode, digest), _load_gold(digest)
        if not run or not gold:
            continue
        golds = [GoldFact.from_dict(g) for g in gold["facts"]]

        def trusted(fact: dict, slide: dict) -> bool:
            if slide["chars"] >= MIN_TEXT_LAYER:
                return fact["value_in_text"]
            return fact["verdict"] == Verdict.correct.value

        every = _predictions(run, gold)
        kept = _predictions(run, gold, trusted)
        row = {}
        for label, preds, strict in (
            ("strict_all", every, True), ("relaxed_all", every, False),
            ("strict_trusted", kept, True), ("relaxed_trusted", kept, False),
        ):
            score, _ = score_deck(golds, preds, strict=strict)
            totals[label].add(score)
            row[label] = score.as_dict()
        per_deck[split["decks"][digest]] = {"gold_facts": len(golds), **row}
    report = {
        "split": args.split, "model": args.model, "mode": args.mode,
        "decks": len(per_deck),
        "gold_facts": sum(d["gold_facts"] for d in per_deck.values()),
        "total": {k: v.as_dict() for k, v in totals.items()},
        "per_deck": per_deck,
    }
    target = LAB / "reports" / f"{args.split}__{args.model.replace(':', '_')}__{args.mode.replace('+', '_')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("split", "model", "mode", "decks", "gold_facts", "total")},
                     ensure_ascii=False, indent=1))


def cmd_flags(args: argparse.Namespace) -> None:
    """Print the flags each deck gets, so a person can judge them against the slides."""
    split = load_split()
    report = {}
    for digest in split[args.split]:
        run = _load_run(args.model, args.mode, digest)
        if not run:
            continue
        name = split["decks"][digest]
        raws = {r.number: r.text for r in read_deck(Path(args.decks) / name)}
        facts = []
        for slide in run["slides"]:
            for raw_fact in slide["facts"]:
                fact = DeckFact.model_validate(raw_fact)
                text = raws.get(fact.slide, "")
                if len(text.strip()) >= MIN_TEXT_LAYER:
                    fact.needs_review = not fact.value_in_text
                else:
                    fact.needs_review = fact.verdict != Verdict.correct
                facts.append(fact)
        slides = [Slide(number=n, text=t) for n, t in raws.items()]
        report[name] = [f.model_dump(mode="json") for f in detect_red_flags(facts, slides)]
    target = LAB / "reports" / f"flags_{args.split}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, flags in report.items():
        print(f"== {name}")
        for flag in flags:
            print(f"  {flag['severity']:6} {flag['rule']:24} {flag['slides']} {flag['detail'][:150]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    split = sub.add_parser("split")
    split.add_argument("--decks", required=True)
    split.add_argument("--seen", nargs="*", help="deck file names already viewed; they stay in train")
    run = sub.add_parser("run")
    run.add_argument("--decks", required=True)
    run.add_argument("--split", default="train", choices=["train", "test", "all"])
    run.add_argument("--limit", type=int)
    flags = sub.add_parser("flags")
    flags.add_argument("--decks", required=True)
    flags.add_argument("--split", default="test", choices=["train", "test"])
    evaluate = sub.add_parser("eval")
    evaluate.add_argument("--split", default="test", choices=["train", "test"])
    for item in (run, flags, evaluate):
        item.add_argument("--gold-only", action="store_true", help="use only annotated slides")
        item.add_argument("--model", default="qwen2.5vl:7b")
        item.add_argument("--mode", default="text+image", choices=["text", "image", "text+image"])
    args = parser.parse_args()
    global GOLD_ONLY
    GOLD_ONLY = getattr(args, "gold_only", False)
    if args.command == "split":
        cmd_split(args)
    elif args.command == "run":
        asyncio.run(_run(args))
    elif args.command == "flags":
        cmd_flags(args)
    else:
        cmd_eval(args)


if __name__ == "__main__":
    main()
