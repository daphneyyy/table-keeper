"""Stage-4 HTTP invariants, rollback, races, and real prior-stage imports."""
import copy
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from check_service import DAY, USER, body, call, expect, reset
from check_policies_series import fixture, create, export, history, policy

RP = '/restaurants/restaurant/replans'


def setup():
    data = fixture()
    data['restaurants'][0]['tables'].append(dict(id='c', label='Third', capacity=4))
    data['restaurants'][0]['combinable'] = [['b', 'a'], ['b', 'c']]
    return data


def close(table='a', start='18:00', end='19:30', day=DAY):
    return dict(table_id=table, **{'from':day+'T'+start+':00+00:00','to':day+'T'+end+':00+00:00'})


def preview(token, key='preview', request=None):
    return expect(*call('POST', RP, request or close(), token, key), 201)


def apply(token, plan, key='apply'):
    return call('POST', RP+'/'+plan['plan_id']+'/apply', {}, token, key)


def series(token, count=4):
    anchor = create(token, 'anchor')
    request = dict(anchor_reference=anchor['reference'], count=count, interval_weeks=1)
    result = expect(*call('POST', '/series', request, token, 'adopt'), 201)
    return result, request


def amend(token, agreement, revision, at, key, index=0):
    return call('POST', '/series/'+agreement['series_id']+'/amend',
                dict(expected_revision=revision, from_index=index, local_time=at), token, key)


def run():
    token = reset(setup())
    other = expect(*call('POST', '/auth/login', setup()['users'][1]),200)['token']
    original = create(token, 'original')
    b = create(token, 'b', body('b'))
    fixed = create(token, 'fixed', body('c', '19:30'))
    before = export()
    expect(*call('POST', RP, close(), key='no-token'),401,'unauthenticated')
    expect(*call('POST', RP, close(), other,'nonmanager'),403,'forbidden')
    expect(*call('POST', RP, close(), token),400,'missing_idempotency_key')
    for request in [close(end='18:00'), close(start='20:00'), dict(close(), **{'from':DAY+'T18:00:00'}),
                    dict(close(), **{'from':DAY+'T18:00:00+01:99'}), dict(close(), to=False)]:
        expect(*call('POST', RP,request,token,'bad'),422,'validation_failed')
        assert export() == before
    expect(*call('POST', RP, close('missing'),token,'bad'),404,'not_found')
    expect(*call('POST', RP, dict(close(),table_id=False),token,'bad'),400,'malformed_request')
    plan = preview(token)
    assert plan['moved_count'] == 1 and plan['unused_seats'] == 4
    assert [a['reference'] for a in plan['assignments']] == sorted([original['reference'],b['reference']])
    after = export()
    for field in ('reservations','histories','restaurant_revisions','closures','series'):
        assert before['state'][field] == after['state'][field]
    assert expect(*call('POST',RP,close(),token,'preview'),200) == plan
    result = expect(*apply(token,plan),201)
    repaired = next(r for r in result['reservations'] if r['reference']==original['reference'])
    assert repaired['table_id']=='c' and repaired['revision']==2
    assert repaired['accepted_terms']==original['accepted_terms']
    assert all(repaired[k]==original[k] for k in ('starts_at','ends_at','starts_at_local','party_size','created_at','reservation_id'))
    entry = history(original['reference'],token)[-1]
    assert entry['event']=='reassigned' and entry['plan_id']==plan['plan_id']
    assert entry['changes']==[{'field':'table_ids','from':['a'],'to':['c']}]
    assert len(history(b['reference'],token))==1
    assert expect(*call('GET','/reservations/'+fixed['reference'],token=token),200)==fixed
    expect(*apply(token,plan,'different'),409,'plan_already_applied')
    assert expect(*apply(token,plan),200)==result
    assert expect(*call('POST','/reservations',body(),token,'original'),200)==original
    before = export()
    expect(*call('POST','/reservations',body(),token,'blocked'),409,'table_unavailable')
    expect(*call('PATCH','/reservations/'+b['reference'],{'table_id':'a'},token),409,'table_unavailable')
    assert export()==before
    query='/availability?restaurant_id=restaurant&date='+DAY+'&party_size=2&explain=true'
    slot=next(s for s in expect(*call('GET',query),200)['slots'] if s['starts_at_local'].endswith('18:00'))
    assert not slot['explain'][0]['rules'][1]['holds']
    assert all('a' not in o['table_ids'] for o in slot['available_options'])
    create(token,'adjacent-before',body('a','16:30'))
    create(token,'adjacent-after',body('a','19:30'))
    snapshot=export(); expect(*call('POST','/_test/import',snapshot),204); assert export()==snapshot
    assert expect(*apply(token,plan),200)==result
    print('PASS preview purity, manager/auth/validation, objective, fixed boundary, closure/explain/pair exclusion, reassigned history, receipts, exact snapshot round-trip')

    token=reset(setup()); original=create(token,'original')
    plan=preview(token)
    create(token,'new',body('c','21:00'))
    before=export(); expect(*apply(token,plan),409,'stale_plan'); assert export()==before
    plan=preview(token,'fresh')
    with ThreadPoolExecutor(max_workers=30) as pool:
        results=list(pool.map(lambda i:apply(token,plan,str(i)),range(30)))
    assert [s for s,_ in results].count(201)==1
    assert all(r['error']['code']=='plan_already_applied' for s,r in results if s!=201)
    assert len(export()['state']['closures'])==1 and len(history(original['reference'],token))==2
    token=reset(setup()); create(token,'a'); create(token,'b',body('b')); create(token,'c',body('c'))
    before=export(); expect(*call('POST',RP,close(),token,'impossible'),409,'no_feasible_plan'); assert export()==before
    # An empty repair still installs a closure and invalidates another preview.
    token=reset(setup()); p1=preview(token,'one'); p2=preview(token,'two',close('b'))
    empty=expect(*apply(token,p1),201); assert empty['reservations']==[] and empty['restaurant_revision']==1
    expect(*apply(token,p2,'two'),409,'stale_plan')
    snapshot=export(); expect(*call('POST','/_test/import',snapshot),204); assert export()==snapshot
    print('PASS stale/infeasible rollback, 30-way atomic application race and empty-plan invalidation')

    series_checks()
    for source in sys.argv[2:]:
        migration(source)
    print('All stage-4 supplemental HTTP checks passed')


