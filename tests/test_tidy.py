#!/usr/bin/env python3
"""rdt-tidy end-to-end tests via a fake rdt shim on PATH."""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIDY = os.path.join(ROOT, "rdt-tidy")
SHIMDIR = os.path.join(ROOT, "tests", "shim")
FIX = os.path.join(ROOT, "tests", "fixtures")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    if not cond:
        print(f"FAIL {name} {extra}")
        raise SystemExit(1)
    PASS += 1
    print(f"ok {name}")


def run(env, *args):
    e = dict(os.environ)
    e.update(env)
    e["PATH"] = SHIMDIR + os.pathsep + e.get("PATH", "")
    return subprocess.run(
        [sys.executable, TIDY, *args],
        capture_output=True, text=True, timeout=30, env=e,
    )


def fixture(name):
    return os.path.join(FIX, name)


with tempfile.TemporaryDirectory() as tmp:
    log = os.path.join(tmp, "argv.log")

    # 1. Compact listing: shape and ratio
    p = run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
            "--compact", "sub", "python")
    check("listing exit0", p.returncode == 0, p.stderr)
    lines = p.stdout.strip().splitlines()
    check("listing 4 lines (header+2+next)", len(lines) == 4, repr(p.stdout))
    check("listing header", lines[0] == "no | score | title | author | id", lines[0])
    check("listing no r/python (sub command)", "r/python" not in lines[1], lines[1])
    check("listing has id", lines[1].endswith("| 1abc11"), lines[1])
    check("listing next", lines[3] == "next t3_1abc22", lines[3])
    raw = open(fixture("listing.json"), encoding="utf-8").read()
    # Header adds a fixed ~35 bytes; 1/4 is the small-fixture bound
    # (live data observes ~1/20, 54KB -> 2.7KB).
    check("listing ratio<=1/4", len(p.stdout) * 4 <= len(raw),
          f"{len(p.stdout)} vs {len(raw)}")

    # 2. Caps: -n 50 -> 10; default -> -n 5
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "search", "x", "-n", "50")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("cap -n 50->10", "10" in argv and "50" not in argv, repr(argv))
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "search", "x")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("default -n 5", "-n" in argv and "5" in argv, repr(argv))
    check("backend --json", "--json" in argv, repr(argv))

    # 3. Feed subs-only cap 5x5
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "feed", "--subs-only", "--max-subs", "20", "-n", "25")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("subs cap", "5" in argv and "20" not in argv and "25" not in argv, repr(argv))

    # 4. Read from raw listing shape
    p = run({"RDT_FIXTURE": fixture("comments_raw.json")},
            "--compact", "read", "1abc11")
    check("read exit0", p.returncode == 0, p.stderr)
    out = p.stdout
    check("read header", out.splitlines()[0].startswith("# 1abc11 r/python"), out.splitlines()[0])
    check("read body full", "uzun govde " * 5 in out and "[...]" not in out, out[:200])
    check("read reply indented", "\n  u/zeynep" in out, out)
    check("read top-level unindented", "\nu/dave" in out and "\nu/erin" in out, out)
    check("read all comments", "u/erin" in out, out)
    check("read +2 more", "+2 more" in out, out)
    check("read no raw keys", "awardings" not in out and "selftext_html" not in out, "")
    raw = open(fixture("comments_raw.json"), encoding="utf-8").read()
    check("read ratio<=1/2", len(out) * 2 <= len(raw), f"{len(out)} vs {len(raw)}")

    # 5. Read from typed detail shape
    p = run({"RDT_FIXTURE": fixture("detail_typed.json")},
            "--compact", "read", "9zz")
    check("typed exit0", p.returncode == 0, p.stderr)
    check("typed header", p.stdout.splitlines()[0].startswith("# 9zz r/go"), p.stdout)
    check("typed reply indented", "\n  u/deli" in p.stdout, p.stdout)
    check("typed top-level unindented", "\nu/veli" in p.stdout, p.stdout)
    check("typed more", "+4 more" in p.stdout, p.stdout)

    # 6. Error passthrough
    p = run({"RDT_FIXTURE": fixture("error.json")},
            "--compact", "search", "x")
    check("error exit1", p.returncode == 1, str(p.returncode))
    check("error line", p.stdout.strip() == "ERR forbidden: Access forbidden: Resource",
          repr(p.stdout))

    # 7. Passthrough is byte-identical
    p = run({"RDT_FIXTURE": fixture("listing.json")}, "sub", "python", "-n", "2")
    check("passthrough identical", p.stdout == open(fixture("listing.json"), encoding="utf-8").read()
          and p.returncode == 0, repr(p.stdout[:100]))

    # 8) sub-info / user / whoami
    p = run({"RDT_FIXTURE": fixture("subinfo.json")}, "--compact", "sub-info", "python")
    check("subinfo 3 lines", len(p.stdout.strip().splitlines()) == 3, repr(p.stdout))
    check("subinfo no html", "banner_img" not in p.stdout and "<p>" not in p.stdout, "")
    p = run({"RDT_FIXTURE": fixture("user.json")}, "--compact", "user", "spez")
    check("user line", p.stdout.strip() == "u/spez post:100 comment:200 age:2005-09-12",
          repr(p.stdout))
    p = run({"RDT_FIXTURE": fixture("whoami.json")}, "--compact", "whoami")
    check("whoami 2 lines", p.stdout.strip().splitlines() == [
        "u/spez post:100 comment:200 age:2005-09-12", "sess read,vote modhash:1"],
        repr(p.stdout))

    # 9. user-comments keeps the full body
    p = run({"RDT_FIXTURE": fixture("ucomments.json")}, "--compact", "user-comments", "u1")
    check("ucomments full", "[...]" not in p.stdout
          and p.stdout.splitlines()[0] == "no | author | score | sub | body | id"
          and p.stdout.splitlines()[1].startswith("1 | u/u1 | +9 | r/python | yor")
          and p.stdout.splitlines()[1].endswith("| k1"), repr(p.stdout))

    # 10. saved mixes post/comment kinds
    p = run({"RDT_FIXTURE": fixture("mixed.json")}, "--compact", "saved")
    ls = p.stdout.strip().splitlines()
    check("mixed header", ls[0] == "kind | no | score | sub | title/body | author | id",
          repr(p.stdout))
    check("mixed P/C", ls[1].startswith("P | 1 ") and ls[2].startswith("C | 2 "),
          repr(p.stdout))

    # 11. Compact export requires -o
    p = run({}, "--compact", "export", "x")
    check("export -o required", p.returncode == 2, str(p.returncode))
    out_csv = os.path.join(tmp, "out.txt")
    csv_text = ("title,subreddit,author,score,num_comments,url,permalink\n"
                "Hello world,python,ali,10,3,https://ex.com/a,/r/python/a/\n")
    p = run({"RDT_EXPORT_CSV": csv_text}, "--compact", "export", "x", "-o", out_csv)
    check("export exit0", p.returncode == 0, p.stderr)
    content = open(out_csv, encoding="utf-8").read()
    check("export minimal", content.strip() == "score | sub | title | author | url\n"
          "+10c3 | r/python | Hello world | u/ali | https://ex.com/a",
          repr(content))
    check("export summary", p.stdout.strip() == f"saved {out_csv} (1 rows)", repr(p.stdout))

    # 12. Trailing -c stays with rdt (passthrough)
    open(log, "w").close()
    p = run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
            "comment", "3", "-c")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("-c text preserved", argv == ["comment", "3", "-c"], repr(argv))
    check("-c passthrough mode", p.stdout == open(fixture("listing.json"), encoding="utf-8").read(), "")

    # 13. Trailing --compact does not enable tidy mode
    open(log, "w").close()
    p = run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
            "sub", "python", "--compact")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("trailing --compact passthrough", "--compact" in argv
          and p.stdout == open(fixture("listing.json"), encoding="utf-8").read(), repr(argv))

    # 14. Tidy compact strips rdt --compact for the backend
    open(log, "w").close()
    p = run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
            "--compact", "search", "x", "--compact")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("rdt -c stripped", "--compact" not in argv and "--json" in argv, repr(argv))
    check("still compact output", p.stdout.splitlines()[1].startswith("1 | "), repr(p.stdout[:80]))

    # 15. Compact forces --json over --yaml
    open(log, "w").close()
    p = run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
            "--compact", "sub", "python", "--yaml")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("yaml stripped", "--yaml" not in argv and "--json" in argv, repr(argv))

    # 16. Empty stdout becomes ERR with exit 1
    open(os.path.join(tmp, "empty.json"), "w").close()
    p = run({"RDT_FIXTURE": os.path.join(tmp, "empty.json")},
            "--compact", "sub", "python")
    check("empty output exit1", p.returncode == 1 and p.stdout.startswith("ERR backend:"),
          repr((p.returncode, p.stdout)))

    # 17. Packed -n50 -> -n10
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "search", "x", "-n50")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("packed cap", "-n10" in argv and "-n50" not in argv, repr(argv))

    # 18. Dash-led query keeps the default limit
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "search", "-nonsense")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("dash query + default -n", argv.count("-n") >= 1 and "5" in argv
          and "-nonsense" in argv, repr(argv))

    # 19. Unknown command passes through
    open(log, "w").close()
    p = run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
            "frobnicate", "--x")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("unknown passthrough", argv == ["frobnicate", "--x"]
          and p.stdout == open(fixture("listing.json"), encoding="utf-8").read(), repr(argv))

    # 20. Negative score prints as -5, not +-
    p = run({"RDT_FIXTURE": fixture("neg.json")}, "--compact", "sub", "s")
    check("negative score", p.stdout.splitlines()[1].startswith("1 | -5c0 | "),
          repr(p.stdout))

    # 21. Flag-position -c belongs to rdt; text after `--` is kept
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "-c", "search", "-c")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("-c flag stripped", argv == ["search", "-n", "5", "--json"], repr(argv))
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "-c", "search", "--", "-c")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("-- after -c preserved", argv == ["search", "-n", "5", "--json", "--", "-c"],
          repr(argv))

    # 22. File output preserves the raw limit (no compact clamp to 10)
    out1 = os.path.join(tmp, "list-out.txt")
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "sub", "python", "-n", "50", "-o", out1)
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("file -o keeps -n 50", "50" in argv and "10" not in argv, repr(argv))
    check("file -o no compact --json", "--json" not in argv, repr(argv))
    out2 = os.path.join(tmp, "list-out2.txt")
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "sub", "python", "-n", "50", f"--output={out2}")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("file --output= keeps -n 50", "50" in argv and "10" not in argv, repr(argv))

    # 23. feed --subs-only=true triggers the 5x5 cap via structured parsing
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "feed", "--subs-only=true", "--max-subs", "20", "-n", "25")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("subs-only=true cap", "5" in argv and "20" not in argv and "25" not in argv,
          repr(argv))

    # 24. Export backend success without a file is a backend discrepancy
    missing = os.path.join(tmp, "never-written.csv")
    p = run({"RDT_EXPORT_SKIP": "1"}, "--compact", "export", "x", "-o", missing)
    check("export missing file exit1", p.returncode == 1, str(p.returncode))
    check("export missing file backend msg",
          p.stderr.strip() == f"ERR backend: export did not write {missing}",
          repr((p.stdout, p.stderr)))
    check("export missing file not io", "ERR io" not in p.stderr, repr(p.stderr))

    # 25. `--` escapes help flags: search for literal "-h" stays compact
    open(log, "w").close()
    p = run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
            "--compact", "search", "--", "-h")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("dashdash -h stays compact",
          argv == ["search", "-n", "5", "--json", "--", "-h"], repr(argv))
    check("dashdash -h renders table",
          p.stdout.splitlines()[0] == "no | score | sub | title | author | id",
          repr(p.stdout[:80]))

    # 26. Empty envelope {"ok": true} renders header only, no KeyError
    empty_env = os.path.join(tmp, "empty_env.json")
    open(empty_env, "w", encoding="utf-8").write('{"ok": true}')
    p = run({"RDT_FIXTURE": empty_env}, "--compact", "search", "x")
    check("empty envelope exit0", p.returncode == 0, repr((p.returncode, p.stderr)))
    check("empty envelope header only",
          p.stdout.strip() == "no | score | sub | title | author | id", repr(p.stdout))

    # 27. Null data node does not raise AttributeError
    null_env = os.path.join(tmp, "null_data.json")
    open(null_env, "w", encoding="utf-8").write('{"ok": true, "data": null}')
    p = run({"RDT_FIXTURE": null_env}, "--compact", "search", "x")
    check("null data exit0", p.returncode == 0, repr((p.returncode, p.stderr)))
    check("null data header", "no | score" in p.stdout, repr(p.stdout))

    # 28. Non-dict envelope -> controlled ERR, not AssertionError
    arr_env = os.path.join(tmp, "arr.json")
    open(arr_env, "w", encoding="utf-8").write('[]')
    p = run({"RDT_FIXTURE": arr_env}, "--compact", "search", "x")
    check("array envelope exit1", p.returncode == 1, str(p.returncode))
    check("array envelope msg", "ERR backend: invalid envelope" in p.stdout,
          repr((p.stdout, p.stderr)))
    scalar_env = os.path.join(tmp, "scalar.json")
    open(scalar_env, "w", encoding="utf-8").write('"oops"')
    p = run({"RDT_FIXTURE": scalar_env}, "--compact", "search", "x")
    check("scalar envelope exit1", p.returncode == 1, str(p.returncode))
    check("scalar envelope msg", "ERR backend: invalid envelope" in p.stdout,
          repr((p.stdout, p.stderr)))

    # 29. Double dash keeps -c positional, synthesized opts precede --
    open(log, "w").close()
    p = run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
            "-c", "search", "--", "-c")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("doubledash -n/--json before --",
          argv == ["search", "-n", "5", "--json", "--", "-c"], repr(argv))

    # 30. Packed numeric flag: -n=5 leaves --subs-only as flag
    # (covered in unit, e2e guard: backend receives intact --subs-only)
    open(log, "w").close()
    run({"RDT_FIXTURE": fixture("listing.json"), "RDT_ARGV_LOG": log},
        "--compact", "feed", "--subs-only", "-n=25")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("packed -n= clamps, subs-only intact",
          "--subs-only" in argv and "25" not in argv, repr(argv))

    # 31. Missing subreddit emits r/? with invariant column count
    missing_sub = os.path.join(tmp, "missing_sub.json")
    open(missing_sub, "w", encoding="utf-8").write(json.dumps({
        "ok": True, "data": {"data": {"children": [
            {"kind": "t3", "data": {"id": "a1", "title": "t", "author": "a",
                                    "score": 1, "num_comments": 0}},
        ], "after": None}}}))
    p = run({"RDT_FIXTURE": missing_sub}, "--compact", "search", "x")
    check("missing sub r/?", "r/?" in p.stdout, repr(p.stdout))
    check("missing sub col count",
          len(p.stdout.splitlines()[1].split(" | ")) == len("no | score | sub | title | author | id".split(" | ")),
          repr(p.stdout))

    # 32. Export default cap injects -n 50
    out3 = os.path.join(tmp, "exp3.csv")
    csv_text2 = ("title,subreddit,author,score,num_comments,url\n"
                 "t,s,a,1,0,http://e.com\n")
    open(log, "w").close()
    p = run({"RDT_EXPORT_CSV": csv_text2, "RDT_ARGV_LOG": log},
            "--compact", "export", "x", "-o", out3)
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("export default -n 50", "-n" in argv and "50" in argv, repr(argv))

    # 33. Invalid JSON stdout forwards proc.stderr
    bad_json = os.path.join(tmp, "bad.json")
    open(bad_json, "w", encoding="utf-8").write("not-json\n")
    p = run({"RDT_FIXTURE": bad_json, "RDT_EXIT": "1", "RDT_STDERR": "boom-stderr\n"},
            "--compact", "search", "x")
    check("bad json exit1", p.returncode == 1, str(p.returncode))
    check("bad json stdout passthrough", p.stdout == "not-json\n", repr(p.stdout))
    check("bad json stderr forwarded", "boom-stderr" in p.stderr, repr(p.stderr))

    # 34. Export compact strips -c / --compact / --yaml before backend
    out4 = os.path.join(tmp, "exp4.csv")
    open(log, "w").close()
    p = run({"RDT_EXPORT_CSV": csv_text2, "RDT_ARGV_LOG": log},
            "--compact", "export", "-c", "x", "-o", out4, "--yaml", "--compact")
    argv = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
    check("export strips -c", "-c" not in argv, repr(argv))
    check("export strips --compact", "--compact" not in argv, repr(argv))
    check("export strips --yaml", "--yaml" not in argv, repr(argv))
    check("export format csv", "--format" in argv and "csv" in argv, repr(argv))

print(f"\n{PASS} tests passed")
