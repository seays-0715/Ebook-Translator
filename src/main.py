"""CLI entry point for Ebook Translator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.core.chapter_ops import (
    merge_adjacent,
    remove_chapter,
    rename_chapter,
    split_chapter,
)
from src.core.pipeline import (
    convert_file,
    create_translation_job,
    export_job_epub,
    parse_to_book,
    run_translation_job,
)
from src.core.storage import Storage
from src.epub.generator import generate_epub
from src.glossary.builder import build_candidates_from_alignment
from src.glossary.store import GlossaryStore
from src.models.job import JobConfig
from src.queue.batch_queue import BatchQueue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ebook-translator",
        description="Ebook processor + Local AI translator",
    )
    parser.add_argument(
        "--gui", action="store_true", help="Launch GUI (CustomTkinter)"
    )
    sub = parser.add_subparsers(dest="cmd", required=False)

    p_convert = sub.add_parser("convert", help="Normalize input to clean EPUB")
    p_convert.add_argument("input", type=Path)
    p_convert.add_argument("-o", "--output", type=Path, required=True)

    p_preview = sub.add_parser(
        "preview", help="Show chapter detection result (JSON)"
    )
    p_preview.add_argument("input", type=Path)

    p_translate = sub.add_parser("translate", help="Create and run a translation job")
    p_translate.add_argument("input", type=Path)
    p_translate.add_argument("-o", "--output", type=Path, required=True)
    p_translate.add_argument("--target", default="zh-TW")
    p_translate.add_argument("--source", default="auto")
    p_translate.add_argument("--endpoint", default="http://localhost:8000/v1")
    p_translate.add_argument("--model", default="local")
    p_translate.add_argument("--work-dir", type=Path, default=Path("./jobs"))
    p_translate.add_argument("--db", type=Path, default=Path("./ebook_translator.db"))
    p_translate.add_argument("--glossary", type=Path, default=None)
    p_translate.add_argument(
        "--force-export",
        action="store_true",
        help="Export even if Level 2/3 validation fails",
    )

    p_export = sub.add_parser("export", help="Export a finished job to EPUB")
    p_export.add_argument("job_id")
    p_export.add_argument("-o", "--output", type=Path, required=True)
    p_export.add_argument("--db", type=Path, default=Path("./ebook_translator.db"))
    p_export.add_argument("--force", action="store_true")

    p_list = sub.add_parser("list-jobs", help="List jobs")
    p_list.add_argument("--db", type=Path, default=Path("./ebook_translator.db"))

    p_retry = sub.add_parser("retry-failed", help="Retry failed chunks of a job")
    p_retry.add_argument("job_id")
    p_retry.add_argument("--db", type=Path, default=Path("./ebook_translator.db"))
    p_retry.add_argument("--chunk", action="append", dest="chunks", default=None)

    # Glossary
    p_gloss = sub.add_parser("glossary", help="Glossary tools")
    g_sub = p_gloss.add_subparsers(dest="gloss_cmd", required=True)
    g_create = g_sub.add_parser("create", help="Create empty glossary")
    g_create.add_argument("name")
    g_create.add_argument("--root", type=Path, default=Path("./glossaries"))
    g_add = g_sub.add_parser("add", help="Add entry")
    g_add.add_argument("glossary_id")
    g_add.add_argument("source")
    g_add.add_argument("target")
    g_add.add_argument("--root", type=Path, default=Path("./glossaries"))
    g_add.add_argument("--confirm", action="store_true")
    g_build = g_sub.add_parser(
        "build", help="Build candidates from source+official translation"
    )
    g_build.add_argument("source", type=Path)
    g_build.add_argument("official", type=Path)
    g_build.add_argument("--root", type=Path, default=Path("./glossaries"))
    g_build.add_argument("--name", default="auto")
    g_list = g_sub.add_parser("list", help="List glossaries")
    g_list.add_argument("--root", type=Path, default=Path("./glossaries"))

    # Queue
    p_queue = sub.add_parser("queue", help="Run a batch queue (sequential books)")
    p_queue.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input files",
    )
    p_queue.add_argument("-o", "--output-dir", type=Path, required=True)
    p_queue.add_argument("--target", default="zh-TW")
    p_queue.add_argument("--endpoint", default="http://localhost:8000/v1")
    p_queue.add_argument("--model", default="local")
    p_queue.add_argument("--db", type=Path, default=Path("./ebook_translator.db"))
    p_queue.add_argument("--work-dir", type=Path, default=Path("./jobs"))

    args = parser.parse_args(argv)

    if args.gui or args.cmd is None:
        from src.ui.app import launch
        launch()
        return 0

    if args.cmd == "convert":
        out = convert_file(args.input, args.output)
        print(f"Wrote {out}")
        return 0

    if args.cmd == "preview":
        result = parse_to_book(args.input)
        data = {
            "title": result.book.metadata.title,
            "author": result.book.metadata.author,
            "language": result.book.metadata.language,
            "chapters": result.chapter_suggestions
            or [
                {
                    "id": ch.id,
                    "title": ch.title,
                    "order": ch.order,
                    "block_count": len(ch.blocks),
                }
                for ch in result.book.chapters
            ],
            "warnings": result.warnings,
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "translate":
        storage = Storage(args.db)
        config = JobConfig(
            source_language=args.source,
            target_language=args.target,
            endpoint=args.endpoint,
            model=args.model,
            model_identifier=args.model,
        )
        gloss_entries = None
        gloss_ver = None
        if args.glossary:
            gstore = GlossaryStore(args.glossary.parent)
            if args.glossary.suffix == ".json":
                from src.glossary.models import Glossary

                g = Glossary.model_validate_json(
                    args.glossary.read_text(encoding="utf-8")
                )
            else:
                g = gstore.load(args.glossary.name)
            gloss_entries = g.as_prompt_list()
            gloss_ver = g.version

        work = args.work_dir / args.input.stem
        job = create_translation_job(
            args.input,
            storage,
            config,
            work_dir=work,
            glossary_entries=gloss_entries,
            glossary_version=gloss_ver,
        )
        print(f"Job created: {job.job_id}")

        def progress(event, data):
            if event == "chunk_done":
                print(
                    f"  [{data['completed']}/{data['total']}] "
                    f"{data['chunk_id']} -> {data['status']}"
                )

        # Resume/run uses Job snapshot only (no glossary override)
        status = run_translation_job(
            storage, job.job_id, on_progress=progress
        )
        print(f"Job finished: {status.value}")
        if status.value in ("completed", "completed_with_errors"):
            try:
                out = export_job_epub(
                    storage,
                    job.job_id,
                    args.output,
                    force=args.force_export
                    or status.value == "completed_with_errors",
                )
                print(f"Exported {out}")
            except RuntimeError as e:
                print(f"Export blocked: {e}", file=sys.stderr)
                return 2
        return 0 if status.value == "completed" else 1

    if args.cmd == "export":
        storage = Storage(args.db)
        try:
            out = export_job_epub(
                storage, args.job_id, args.output, force=args.force
            )
            print(f"Exported {out}")
            return 0
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 2

    if args.cmd == "list-jobs":
        storage = Storage(args.db)
        for j in storage.list_jobs():
            print(
                f"{j['job_id'][:8]}  {j['status']:24}  "
                f"{j['completed_chunks']}/{j['total_chunks']}  "
                f"failed={j['failed_chunks']}"
            )
        return 0

    if args.cmd == "retry-failed":
        from src.translation.engine import TranslationEngine

        storage = Storage(args.db)
        job = storage.load_job(args.job_id)
        object.__setattr__(job, "_book_id", args.job_id)
        engine = TranslationEngine(storage, job)
        status = engine.retry_failed_chunks(args.chunks)
        print(f"Retry finished: {status.value}")
        return 0 if status.value == "completed" else 1

    if args.cmd == "glossary":
        return _glossary_cmd(args)

    if args.cmd == "queue":
        return _queue_cmd(args)

    return 1


def _glossary_cmd(args) -> int:
    store = GlossaryStore(args.root)
    if args.gloss_cmd == "create":
        g = store.create(args.name)
        print(g.glossary_id)
        return 0
    if args.gloss_cmd == "add":
        e = store.add_entry(
            args.glossary_id,
            args.source,
            args.target,
            confirmed=args.confirm,
        )
        if args.confirm:
            store.confirm_entry(args.glossary_id, e.id, True)
        print(e.id)
        return 0
    if args.gloss_cmd == "list":
        for gid in store.list_ids():
            g = store.load(gid)
            print(f"{gid[:8]}  {g.name}  v{g.version}  entries={len(g.entries)}")
        return 0
    if args.gloss_cmd == "build":
        src = parse_to_book(args.source)
        tgt = parse_to_book(args.official)
        result = build_candidates_from_alignment(src.book, tgt.book)
        if result.needs_manual_alignment:
            print(f"MANUAL ALIGNMENT NEEDED: {result.message}", file=sys.stderr)
        g = store.create(args.name, entries=result.candidates)
        print(
            json.dumps(
                {
                    "glossary_id": g.glossary_id,
                    "candidates": len(result.candidates),
                    "pairs": len(result.pairs),
                    "needs_manual_alignment": result.needs_manual_alignment,
                    "message": result.message,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return 1


def _queue_cmd(args) -> int:
    storage = Storage(args.db)
    config = JobConfig(
        target_language=args.target,
        endpoint=args.endpoint,
        model=args.model,
        model_identifier=args.model,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    done = threading_event = __import__("threading").Event()

    def progress(event, data):
        if event == "chunk_done":
            print(
                f"  job={data.get('job_id', '')[:8]} "
                f"[{data['completed']}/{data['total']}] {data['status']}"
            )
        elif event == "item_exported":
            print(f"Exported {data.get('output')}")

    q = BatchQueue(
        storage=storage,
        work_root=args.work_dir,
        config=config,
        on_progress=progress,
    )
    for p in args.inputs:
        out = args.output_dir / f"{p.stem}.translated.epub"
        q.add(p, out)

    q.start()
    # Wait for worker
    while q.status.value == "running":
        __import__("time").sleep(0.5)
        w = q._worker
        if w and not w.is_alive():
            break
    print(f"Queue status: {q.status.value}")
    for item in q.items():
        print(f"  {Path(item.source_path).name}: {item.status.value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