def series_checks():
    token=reset(setup()); agreement,request=series(token)
    sid=agreement['series_id']; path='/series/'+sid
    refs=[o['reference'] for o in agreement['occurrences']]
    expect(*call('PATCH','/reservations/'+refs[1],{'party_size':3},token),200)
    expect(*call('POST','/reservations/'+refs[2]+'/cancel',{},token),200)
    before=export()
    expect(*call('POST',path+'/amend',{},key='unauth'),401,'unauthenticated')
    other=expect(*call('POST','/auth/login',setup()['users'][1]),200)['token']
    expect(*call('POST',path+'/amend',{},other,'other'),404,'not_found')
    before=export()
    for changes in [dict(expected_revision=True,from_index=0,local_time='20:00'),
                    dict(expected_revision=3,from_index=False,local_time='20:00'),
                    dict(expected_revision=3,from_index=4,local_time='20:00'),
                    dict(expected_revision=3,from_index=0,local_time='24:00')]:
        expect(*call('POST',path+'/amend',changes,token,'bad'),422,'validation_failed'); assert export()==before
    expect(*amend(token,agreement,1,'20:00','stale'),409,'stale_revision'); assert export()==before
    amended=expect(*amend(token,agreement,3,'20:00','amend'),201)
    assert amended['revision']==4
    assert [o['reservation']['starts_at_local'][-5:] for o in amended['occurrences']]==['20:00','18:00','18:00','20:00']
    assert [o['exception'] for o in amended['occurrences']]==[False,True,False,False]
    assert export()['state']['restaurant_revisions']['restaurant']==before['state']['restaurant_revisions']['restaurant']+1
    snapshot=export(); expect(*call('POST','/_test/import',snapshot),204); assert export()==snapshot
    unchanged=expect(*amend(token,agreement,4,'20:00','noop'),201); assert unchanged==amended
    assert export()['state']['histories']==snapshot['state']['histories']
    # Repair two eligible members at once, preserve exception flags, once per series.
    plan=preview(token,'repair',close(day=DAY,end='23:00'))
    expect(*apply(token,plan),201)
    current=expect(*call('GET',path,token=token),200)
    assert current['revision']==5 and [o['exception'] for o in current['occurrences']]==[False,True,False,False]
    assert expect(*amend(token,agreement,3,'20:00','amend'),200)==amended
    snapshot=export(); expect(*call('POST','/_test/import',snapshot),204); assert export()==snapshot
    # New time retains the repaired table and original scheduled date.
    current=expect(*amend(token,agreement,5,'21:00','again'),201)
    assert current['occurrences'][0]['reservation']['table_id']!='a'
    assert current['occurrences'][0]['reservation']['starts_at_local']==DAY+'T21:00'
    assert expect(*call('POST','/series',request,token,'adopt'),200)==agreement
    print('PASS series owner/input rules, exceptions/cancellations, original dates, exact no-ops, repair counter/flags, retained repaired table and original receipts after import')

    token=reset(setup()); agreement,_=series(token,3)
    with ThreadPoolExecutor(max_workers=30) as pool:
        replies=list(pool.map(lambda i:amend(token,agreement,1,'20:00',str(i)),range(30)))
    assert [s for s,_ in replies].count(201)==1
    assert all(r['error']['code']=='stale_revision' for s,r in replies if s!=201)
    token=reset(setup()); agreement,_=series(token,3)
    # Earlier occupancy loses to a later non-occupancy failure.
    create(token,'block',body('a','20:00'))
    p=policy(effective=(date.fromisoformat(DAY)+timedelta(days=14)).isoformat(),capacities={'a':1,'b':4,'c':4})
    expect(*call('POST','/restaurants/restaurant/policies',p,token,'policy'),201)
    before=export(); expect(*amend(token,agreement,1,'20:00','retry'),422,'party_exceeds_capacity'); assert export()==before
    p['capacities']['a']=4
    expect(*call('POST','/restaurants/restaurant/policies',p,token,'fix'),201)
    before=export(); expect(*amend(token,agreement,1,'20:00','retry'),409,'table_unavailable'); assert export()==before
    # Closure conflicts also roll the entire operation back.
    plan=preview(token,'close',close('a','21:00','22:30')); expect(*apply(token,plan),201)
    before=export(); expect(*amend(token,agreement,1,'21:00','closure'),409,'table_unavailable'); assert export()==before
    print('PASS 30-way series revision race; nonoccupancy-before-occupancy precedence; conflict/closure atomic rollback')


