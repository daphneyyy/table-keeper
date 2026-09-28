"""Additional bounded-planner, accepted-policy, DST and empty-series cases."""
import copy
from datetime import date, timedelta

from check_service import DAY, body, call, expect, reset
from check_policies_series import create, export, history, policy
from check_replans_series_amend import RP, amend, apply, close, preview, series, setup


def run():
    data=setup(); rest=data['restaurants'][0]
    rest['tables']=[dict(id=t,label=t,capacity=4) for t in 'abcdef']
    rest['combinable']=[['a','b'],['b','c'],['c','d'],['d','e']]
    token=reset(data)
    for i in range(6):
        create(token,str(i),body('f',f'{2*i:02}:00'))
    plan=preview(token,request=close('f','00:00','13:00'))
    assert len(plan['assignments'])==6 and plan['moved_count']==6
    assert all(a['table_ids']==['a'] for a in plan['assignments'])
    expect(*apply(token,plan),201)
    snapshot=export(); expect(*call('POST','/_test/import',snapshot),204); assert export()==snapshot
    token=reset(data)
    for i in range(7): create(token,str(i),body('f',f'{2*i:02}:00'))
    before=export(); expect(*call('POST',RP,close('f','00:00','15:00'),token,'limit'),422,'planning_limit'); assert export()==before
    for too_big in ('tables','pairs'):
        data=setup(); r=data['restaurants'][0]
        r['tables']=[dict(id=t,label=t,capacity=4) for t in 'abcdefg'[:7 if too_big=='tables' else 6]]
        r['combinable']=[['a',t] for t in 'bcdef'] if too_big=='pairs' else []
        token=reset(data); before=export()
        expect(*call('POST',RP,close(),token,'limit'),422,'planning_limit'); assert export()==before
    print('PASS exact supported 6-table/4-pair/6-booking boundary and rollback at each documented planning limit')

    # Accepted capacities dominate a later policy; repairs ignore a past cutoff.
    data=setup(); token=reset(data)
    old=create(token,'past',dict(body(),starts_at_local='2020-06-05T18:00',party_size=4))
    p=policy(effective='2020-01-01',capacities={'a':1,'b':1,'c':1})
    expect(*call('POST','/restaurants/restaurant/policies',p,token,'policy'),201)
    plan=preview(token,request=close(day='2020-06-05'))
    current=expect(*apply(token,plan),201)['reservations'][0]
    assert current['table_id']=='b' and current['accepted_terms']==old['accepted_terms']
    assert history(old['reference'],token)[-1]['event']=='reassigned'
    snapshot=export(); expect(*call('POST','/_test/import',snapshot),204); assert export()==snapshot
    for mutate in ('closure','assignment','history','receipt'):
        bad=copy.deepcopy(snapshot)
        if mutate=='closure': bad['state']['closures'][0]['table_id']='c'
        if mutate=='assignment': bad['state']['plans'][plan['plan_id']]['preview']['assignments'][0]['changed']=False
        if mutate=='history': bad['state']['histories'][old['reference']][-1]['plan_id']='missing'
        if mutate=='receipt': bad['state']['receipts'][-1]['response']['restaurant_revision']+=1
        expect(*call('POST','/_test/import',bad),422,'validation_failed'); assert export()==snapshot
    print('PASS accepted capacities after policy shrink, operator repair past cutoff, corrupted plan/closure/history/receipt import rollback')

    # Restaurant-scoped revisions; fixed bookings can conflict outside the
    # proposed interval with the longer unchanged booking being repaired.
    data=setup(); other=copy.deepcopy(data['restaurants'][0]); other['id']='other'; data['restaurants'].append(other)
    token=reset(data); create(token,'r'); plan=preview(token)
    create(token,'other',dict(body(),restaurant_id='other'))
    expect(*apply(token,plan),201)
    token=reset(setup()); create(token,'a'); create(token,'fixed',body('b','19:00'))
    plan=preview(token,request=close('a','18:00','18:30'))
    assert plan['assignments'][0]['table_ids']==['c']
    print('PASS unrelated-restaurant revision isolation and fixed booking conflict beyond closure interval')

    # Empty eligible sets and expired no-ops must not adopt a policy or tick.
    token=reset(setup()); agreement,_=series(token,2)
    for o in agreement['occurrences']:
        expect(*call('PATCH','/reservations/'+o['reference'],{'party_size':3},token),200)
    before=export(); result=expect(*amend(token,agreement,3,'21:00','empty'),201)
    assert result['revision']==3 and export()['state']['restaurant_revisions']==before['state']['restaurant_revisions']
    # Populate an old series through a validated snapshot: earlier stages allow
    # import of expired confirmed series while normal adoption checks cutoff.
    token=reset(setup()); agreement,_=series(token,2)
    snapshot=export()
    def past(value):
        if isinstance(value,str): return value.replace('2090-','2020-')
        if isinstance(value,list): return [past(x) for x in value]
        if isinstance(value,dict): return {k:past(v) for k,v in value.items()}
        return value
    snapshot=past(snapshot); expect(*call('POST','/_test/import',snapshot),204)
    no_op=expect(*amend(token,agreement,1,'18:00','expired-noop'),201)
    assert no_op['revision']==1
    before=export(); expect(*amend(token,agreement,1,'20:00','expired-change'),409,'cutoff_passed'); assert export()==before
    expect(*amend(token,agreement,999,'20:00','expired-stale'),409,'stale_revision')
    print('PASS empty eligible and expired no-op stability; stale-before-cutoff and real-change cutoff')

    for zone in ('America/New_York','Europe/Berlin'):
        data=setup(); data['restaurants'][0]['timezone']=zone
        if zone=='America/New_York':
            spring=date(2090,3,8); spring+=timedelta(days=(6-spring.weekday())%7)
        else:
            spring=date(2090,3,31); spring-=timedelta(days=(spring.weekday()-6)%7)
        token=reset(data)
        anchor=create(token,'anchor',dict(body(at='00:00'),starts_at_local=(spring-timedelta(days=7)).isoformat()+'T00:00'))
        request=dict(anchor_reference=anchor['reference'],count=2,interval_weeks=1)
        agreement=expect(*call('POST','/series',request,token,'adopt'),201)
        before=export(); expect(*amend(token,agreement,1,'02:30','gap'),422,'invalid_local_time'); assert export()==before
    print('PASS per-occurrence DST gap validation and whole-series rollback in New York and Berlin')


if __name__=='__main__': run()
