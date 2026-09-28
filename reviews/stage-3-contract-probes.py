"""Independent stage-3 contract probes. Resets ONLY the disposable URL passed in."""
import copy
import sys
import httpx

c = httpx.Client(base_url=sys.argv[1], timeout=10)
fixture = {
    'users': [{'id': uid, 'email': uid+'@example.test', 'password': 'review-password', 'display_name': uid}
              for uid in ['manager', 'diner', 'other']],
    'restaurants': [{'id': 'r', 'name': 'Policy review', 'timezone': 'Europe/Berlin',
                     'slot_minutes': 30, 'reservation_duration_minutes': 90, 'cancellation_cutoff_minutes': 120,
                     'manager_user_ids': ['manager'],
                     'opening_hours': [{'weekday': day, 'opens': '00:00', 'closes': '23:59'}
                                       for day in ['mon','tue','wed','thu','fri','sat','sun']],
                     'tables': [{'id': 'a', 'label': 'Window', 'capacity': 2}, {'id': 'b', 'label': 'Garden', 'capacity': 2}, {'id': 'c', 'label': 'Round', 'capacity': 6}],
                     'combinable': [['a','b']]}],
    'reservations': [],
}

def call(method, path, status=200, body=None, owner=None, key=None):
    headers = {}
    if owner: headers['Authorization'] = 'Bearer '+tokens[owner]
    if key: headers['Idempotency-Key'] = key
    response = c.request(method, path, json=body, headers=headers)
    assert response.status_code == status, (method, path, status, response.status_code, response.text)
    return response.json() if response.content else None

def policy(date, duration, capacity, cutoff=60):
    return {'effective_from': date, 'slot_minutes':30, 'reservation_duration_minutes':duration,
            'cancellation_cutoff_minutes':cutoff, 'opening_hours':copy.deepcopy(fixture['restaurants'][0]['opening_hours']),
            'capacities': {'a': capacity, 'b': capacity, 'c': capacity}}

def book(date, table='c', size=2, key='create'):
    body={'restaurant_id':'r', 'starts_at_local':date+'T18:00', 'party_size':size}
    body.update({'table_ids':table} if isinstance(table,list) else {'table_id':table})
    return call('POST','/reservations',201,body,'diner',key), body

assert c.post('/_test/reset',json=fixture).status_code == 204
tokens={uid:c.post('/auth/login',json={'email':uid+'@example.test','password':'review-password'}).json()['token'] for uid in ['manager','diner','other']}
old, old_body=book('2030-02-01',['a','b'],4,'old-pair')
ref=old['reference']
original_history=call('GET',f'/reservations/{ref}/history',owner='diner')
assert old['accepted_terms']['policy_version']==0 and old['revision']==1

p1=policy('2030-02-01',120,3)
first=call('POST','/restaurants/r/policies',201,p1,'manager','p1')
assert first['policy_version']==1
assert call('POST','/restaurants/r/policies',200,p1,'manager','p1')==first
assert call('POST','/restaurants/r/policies',409,{'bad':True},'manager','p1')['error']['code']=='idempotency_key_reuse'
call('POST','/restaurants/r/policies',403,p1,'diner','not-manager')
call('POST','/restaurants/r/policies',401,p1,key='no-token')
bad=policy('2030-02-01',True,3)
assert call('POST','/restaurants/r/policies',422,bad,'manager','invalid')['error']['code']=='validation_failed'
p2=call('POST','/restaurants/r/policies',201,policy('2030-01-01',60,4,30),'manager','p2')
p3=call('POST','/restaurants/r/policies',201,policy('2030-02-01',30,1,15),'manager','p3')
assert [p['policy_version'] for p in call('GET','/restaurants/r/policies')['policies']]==[1,2,3]
assert call('GET','/restaurants/r')['tables'][0]['capacity']==2
assert call('GET',f'/reservations/{ref}',owner='diner')==old
assert call('GET',f'/reservations/{ref}/history',owner='diner')==original_history
noop=call('PATCH',f'/reservations/{ref}',body={'table_ids':['b','a'],'expected_revision':1},owner='diner')
assert noop==old
assert call('GET',f'/reservations/{ref}/history',owner='diner')==original_history
call('PATCH',f'/reservations/{ref}',422,{'party_size':3},'diner')
assert call('GET',f'/reservations/{ref}',owner='diner')==old
changed=call('PATCH',f'/reservations/{ref}',body={'party_size':2,'expected_revision':1},owner='diner')
assert changed['revision']==2 and changed['accepted_terms']['policy_version']==3
assert changed['ends_at'][11:16]=='18:30'
history=call('GET',f'/reservations/{ref}/history',owner='diner')['entries']
assert history[0]['changes'][0]=={'field':'table_ids','from':None,'to':['a','b']}
assert history[1]['changes']==[{'field':'party_size','from':4,'to':2}]
assert history[0]['accepted_terms']['policy_version']==0
assert call('PATCH',f'/reservations/{ref}',409,{'party_size':False,'expected_revision':1},'diner')['error']['code']=='stale_revision'
call('PATCH',f'/reservations/{ref}',422,{'expected_revision':True},'diner')
assert call('POST','/reservations',200,old_body,'diner','old-pair')==old
for suffix in ['history','decision']:
    call('GET',f'/reservations/{ref}/{suffix}',404)
    call('GET',f'/reservations/{ref}/{suffix}',404,owner='other')
    call('GET',f'/reservations/{ref}/{suffix}',404,owner='manager')