def migration(source):
    expect(*call('POST','/_test/reset',fixture(),base=source),204)
    token=expect(*call('POST','/auth/login',USER,base=source),200)['token']
    original=expect(*call('POST','/reservations',body(),token,'old',base=source),201)
    request=dict(anchor_reference=original['reference'],count=4,interval_weeks=1)
    old_series=None
    if 'revision' in original:
        old_series=expect(*call('POST','/series',request,token,'old-series',base=source),201)
        refs=[o['reference'] for o in old_series['occurrences']]
        expect(*call('PATCH','/reservations/'+refs[1],{'table_id':'b'},token,base=source),200)
        expect(*call('POST','/reservations/'+refs[2]+'/cancel',{},token,base=source),200)
    snapshot=expect(*call('GET','/_test/export',base=source),200)
    expect(*call('POST','/_test/import',snapshot),204)
    assert expect(*call('POST','/reservations',body(),token,'old'),200)==original
    expect(*call('POST','/auth/login',USER),200)
    if old_series:
        assert expect(*call('POST','/series',request,token,'old-series'),200)==old_series
        agreement=expect(*call('GET','/series/'+old_series['series_id'],token=token),200)
    else:
        agreement=expect(*call('POST','/series',request,token,'new-series'),201)
    current=expect(*amend(token,agreement,agreement['revision'],'20:00','upgrade'),201)
    assert current['occurrences'][0]['reservation']['starts_at_local']==DAY+'T20:00'
    if old_series:
        assert current['occurrences'][1]['exception'] and current['occurrences'][2]['reservation']['status']=='cancelled'
        assert expect(*call('POST','/series',request,token,'old-series'),200)==old_series
    upgraded=export(); expect(*call('POST','/_test/import',upgraded),204); assert export()==upgraded
    assert expect(*call('POST','/reservations',body(),token,'old'),200)==original
    print('PASS actual populated prior export -> stage4 amendment with hashes/tokens/receipts and changed/cancelled series from '+source)


if __name__=='__main__':
    run()
