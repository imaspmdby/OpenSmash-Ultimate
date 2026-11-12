"""The night's run of the reduction, unattended and safe to stop:

    deps/python/python.exe research/tools/reduce_night.py <stop time HH:MM> [--no-search]

1. the witness of judge L (corrected-input rollbacks, nothing removed) on its three matches: must equal the reference;
   a match whose witness does not is left out of the validation (and said); their differing sites join the census;
2. the census widened: the ring on every validation match, a second replay run of each;
3. loop: the candidate set from the census (reduce.py set), its validation (replays on 7 matches, the long ring on 7,
   corrected inputs on up to 3, two repeats); every removed site that differed in a failed trial is put back
   (ever_differ_extra.json) and the loop goes again, until every trial passes, nothing more can be put back, or the
   time is up;
4. if the set is validated and time is left: the search inside the sites that differ (reduce.py search), then the
   validation again; a search result that does not validate is dropped (the validated set comes back);
5. the report (research/map/minimal_set.md) and research/runs/reduce/night.json (what happened, step by step).
Everything goes through reduce.py's trial log: a trial already made is not made again.
"""
import datetime
import json
import os
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reduce as R  # noqa: E402
import reduce_census  # noqa: E402

LOG = os.path.join(R.OUT, "night.json")
EXTRA = os.path.join(R.OUT, "ever_differ_extra.json")


class Args:
    jobs = 3
    minutes = 0
    family = None
    force = False
    reps = 1
    seed = None


def now():
    return time.strftime("%H:%M")


def main():
    hh, mm = sys.argv[1].split(":")
    stop = datetime.datetime.now().replace(hour=int(hh), minute=int(mm), second=0)
    left = lambda: (stop - datetime.datetime.now()).total_seconds() / 60
    events = []

    def note(what, **kw):
        events.append(dict(time=now(), what=what, **kw))
        json.dump(events, open(LOG, "w"), indent=1)
        print(f"[{now()}] {what} {kw if kw else ''}", flush=True)

    a = Args()
    # 1. judge L's witness
    st = R.load_state()
    jobs = [("L", ("lfi.txt", n, []), "drop", [], "witness of judge L on " + n, 0) for n in R.LF_MATCHES]
    res = R.run_many(jobs, 3)
    skip = []
    for n, r in zip(R.LF_MATCHES, res):
        d = os.path.join(R.OUT, "t_" + r["key"], "diff.txt")
        if r["pass"] and os.path.exists(d):
            shutil.copyfile(d, os.path.join(R.OUT, "census_%s_L.txt" % n))
        else:
            skip.append(n)
        note("judge L witness", match=n, passes=r["pass"], lfcompare=r.get("lfcompare"), why=r.get("why"))
    st = R.load_state()
    st["skip_L"] = skip
    R.save_state(st)
    # 2. the census widened
    sys.argv = ["reduce_census.py", "--ring", "--again", "2"]
    try:
        reduce_census.main()
        cen = json.load(open(R.CENSUS))
        note("census", runs=len(cen["files"]), loads=cen["loads"], sites=len(cen["seen"]))
    except Exception:
        note("census failed", error=traceback.format_exc()[-400:])
    # 3. set, validate, put back, again
    validated = False
    for it in range(1, 12):
        if left() < 32:
            note("no time for another validation", minutes_left=round(left()))
            break
        R.step_set(a)
        st = R.load_state()
        note("set", iteration=it, sites=st["static_sites"], mb=round(st["static_bytes"] / 2**20, 1))
        ok = R.step_validate(a)
        st = R.load_state()
        fails = [v for v in st["validation"] if not v["pass"]]
        note("validation", iteration=it, passed=len(st["validation"]) - len(fails), failed=[(v["judge"], v["match"], v.get("why")) for v in fails])
        if ok:
            validated = True
            shutil.copyfile(R.STATE, os.path.join(R.OUT, "validated_state.json"))
            break
        back = set()
        for v in fails:
            back |= {k for k, _n in (v.get("differed") or []) if k.startswith("site ")}
        extra = set(json.load(open(EXTRA))) if os.path.exists(EXTRA) else set()
        new = back - extra
        if not new:
            note("a trial fails and no removed site differed in it: nothing to put back, the loop stops", failed=[(v["judge"], v["match"]) for v in fails])
            break
        json.dump(sorted(extra | new), open(EXTRA, "w"))
        note("sites put back", n=len(new))
    # 4. the search inside the sites that differ
    if validated and "--no-search" not in sys.argv and left() > 75:
        a.minutes = left() - 45
        try:
            note("search starts", minutes=round(a.minutes))
            R.step_search(a)
            st = R.load_state()
            note("search stopped", removed=len(st["removed"]), needed=len(st["needed"]), queue=len(st.get("queue", [])))
            if left() > 30:
                ok = R.step_validate(a)
                st = R.load_state()
                note("validation after the search", ok=ok, failed=[(v["judge"], v["match"]) for v in st["validation"] if not v["pass"]])
                if not ok:
                    shutil.copyfile(R.STATE, os.path.join(R.OUT, "search_not_validated_state.json"))
                    shutil.copyfile(os.path.join(R.OUT, "validated_state.json"), R.STATE)
                    note("the search's set does not validate: kept aside (search_not_validated_state.json), the validated set is back")
            else:
                shutil.copyfile(R.STATE, os.path.join(R.OUT, "search_not_validated_state.json"))
                shutil.copyfile(os.path.join(R.OUT, "validated_state.json"), R.STATE)
                note("no time to validate the search's set: kept aside (search_not_validated_state.json), the validated set is back")
        except Exception:
            note("search failed", error=traceback.format_exc()[-600:])
            if os.path.exists(os.path.join(R.OUT, "validated_state.json")):
                shutil.copyfile(os.path.join(R.OUT, "validated_state.json"), R.STATE)
    try:
        R.step_report(a)
    except Exception:
        note("report failed", error=traceback.format_exc()[-400:])
    note("night run done", validated=validated)


if __name__ == "__main__":
    main()
