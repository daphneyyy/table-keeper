"""Independent exhaustive Cartesian-product oracle for the bounded optimizer.

Run from the stage directory: PYTHONPATH=. python tests/check_optimizer.py
This oracle shares no candidate filtering, conflict or objective implementation.
"""
import itertools
import random
from datetime import datetime, timedelta, timezone

from app.replans import solve
from app.rules import Error


def dt(value):
    return datetime.fromisoformat(value)


def collide(a, b):
    return (a['restaurant_id'] == b['restaurant_id'] and set(a['table_ids']).intersection(b['table_ids'])
            and dt(a['starts_at']) < dt(b['ends_at']) and dt(b['starts_at']) < dt(a['ends_at']))


def oracle(restaurant, records, closures, closure):
    considered = sorted([r for r in records if r['status'] == 'confirmed' and r['restaurant_id'] == restaurant['id']
                         and dt(r['starts_at']) < dt(closure['to']) and dt(closure['from']) < dt(r['ends_at'])],
                        key=lambda r: r['reference'])
    fixed = [r for r in records if r not in considered and r['status'] == 'confirmed']
    obstacles = fixed + [dict(restaurant_id=c['restaurant_id'], table_ids=[c['table_id']], starts_at=c['from'], ends_at=c['to'])
                         for c in closures + [dict(closure, restaurant_id=restaurant['id'])]]
    choices = [[t['id']] for t in restaurant['tables']] + restaurant['combinable']
    best, result = None, None
    for ranks in itertools.product(range(len(choices)), repeat=len(considered)):
        assigned = [dict(r, table_ids=choices[k]) for r, k in zip(considered, ranks)]
        unused = [sum(r['accepted_terms']['capacities'][t] for t in r['table_ids']) - r['party_size'] for r in assigned]
        if any(n < 0 for n in unused):
            continue
        if any(collide(a, b) for i, a in enumerate(assigned) for b in obstacles + assigned[:i]):
            continue
        moved = [set(a['table_ids']) != set(b['table_ids']) for a, b in zip(assigned, considered)]
        score = (sum(moved), sum(unused), ranks)
        if best is None or score < best:
            best = score
            result = ([dict(reference=r['reference'], table_ids=r['table_ids'], changed=m)
                       for r, m in zip(assigned, moved)], score[0], score[1])
    return result


def run():
    rng = random.Random(947234)
    origin = datetime(2090, 6, 5, 18, tzinfo=timezone.utc)
    def time(i):
        return (origin + timedelta(minutes=30*i)).isoformat()
    cases = 0
    for size in range(1, 5):
        tables = [chr(97+i) for i in range(size)]
        allpairs = list(itertools.combinations(tables, 2))
        # Exhaust every capacity configuration, closure table, and zero/one/two
        # considered booking count; additional seeded random larger instances.
        for capacities in itertools.product((2, 4), repeat=size):
            for closed in tables:
                for count in range(3):
                    pairs = [list(p) for p in allpairs[:4]]
                    restaurant = dict(id='r', tables=[dict(id=t, capacity=c) for t,c in zip(tables, capacities)], combinable=pairs)
                    records = [dict(reference=f'R{i:02}', restaurant_id='r', status='confirmed', table_ids=[rng.choice(tables)],
                                    party_size=rng.choice((1,2,3,5)), starts_at=time(rng.choice((0,1))), ends_at=time(rng.choice((2,3))),
                                    accepted_terms={'capacities': dict(zip(tables, capacities))}) for i in range(count)]
                    closure = dict(table_id=closed, **{'from':time(0), 'to':time(2)})
                    compare(restaurant, records, [], closure)
                    cases += 1
    for _ in range(300):
        size = rng.randint(2, 6)
        tables = [chr(97+i) for i in range(size)]
        pairs = rng.sample(list(itertools.combinations(tables, 2)), rng.randint(0, min(4, size*(size-1)//2)))
        restaurant = dict(id='r', tables=[dict(id=t, capacity=99) for t in tables], combinable=[list(p) for p in pairs])
        records = []
        for i in range(rng.randint(0, 5)):
            start = rng.randint(-2, 3)
            records.append(dict(reference=f'R{i:02}',restaurant_id='r',status=rng.choice(('confirmed',)*5+('cancelled',)),
                                table_ids=rng.choice([[t] for t in tables]+restaurant['combinable']), party_size=rng.randint(1,7),
                                starts_at=time(start),ends_at=time(start+rng.randint(1,3)),
                                accepted_terms={'capacities':{t:rng.randint(1,5) for t in tables}}))
        closures = [dict(restaurant_id='r',table_id=rng.choice(tables),**{'from':time(2),'to':time(4)})] if rng.random()<.5 else []
        closure = dict(table_id=rng.choice(tables), **{'from':time(0),'to':time(2)})
        compare(restaurant, records, closures, closure)
        cases += 1
    print(f'PASS {cases} exhaustive-oracle comparisons (all 2/4-seat configurations through four tables plus 300 seeded mixed-policy/fixed/closure cases)')


def compare(restaurant, records, closures, closure):
    expected = oracle(restaurant, records, closures, closure)
    try:
        actual = solve(restaurant, records, closures, closure)[:3]
    except Error as exc:
        assert exc.code == 'no_feasible_plan' and expected is None, (expected, exc.code)
    else:
        assert actual == expected, (actual, expected, restaurant, records, closures, closure)


if __name__ == '__main__':
    run()
