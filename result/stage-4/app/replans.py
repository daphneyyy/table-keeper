"""Bounded exact seating search, using accepted capacities and UTC intervals."""
import copy
import re

from .rules import Error, identifier, instant, overlaps, require


def interval(body, restaurant):
    tid = identifier(body, 'table_id')
    require(tid in {t['id'] for t in restaurant['tables']}, 404, 'not_found')
    try:
        for key in ('from', 'to'):
            require(type(body.get(key)) is str and re.fullmatch(
                r'[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})', body[key]))
            if body[key][-1] not in 'Zz':
                require(int(body[key][-5:-3]) < 24 and int(body[key][-2:]) < 60)
            instant(body[key].replace('z', 'Z'))
        require(instant(body['from'].replace('z', 'Z')) < instant(body['to'].replace('z', 'Z')))
    except (Error, ValueError, OverflowError):
        raise Error() from None
    return {k: body[k].replace('z', 'Z') if k != 'table_id' else body[k] for k in ('table_id', 'from', 'to')}


def blocked(record, closures):
    return any(record['restaurant_id'] == c['restaurant_id'] and c['table_id'] in record['table_ids']
               and instant(record['starts_at']) < instant(c['to'])
               and instant(c['from']) < instant(record['ends_at']) for c in closures)


def assign(record, ids):
    result = copy.deepcopy(record)
    result.pop('table_id', None)
    result['table_ids'] = list(ids)
    if len(ids) == 1:
        result['table_id'] = ids[0]
    return result


def solve(restaurant, records, closures, closure):
    """Return the lexicographic optimum; no state mutation or clock dependency.

    Precompute candidate conflicts. At most 10**6 leaves at the documented
    boundary, with changed-count/unused-seat lower bounds pruning subtrees.
    """
    rid = restaurant['id']
    start, end = instant(closure['from']), instant(closure['to'])
    live = [r for r in records if r['restaurant_id'] == rid and r['status'] == 'confirmed']
    considered = sorted([r for r in live if instant(r['starts_at']) < end and start < instant(r['ends_at'])],
                        key=lambda r: r['reference'])
    require(len(restaurant['tables']) <= 6 and len(restaurant.get('combinable', [])) <= 4
            and len(considered) <= 6, 422, 'planning_limit')
    refs = {r['reference'] for r in considered}
    fixed = [r for r in live if r['reference'] not in refs]
    obstacles = list(closures) + [dict(closure, restaurant_id=rid)]
    choices = [[t['id']] for t in restaurant['tables']] + restaurant.get('combinable', [])
    candidates = []
    for record in considered:
        options = []
        for rank, ids in enumerate(choices):
            unused = sum(record['accepted_terms']['capacities'][tid] for tid in ids) - record['party_size']
            candidate = assign(record, ids)
            if unused >= 0 and not blocked(candidate, obstacles) and not any(overlaps(candidate, r) for r in fixed):
                options.append((int(set(ids) != set(record['table_ids'])), unused, rank, candidate))
        require(options, 409, 'no_feasible_plan')
        candidates.append(sorted(options, key=lambda o: o[:3]))
    # All interval/set comparisons are outside the combinatorial loop.
    conflicts = {}
    for i, options in enumerate(candidates):
        for j in range(i):
            conflicts[i, j] = {(a, b) for a, x in enumerate(options) for b, y in enumerate(candidates[j])
                               if overlaps(x[3], y[3])}
    lower = [(0, 0)] * (len(candidates) + 1)
    for i in range(len(candidates) - 1, -1, -1):
        lower[i] = (lower[i+1][0] + min(o[0] for o in candidates[i]),
                    lower[i+1][1] + min(o[1] for o in candidates[i]))
    best, best_picks = None, None

    def search(picks, moved, unused, ranks):
        nonlocal best, best_picks
        i = len(picks)
        if best is not None and (moved + lower[i][0], unused + lower[i][1]) > best[:2]:
            return
        if i == len(candidates):
            score = (moved, unused, tuple(ranks))
            if best is None or score < best:
                best, best_picks = score, list(picks)
            return
        for k, option in enumerate(candidates[i]):
            if not any((k, old) in conflicts[i, j] for j, old in enumerate(picks)):
                search(picks + [k], moved + option[0], unused + option[1], ranks + [option[2]])

    search([], 0, 0, [])
    require(best is not None, 409, 'no_feasible_plan')
    assignments = [dict(reference=r['reference'], table_ids=candidates[i][best_picks[i]][3]['table_ids'],
                        changed=bool(candidates[i][best_picks[i]][0])) for i, r in enumerate(considered)]
    return assignments, best[0], best[1], considered
