"""Every site never seen to differ at a load (reduce_census.py's census, plus ever_differ_extra.json), and 6 host parts,
removed: judge A, the repeats given (default 1 2 3); the removed units that differed in each run are printed and added to
ever_differ_extra.json.   deps/python/python.exe research/tools/reduce_static.py [<repeat> ...]"""
import sys, json
sys.path.insert(0, 'research/tools')
import reduce as R
units = R.load_units()
cen = json.load(open(R.OUT + '/census.json'))
try:
    extra = set(json.load(open(R.OUT + '/ever_differ_extra.json')))
except OSError:
    extra = set()
differ = set(cen['seen']) | extra
host_ok = ['host ' + h for h in ('kernel', 'setjmp', 'vi', 'audio', 'net', 'ipc')]
static = [u['spec'] for u in units if u['spec'].startswith('site ') and u['spec'] not in differ]
sb = sum(u['bytes'] for u in units if u['spec'].startswith('site ') and u['spec'] not in differ)
print('sites never seen to differ:', len(static), '%.1f MB' % (sb / 2**20))
drop = static + host_ok
reps = [int(x) for x in sys.argv[1:]] or [1, 2, 3]
rs = R.run_many([("A", R.SEARCH, "drop", drop, "every site never seen to differ (%d) and 6 host parts, time %d" % (len(static), k), k) for k in reps], 3)
new = set()
for r in rs:
    print(r['pass'], r.get('why', '')[:50], 'hangs', r.get('hangs'), 'removed units that differed in this run:', r.get('removed_that_differed'), r.get('removed_that_differed_top', [])[:5])
    new |= {k for k, v in r.get('removed_that_differed_top', [])}
json.dump(sorted(extra | new), open(R.OUT + '/ever_differ_extra.json', 'w'))
json.dump({'drop': drop, 'static_sites': len(static), 'static_bytes': sb}, open(R.OUT + '/static_set.json', 'w'))
