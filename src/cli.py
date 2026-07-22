import argparse
import glob
import os
import threading
import time
from collections import defaultdict
from queue import Empty, Full, Queue
from typing import Any

import dotenv

from database.database import SELECT_COMPANIES_SLUG_URL, database
from producer import run_producers
from services._models import DISABLED_ATS, ATSType
from signals import setup_signal_handlers
from workers import Worker

dotenv.load_dotenv()


def _dump_recent(args: argparse.Namespace):
    with database.connect() as connection:
        database.dump_jobs_recent(connection)


def _dump_ats(args: argparse.Namespace):
    with database.connect() as connection:
        database.dump_jobs_by_ats(connection, args.ats or None)


def _dump_company(args: argparse.Namespace):
    with database.connect() as connection:
        database.dump_jobs_by_company(connection, args.companies or None)


def _dump_companies(args: argparse.Namespace):
    with database.connect() as connection:
        database.dump_all_companies(connection)
    print("Dumped companies table to data/parquet/companies.parquet")


def _dump_ats_table(args: argparse.Namespace):
    with database.connect() as connection:
        database.dump_ats_table(connection)
    print("Dumped ats table to data/parquet/ats.parquet")


def _dump_watchlist_table(args: argparse.Namespace):
    with database.connect() as connection:
        database.dump_watch_table(connection)
    print("Dumped watchlists table to data/parquet/watchlists.parquet")


def _dump_watchlist(args: argparse.Namespace):
    with database.connect() as connection:
        if args.watchlist:
            count = database.dump_watchlist_jobs(connection, args.watchlist)
            print(f"Dumped {count} jobs for watchlist '{args.watchlist}'")
        else:
            total = 0
            for source in database.read_watchlist_sources(connection):
                count = database.dump_watchlist_jobs(connection, source)
                total += count
                print(f"  {source}: {count} jobs")
            print(f"Dumped {total} jobs total across all watchlists")


def _get_all_companies() -> dict[ATSType, list[dict[str, str]]]:
    with database.connect() as connection:
        companies = database.read_companies_ats(connection)
    return {k: v for k, v in companies.items() if k not in DISABLED_ATS}


def _run_collect_pipeline(
    companies_by_ats: dict[ATSType, list[dict[str, str]]],
) -> tuple[str, int, int]:
    start = time.monotonic()
    ingest_queue: Queue[Any] = Queue(maxsize=100)
    shutdown_event = threading.Event()
    setup_signal_handlers(shutdown_event, ingest_queue)

    worker = Worker(ingest_queue)
    worker.start()

    run_producers(ingest_queue, companies_by_ats, shutdown_event)

    while True:
        try:
            ingest_queue.put_nowait(None)
            break
        except Full:
            try:
                ingest_queue.get_nowait()
            except Empty:
                ingest_queue.put(None)
                break

    worker.join()

    with database.connect() as connection:
        database.dump_jobs_recent(connection)

    outcome = "cancelled" if shutdown_event.is_set() else "success"
    return outcome, worker.total_written, int((time.monotonic() - start) * 1000)


def _collect_ats(args: argparse.Namespace):
    valid_ats: list[ATSType] = []
    unknown_ats: list[str] = []

    for ats in args.ats:
        try:
            valid_ats.append(ATSType(ats))
        except ValueError:
            unknown_ats.append(ats)

    if unknown_ats:
        valid_types = ", ".join(m.value for m in ATSType)
        print(f"Unknown ATS type(s): {', '.join(unknown_ats)}. Valid types: {valid_types}")
        if not valid_ats:
            return

    all_companies = _get_all_companies()
    companies_by_ats: dict[ATSType, list[dict[str, str]]] = {}
    for ats_type in valid_ats:
        if ats_type not in all_companies:
            print(f"No companies found for ATS type '{ats_type.value}'")
            continue
        companies = [c for c in all_companies[ats_type] if c["slug"] not in args.skip]
        if companies:
            companies_by_ats[ats_type] = companies

    if not companies_by_ats:
        print("No companies to fetch — all requested ATS types had no companies")
        return

    total = sum(len(c) for c in companies_by_ats.values())
    if args.skip:
        skipped = 0
        for ats_type in valid_ats:
            if ats_type in all_companies:
                skipped += sum(1 for c in all_companies[ats_type] if c["slug"] in args.skip)
        if skipped:
            print(f"Skipping {skipped} companies ({', '.join(args.skip)})")
    ats_list = ", ".join(ats.value for ats in companies_by_ats)
    print(f"Fetching jobs for {total} companies on {ats_list}")

    outcome, written, duration = _run_collect_pipeline(companies_by_ats)
    print(f"Fetch {outcome} — {written} jobs persisted in {duration}ms")