ex=call('GET','/availability?restaurant_id=r&date=2030-02-01&party_size=3&explain=true')
slot=next(s for s in ex['slots'] if s['starts_at_local'].endswith('18:00'))
assert [item['table_id'] for item in slot['explain']]==['a','b','c']
assert slot['explain'][0]['rules']==[{'rule':'capacity','holds':False},{'rule':'no_overlap','holds':False}]
assert all(item['policy_version']==3 for item in slot['explain'])
assert slot['available_table_ids']==[]
plain=call('GET','/availability?restaurant_id=r&date=2030-02-01&party_size=3')
assert all('explain' not in s for s in plain['slots'])
for value in ['false','1','']:
    call('GET','/availability?restaurant_id=r&date=2030-02-01&party_size=3&explain='+value,422)
print('PASS publication order/ties/permissions/receipts, old accepted terms, reversed-pair no-op, stale precedence, history privacy and independent explanations')

anchor,anchor_body=book('2030-01-04','c',2,'anchor')
before=call('GET',f"/reservations/{anchor['reference']}/history",owner='diner')
adopt_body={'anchor_reference':anchor['reference'],'count':3,'interval_weeks':1}
series=call('POST','/series',201,adopt_body,'diner','adopt')
sid=series['series_id']
assert series['revision']==1 and series['occurrences'][0]['reservation']==anchor
assert call('GET',f"/reservations/{anchor['reference']}/history",owner='diner')==before
call('GET','/series/'+sid,404)
call('GET','/series/'+sid,404,owner='other')
refs=[o['reference'] for o in series['occurrences']]
assert [o['reservation']['starts_at_local'][:10] for o in series['occurrences']]==['2030-01-04','2030-01-11','2030-01-18']
call('PATCH','/reservations/'+refs[1],body={'party_size':2},owner='diner')
assert call('GET','/series/'+sid,owner='diner')==series
moves={'moves':[{'reference':refs[0],'party_size':3},{'reference':refs[1],'party_size':3}]}
batch=call('POST','/reservation-moves',201,moves,'diner','batch')
current=call('GET','/series/'+sid,owner='diner')
assert current['revision']==2 and [o['exception'] for o in current['occurrences']]==[True,True,False]
call('POST','/reservations/'+refs[2]+'/cancel',body={},owner='diner')
current=call('GET','/series/'+sid,owner='diner')
assert current['revision']==3 and not current['occurrences'][2]['exception']
call('POST','/reservations/'+refs[2]+'/cancel',body={},owner='diner')
assert call('GET','/series/'+sid,owner='diner')==current
assert call('POST','/series',200,adopt_body,'diner','adopt')==series
assert call('POST','/reservation-moves',200,moves,'diner','batch')==batch
assert call('GET','/series/'+sid,owner='diner')==current
print('PASS anchor identity/history, recurrence dates, owner privacy, no-op preservation, batch counts once per series, cancellation and original series/batch replays')

anchor2,_=book('2030-01-25','c',3,'failed-anchor')
body2={'anchor_reference':anchor2['reference'],'count':3,'interval_weeks':1}
snapshot=call('GET','/_test/export')
assert call('POST','/series',422,body2,'diner','retry-adopt')['error']['code']=='party_exceeds_capacity'
assert call('GET','/_test/export')==snapshot
call('POST','/restaurants/r/policies',201,policy('2030-02-01',60,6),'manager','p4')
recovered=call('POST','/series',201,body2,'diner','retry-adopt')
assert recovered['occurrences'][1]['reservation']['accepted_terms']['policy_version']==4
snapshot=c.get('/_test/export').content
assert c.post('/_test/reset',json={'users':[],'restaurants':[],'reservations':[]}).status_code==204
assert c.post('/_test/import',content=snapshot).status_code==204
assert call('GET','/series/'+sid,owner='diner')==current
assert call('POST','/series',200,adopt_body,'diner','adopt')==series
assert call('POST','/reservations',200,old_body,'diner','old-pair')==old
print('PASS failed adoption exact-state rollback/key reuse and populated stage-3 roundtrip with old immutable receipts')
