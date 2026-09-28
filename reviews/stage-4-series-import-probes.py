"""Real stage-3 changed/cancelled series import, repair, amendment and replay."""
import sys
import httpx

source=httpx.Client(base_url=sys.argv[1],timeout=10)
target=httpx.Client(base_url=sys.argv[2],timeout=10)
fixture={'users':[{'id':uid,'email':uid+'@example.test','password':'review-password','display_name':uid} for uid in ['m','u']],
 'restaurants':[{'id':'r','name':'Review','timezone':'Europe/Berlin','slot_minutes':30,'reservation_duration_minutes':90,'cancellation_cutoff_minutes':120,'manager_user_ids':['m'],
 'opening_hours':[{'weekday':'tue','opens':'18:00','closes':'23:00'}],
 'tables':[{'id':'a','label':'Window','capacity':2},{'id':'b','label':'Garden','capacity':2},{'id':'c','label':'Round','capacity':4}], 'combinable':[['a','b']]}], 'reservations':[]}
assert source.post('/_test/reset',json=fixture).status_code==204
tokens={uid:source.post('/auth/login',json={'email':uid+'@example.test','password':'review-password'}).json()['token'] for uid in ['m','u']}

def call(client,method,path,status=200,body=None,who='u',key=None):
 headers={'Authorization':'Bearer '+tokens[who]}
 if key:headers['Idempotency-Key']=key
 r=client.request(method,path,json=body,headers=headers)
 assert r.status_code==status,(path,status,r.status_code,r.text)
 return r.json() if r.content else None

booking={'restaurant_id':'r','table_id':'a','starts_at_local':'2030-01-01T18:00','party_size':2}
anchor=call(source,'POST','/reservations',201,booking,key='anchor')
adoption={'anchor_reference':anchor['reference'],'count':4,'interval_weeks':1}
original=call(source,'POST','/series',201,adoption,key='series')
sid=original['series_id'];refs=[o['reference'] for o in original['occurrences']]
call(source,'PATCH','/reservations/'+refs[1],body={'starts_at_local':'2030-01-08T20:00'})
call(source,'POST','/reservations/'+refs[2]+'/cancel',body={})
changed=call(source,'GET','/series/'+sid)
assert changed['revision']==3 and [o['exception'] for o in changed['occurrences']]==[False,True,False,False]
assert target.post('/_test/import',content=source.get('/_test/export').content).status_code==204
assert call(target,'GET','/series/'+sid)==changed
assert call(target,'POST','/series',200,adoption,key='series')==original
assert call(target,'POST','/reservations',200,booking,key='anchor')==anchor
plan=call(target,'POST','/restaurants/r/replans',201,{'table_id':'a','from':'2030-01-01T18:00:00+01:00','to':'2030-01-01T20:00:00+01:00'},'m','preview')
assert call(target,'GET','/series/'+sid)==changed
applied=call(target,'POST','/restaurants/r/replans/'+plan['plan_id']+'/apply',201,{},'m','apply')
repaired=call(target,'GET','/series/'+sid)
assert repaired['revision']==4
assert [o['exception'] for o in repaired['occurrences']]==[False,True,False,False]
assert repaired['occurrences'][0]['reservation']['table_ids']==['b']
assert repaired['occurrences'][0]['reservation']['accepted_terms']==anchor['accepted_terms']
assert repaired['occurrences'][0]['reservation']['ends_at']==anchor['ends_at']
assert applied['restaurant_revision']==plan['restaurant_revision']+1
assert call(target,'POST','/restaurants/r/replans/'+plan['plan_id']+'/apply',200,{},'m','apply')==applied
assert call(target,'POST','/restaurants/r/replans/'+plan['plan_id']+'/apply',409,{},'m','new-apply')['error']['code']=='plan_already_applied'
amend={'expected_revision':4,'from_index':0,'local_time':'19:00'}
amended=call(target,'POST','/series/'+sid+'/amend',201,amend,key='amend')
assert amended['revision']==5
assert [o['reservation']['starts_at_local'] for o in amended['occurrences']]==['2030-01-01T19:00','2030-01-08T20:00','2030-01-15T18:00','2030-01-22T19:00']
assert [o['exception'] for o in amended['occurrences']]==[False,True,False,False]
assert amended['occurrences'][0]['reservation']['table_ids']==['b']
snapshot=target.get('/_test/export').content
assert call(target,'POST','/series/'+sid+'/amend',409,amend,key='stale')['error']['code']=='stale_revision'
assert target.get('/_test/export').content==snapshot
noop=call(target,'POST','/series/'+sid+'/amend',201,dict(amend,expected_revision=5),key='noop')
assert noop==amended
call(target,'POST','/reservations/'+refs[3]+'/cancel',body={})
empty_before=call(target,'GET','/series/'+sid)
empty=call(target,'POST','/series/'+sid+'/amend',201,{'expected_revision':6,'from_index':1,'local_time':'21:00'},key='empty')
assert empty==empty_before
assert call(target,'POST','/series/'+sid+'/amend',200,amend,key='amend')==amended
available=target.get('/availability',params={'restaurant_id':'r','date':'2030-01-01','party_size':2,'explain':'true'}).json()['slots']
at18=next(s for s in available if s['starts_at_local'].endswith('18:00'))
at20=next(s for s in available if s['starts_at_local'].endswith('20:00'))
assert not at18['explain'][0]['rules'][1]['holds']
assert 'a' in at20['available_table_ids']
saved=target.get('/_test/export').content
assert target.post('/_test/reset',json={'users':[],'restaurants':[],'reservations':[]}).status_code==204
assert target.post('/_test/import',content=saved).status_code==204
assert call(target,'GET','/series/'+sid)==empty
assert call(target,'POST','/series/'+sid+'/amend',200,amend,key='amend')==amended
assert call(target,'POST','/restaurants/r/replans/'+plan['plan_id']+'/apply',200,{},'m','apply')==applied
print('PASS actual stage3 changed/cancelled series import, old booking/series receipts, repair terms/times/flags, current-table series amendment, skipped exceptions/cancelled, stale rollback, no-op/empty, half-open closure/explanations, roundtrip and immutable apply/amend receipts')