def _collect_company(args: argparse.Namespace):
    companies_by_ats: dict[ATSType, list[dict[str, str]]] = defaultdict(list)
    found = []
    not_found = []

    all_companies = _get_all_companies()
    all_flat = [c for companies in all_companies.values() for c in companies]

    for name in args.companies:
        matched = [c for c in all_flat if c["slug"] == name or c["name"] == name]
        if matched:
            for c in matched:
                for ats_type, companies in all_companies.items():
                    if c in companies:
                        companies_by_ats[ats_type].append(c)
                        break
            found.append(name)
        else:
            not_found.append(name)

    if not_found:
        print(f"Companies not found: {', '.join(not_found)}")
    if not companies_by_ats:
        print("No companies to fetch")
        return

    total = sum(len(c) for c in companies_by_ats.values())
    ats_list = ", ".join(ats.value for ats in companies_by_ats)
    print(f"Fetching jobs for {total} companies on {ats_list}")

    outcome, written, duration = _run_collect_pipeline(companies_by_ats)
    print(f"Fetch {outcome} — {written} jobs persisted in {duration}ms")


def _collect_all(args: argparse.Namespace):
    all_companies = _get_all_companies()

    if args.skip:
        skipped_ats = []
        for skip in args.skip:
            try:
                skip_ats = ATSType(skip)
                if skip_ats in all_companies:
                    del all_companies[skip_ats]
                    skipped_ats.append(skip)
            except ValueError:
                print(f"Unknown ATS type '{skip}' — ignoring")
        if skipped_ats:
            print(f"Skipping {len(skipped_ats)} ATS types: {', '.join(skipped_ats)}")

    total_companies = sum(len(v) for v in all_companies.values())
    unknown_ats = [
        c["ats"]
        for companies in all_companies.values()
        for c in companies
        if c["ats"] not in ATSType._value2member_map_
    ]
    unknown_ats = list(dict.fromkeys(unknown_ats))

    print(f"Fetching jobs for {total_companies} companies across {len(all_companies)} ATS types")
    if unknown_ats:
        print(f"Skipping {len(unknown_ats)} unknown ATS types: {', '.join(unknown_ats)}")

    outcome, written, duration = _run_collect_pipeline(all_companies)
    print(f"Fetch {outcome} — {written} jobs persisted in {duration}ms")


def _watchlist_load(args: argparse.Namespace):
    with database.connect() as connection:
        database.load_watchlists_dir(connection, args.directory)
    print(f"Watch list loaded from {args.directory}")


def _watchlist_list(args: argparse.Namespace):
    watchlist_dir = "data/parquet/watchlist"
    parquets = sorted(glob.glob(os.path.join(watchlist_dir, "*.parquet")))
    if not parquets:
        print(f"No watchlist parquets found in {watchlist_dir}/")
        return
    for path in parquets:
        print(os.path.splitext(os.path.basename(path))[0])


def _collect_watchlist(args: argparse.Namespace):
    with database.connect() as connection:
        if args.watchlist:
            entries = database.read_watchlists_by_source(connection, args.watchlist)
            if not entries:
                print(f"No watchlist entries found for source '{args.watchlist}'")
                return
        else:
            entries = database.read_watchlists(connection)

        companies_urls = dict(connection.execute(SELECT_COMPANIES_SLUG_URL).fetchall())

    if not entries:
        print("Watch list is empty — nothing to fetch")
        return

    companies_by_ats: dict[ATSType, list[dict[str, str]]] = defaultdict(list)
    for e in entries:
        try:
            ats_type = ATSType(e["ats"])
        except ValueError:
            continue
        slug = e["company_slug"]
        url = companies_urls.get(slug) or slug
        companies_by_ats[ats_type].append({"name": e["company_name"], "slug": slug, "url": url})

    if args.skip_ats:
        skipped_ats = []
        for skip in args.skip_ats:
            try:
                skip_ats = ATSType(skip)
                if skip_ats in companies_by_ats:
                    del companies_by_ats[skip_ats]
                    skipped_ats.append(skip)
            except ValueError:
                print(f"Unknown ATS type '{skip}' — ignoring")
        if skipped_ats:
            print(f"Skipping {len(skipped_ats)} ATS types: {', '.join(skipped_ats)}")

    total_companies = sum(len(v) for v in companies_by_ats.values())
    unknown = [e["ats"] for e in entries if e["ats"] not in ATSType._value2member_map_]
    unknown_ats = list(dict.fromkeys(unknown))

    label = f"watchlist '{args.watchlist}'" if args.watchlist else "all watched companies"
    print(
        f"Fetching jobs for {total_companies} companies from {label} across {len(companies_by_ats)} ATS types"
    )
    if unknown_ats:
        print(f"Skipping {len(unknown_ats)} unknown ATS types: {', '.join(unknown_ats)}")

    outcome, written, duration = _run_collect_pipeline(companies_by_ats)
    print(f"Fetch {outcome} — {written} jobs persisted in {duration}ms")


