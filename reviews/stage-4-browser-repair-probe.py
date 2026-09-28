"""Observe real operator repair versus immutable browser confirmation replay."""
import asyncio
import json
import sys
from pathlib import Path
import httpx
from playwright.async_api import async_playwright, expect

base=sys.argv[1].rstrip('/')
out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url=base,timeout=10)
fixture={'users':[{'id':uid,'email':uid+'@example.test','password':'review-password','display_name':uid.title()} for uid in ['manager','diner']],
 'restaurants':[{'id':'r','name':'The Fern & Fig','timezone':'Europe/Berlin','slot_minutes':30,'reservation_duration_minutes':90,'cancellation_cutoff_minutes':120,
 'manager_user_ids':['manager'],'opening_hours':[{'weekday':'tue','opens':'18:00','closes':'23:00'}],
 'tables':[{'id':'a','label':'Window nook','capacity':2},{'id':'b','label':'Garden side','capacity':2},{'id':'c','label':'Round table','capacity':4}], 'combinable':[['a','b']]}], 'reservations':[]}
assert c.post('/_test/reset',json=fixture).status_code==204
manager=c.post('/auth/login',json={'email':'manager@example.test','password':'review-password'}).json()['token']

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch()
  page=await browser.new_page(viewport={'width':1440,'height':1000})
  await page.goto(base+'/login')
  await page.get_by_test_id('login-email').fill('diner@example.test')
  await page.get_by_test_id('login-password').fill('review-password')
  await page.get_by_test_id('login-submit').click()
  await page.get_by_test_id('restaurant-select').select_option('r')
  await page.get_by_test_id('date-input').fill('2030-01-01')
  await page.get_by_test_id('search-button').click()
  await page.get_by_test_id('slot-a-18:00').click()
  async with page.expect_response(lambda r:r.url.endswith('/reservations') and r.request.method=='POST') as response:
   await page.get_by_test_id('booking-submit').click()
  original_response=await response.value
  original=await original_response.json()
  token=await page.evaluate("JSON.parse(sessionStorage.getItem('tablekeeper-session')).token")
  owner={'Authorization':'Bearer '+token}
  ref=original['reference']
  before=c.get('/reservations/'+ref,headers=owner).json()
  history_before=c.get('/reservations/'+ref+'/history',headers=owner).json()
  preview=c.post('/restaurants/r/replans',json={'table_id':'a','from':'2030-01-01T18:00:00+01:00','to':'2030-01-01T21:00:00+01:00'},headers={'Authorization':'Bearer '+manager,'Idempotency-Key':'preview'})
  assert preview.status_code==201,preview.text
  plan=preview.json()
  assert c.get('/reservations/'+ref,headers=owner).json()==before
  assert c.get('/reservations/'+ref+'/history',headers=owner).json()==history_before
  applied=c.post('/restaurants/r/replans/'+plan['plan_id']+'/apply',json={},headers={'Authorization':'Bearer '+manager,'Idempotency-Key':'apply'})
  assert applied.status_code==201,applied.text
  current=c.get('/reservations/'+ref,headers=owner).json()
  assert current['table_ids']==['b']
  assert current['accepted_terms']==before['accepted_terms']
  assert current['starts_at']==before['starts_at'] and current['ends_at']==before['ends_at']
  assert current['revision']==before['revision']+1
  history=c.get('/reservations/'+ref+'/history',headers=owner).json()['entries']
  assert history[-1]['event']=='reassigned' and history[-1]['plan_id']==plan['plan_id']
  async with page.expect_response(lambda r:r.url.endswith('/reservations') and r.request.method=='POST') as response:
   await page.get_by_test_id('booking-submit').click()
  replay=await response.value
  assert replay.status==200 and await replay.json()==original
  await expect(page.get_by_test_id('confirmation-reference')).to_have_text(ref)
  await expect(page.get_by_test_id('confirmation-tables')).to_have_text('Your tables: Garden side')
  result={'original_receipt_tables':original['table_ids'],'current_lookup_tables':current['table_ids'],
          'replayed_confirmation_tables':await page.get_by_test_id('confirmation-tables').inner_text(),
          'replayed_confirmation_details':await page.get_by_test_id('confirmation-details').inner_text(),
          'accepted_terms_preserved':True,'accepted_times_preserved':True,'original_receipt_preserved':True}
  await page.screenshot(path=str(out/'replayed-confirmation-1440.png'),full_page=True)
  await page.set_viewport_size({'width':375,'height':812})
  assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  await page.screenshot(path=str(out/'replayed-confirmation-375.png'),full_page=True)
  # Failed supplementary reads retain the known POST success, clearly historical.
  detail_url=base+'/reservations/'+ref
  async def fail_detail(route): await route.abort('failed')
  await page.route(detail_url,fail_detail)
  await page.get_by_test_id('booking-submit').click()
  await expect(page.get_by_test_id('confirmation')).to_contain_text('current reservation details are unavailable')
  await expect(page.get_by_test_id('confirmation-reference')).to_have_text(ref)
  await expect(page.get_by_test_id('confirmation-tables')).to_have_text('Original tables: Window nook')
  await expect(page.get_by_test_id('booking-error')).to_have_count(0)
  await expect(page.get_by_test_id('booking-uncertain')).to_have_count(0)
  await page.screenshot(path=str(out/'current-read-failed-375.png'),full_page=True)
  await page.unroute(detail_url,fail_detail)
  # Series changes refresh current time without changing the create receipt.
  adopted=c.post('/series',json={'anchor_reference':ref,'count':2,'interval_weeks':1},headers={**owner,'Idempotency-Key':'adopt'})
  assert adopted.status_code==201,adopted.text
  sid=adopted.json()['series_id']
  amended=c.post('/series/'+sid+'/amend',json={'expected_revision':1,'from_index':0,'local_time':'19:00'},headers={**owner,'Idempotency-Key':'amend'})
  assert amended.status_code==201,amended.text
  await page.get_by_test_id('booking-submit').click()
  await expect(page.get_by_test_id('confirmation-details')).to_contain_text('2030-01-01T19:00')
  # An older detail GET cannot overwrite a newer successful attempt.
  release=asyncio.Event();started=asyncio.Event();first=True
  async def delay_detail(route):
   nonlocal first
   if first:
    first=False
    response=await route.fetch();started.set();await release.wait();await route.fulfill(response=response)
   else: await route.continue_()
  await page.route(detail_url,delay_detail)
  await page.get_by_test_id('booking-submit').click()
  await started.wait()
  moved=c.patch('/reservations/'+ref,json={'table_id':'c'},headers=owner)
  assert moved.status_code==200,moved.text
  await page.get_by_test_id('booking-submit').click()
  await expect(page.get_by_test_id('confirmation-tables')).to_have_text('Your tables: Round table')
  release.set();await page.wait_for_timeout(200)
  await expect(page.get_by_test_id('confirmation-tables')).to_have_text('Your tables: Round table')
  await page.unroute(detail_url,delay_detail)
  result['failed_supplementary_get_preserves_confirmed_original_details']=True
  result['series_amendment_current_time_refreshed']=True
  result['older_detail_response_cannot_overwrite_new_attempt']=True
  await page.get_by_role('link',name='View or manage reservation').click()
  await expect(page.get_by_test_id('reservation-tables')).to_have_text('Round table')
  result['lookup_label']=await page.get_by_test_id('reservation-tables').inner_text()
  await page.get_by_role('link',name='Find a table',exact=True).click()
  await page.get_by_test_id('restaurant-select').select_option('r')
  await page.get_by_test_id('date-input').fill('2030-01-01')
  await page.get_by_test_id('search-button').click()
  await expect(page.get_by_test_id('slot-a-18:00')).to_have_attribute('data-available','false')
  await expect(page.get_by_test_id('slot-b-18:00')).to_have_attribute('data-available','true')
  await expect(page.get_by_test_id('slot-c-18:00')).to_have_attribute('data-available','false')
  result['availability_reflects_closure_and_reassignment']=True
  (out/'repair-ui.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
  await browser.close()

asyncio.run(main())