def _remove_unwatched(args: argparse.Namespace):
    with database.connect() as connection:
        removed = database.prune_unwatched_companies(connection, dry_run=args.dry_run)
    label = " (dry run)" if args.dry_run else ""
    print(f"Removed {removed} unwatched companies{label}.")


def _database(args: argparse.Namespace):
    with database.connect() as connection:
        database.initialize(connection)
    print("Database created")


def _load_database(args: argparse.Namespace):
    with database.connect() as connection:
        database.load_companies_from_parquet(connection)
        database.build_ats_from_companies(connection)
        database.load_watchlists_dir(connection, "data/parquet/watchlist")
    print("Database loaded")


def _validate_jobs(args: argparse.Namespace):
    with database.connect() as connection:
        passed, failed, total = database.validate_job_urls(
            connection, max_workers=args.workers, dry_run=args.dry_run
        )
    label = " (dry run)" if args.dry_run else ""
    removed = 0 if args.dry_run else failed
    print(
        f"Job URL validation: {passed} valid, {failed} failed, {removed} removed / {total} total{label}."
    )


def _validate_companies(args: argparse.Namespace):
    with database.connect() as connection:
        passed, failed, skipped, total = database.validate_company_urls(
            connection, max_workers=args.workers, dry_run=args.dry_run
        )
    label = " (dry run)" if args.dry_run else ""
    removed = 0 if args.dry_run else failed
    print(
        f"Company URL validation: {passed} valid, {failed} failed, {skipped} skipped, {removed} removed / {total} total{label}."
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openats", description="openats CLI")
    sub = parser.add_subparsers(dest="command")

    dump = sub.add_parser("dump", help="Dump data from the database")
    dump_sub = dump.add_subparsers(dest="dump_command")

    dump_ats = dump_sub.add_parser("ats", help="Dump jobs grouped by ATS type")
    dump_ats.add_argument("ats", nargs="*", help="ATS type(s) to dump (default: all)")
    dump_ats.set_defaults(func=_dump_ats)

    dump_company = dump_sub.add_parser("company", help="Dump jobs grouped by company")
    dump_company.add_argument("companies", nargs="*", help="Company name(s) to dump (default: all)")
    dump_company.set_defaults(func=_dump_company)

    dump_companies = dump_sub.add_parser(
        "companies-table", help="Dump the companies table to parquet"
    )
    dump_companies.set_defaults(func=_dump_companies)

    dump_ats_table = dump_sub.add_parser("ats-table", help="Dump the ats table to parquet")
    dump_ats_table.set_defaults(func=_dump_ats_table)

    dump_watchlist_table = dump_sub.add_parser(
        "watchlist-table", help="Dump the watchlists table to parquet"
    )
    dump_watchlist_table.set_defaults(func=_dump_watchlist_table)

    dump_watchlist = dump_sub.add_parser("watchlist", help="Dump watchlist jobs")
    dump_watchlist.add_argument("watchlist", nargs="?", help="Watchlist source name (default: all)")
    dump_watchlist.set_defaults(func=_dump_watchlist)

    dump_recent = dump_sub.add_parser("recent", help="Dump jobs posted in the last 24 hours")
    recent_sub = dump_recent.add_subparsers(dest="recent_command")
    dump_recent_jobs = recent_sub.add_parser("jobs", help="Dump the jobs_recent table")
    dump_recent_jobs.set_defaults(func=_dump_recent)

    collect = sub.add_parser("collect", help="Collect jobs from companies")
    collect_sub = collect.add_subparsers(dest="collect_command")
    collect.add_argument("--skip", nargs="+", default=[], help="ATS types to skip")

    collect_company = collect_sub.add_parser("company", help="Collect jobs for specific companies")
    collect_company.add_argument("companies", nargs="+", help="Company name(s) or slug(s)")
    collect_company.set_defaults(func=_collect_company)

    collect_ats = collect_sub.add_parser(
        "ats", help="Collect jobs for companies using specific ATS types"
    )
    collect_ats.add_argument("ats", nargs="+", help="ATS type(s)")
    collect_ats.add_argument("--skip", nargs="+", default=[], help="Company slugs to skip")
    collect_ats.set_defaults(func=_collect_ats)

    collect_watchlist = collect_sub.add_parser(
        "watchlist", help="Collect jobs for companies in a watchlist"
    )
    collect_watchlist.add_argument(
        "watchlist", nargs="?", help="Watchlist source name (default: all)"
    )
    collect_watchlist.add_argument("--skip-ats", nargs="+", default=[], help="ATS types to skip")
    collect_watchlist.set_defaults(func=_collect_watchlist)

    collect.set_defaults(func=_collect_all)

    watchlist = sub.add_parser("watchlist", help="Manage watch list")
    watchlist_sub = watchlist.add_subparsers(dest="watchlist_command")

    watchlist_load = watchlist_sub.add_parser(
        "load", help="Load watch list from parquet files in a directory"
    )
    watchlist_load.add_argument(
        "directory", help="Path to directory with parquet files containing a 'name' column"
    )
    watchlist_load.set_defaults(func=_watchlist_load)

    watchlist_list = watchlist_sub.add_parser("list", help="List available watchlist titles")
    watchlist_list.set_defaults(func=_watchlist_list)

    remove = sub.add_parser("remove", help="Remove company data")
    remove_sub = remove.add_subparsers(dest="remove_command")

    remove_unwatched = remove_sub.add_parser(
        "unwatched", help="Remove companies not in any watchlist"
    )
    remove_unwatched.add_argument(
        "--dry-run", action="store_true", help="Count how many would be removed without deleting"
    )
    remove_unwatched.set_defaults(func=_remove_unwatched)

    validate = sub.add_parser("validate", help="Validate data quality")
    validate_sub = validate.add_subparsers(dest="validate_command")

    validate_jobs = validate_sub.add_parser("jobs", help="Check job URLs exist and titles match")
    validate_jobs.add_argument(
        "--workers", type=int, default=20, help="Concurrent workers (default: 20)"
    )
    validate_jobs.add_argument(
        "--dry-run", action="store_true", help="Print findings without modifying DB"
    )
    validate_jobs.set_defaults(func=_validate_jobs)

    validate_companies = validate_sub.add_parser(
        "companies", help="Check company URLs exist and names match"
    )
    validate_companies.add_argument(
        "--workers", type=int, default=20, help="Concurrent workers (default: 20)"
    )
    validate_companies.add_argument(
        "--dry-run", action="store_true", help="Print findings without modifying DB"
    )
    validate_companies.set_defaults(func=_validate_companies)

    database_cmd = sub.add_parser("database", help="Create or reinitialize the database")
    database_cmd.set_defaults(func=_database)

    load = sub.add_parser("load", help="Load data into the database")
    load_sub = load.add_subparsers(dest="load_command")

    load_database = load_sub.add_parser(
        "database", help="Load seed data from parquet into the database"
    )
    load_database.set_defaults(func=_load_database)

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        from app import main as pipeline_main

        pipeline_main()
    elif args.command == "dump" and args.dump_command is None:
        parser.parse_args(["dump", "--help"])
    elif (
        args.command == "dump"
        and args.dump_command == "recent"
        and getattr(args, "recent_command", None) is None
    ):
        parser.parse_args(["dump", "recent", "--help"])
    elif args.command == "collect" and args.collect_command is None:
        if not args.skip:
            from app import main as pipeline_main

            pipeline_main()
        else:
            _collect_all(args)
    elif args.command == "watchlist" and args.watchlist_command is None:
        parser.parse_args(["watchlist", "--help"])
    elif args.command == "remove" and args.remove_command is None:
        parser.parse_args(["remove", "--help"])
    elif args.command == "validate" and args.validate_command is None:
        parser.parse_args(["validate", "--help"])
    elif args.command == "database":
        args.func(args)
    elif args.command == "load" and args.load_command is None:
        parser.parse_args(["load", "--help"])
    else:
        args.func(args)


if __name__ == "__main__":
    main()
