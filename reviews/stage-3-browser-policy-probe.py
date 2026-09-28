"""Real browser policy compatibility probe. Resets the disposable target URL."""
import asyncio
import json
import sys
from pathlib import Path
import httpx
from playwright.async_api import async_playwright, expect

base=sys.argv[1].rstrip('/')
out=Path(sys.argv[2]); out.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url=base)
fixture={'users':[{'id':uid,'email':uid+'@example.test','password':'review-password','display_name':uid.title()} for uid in ['manager','diner']],
 'restaurants':[{'id':'fern','name':'The Fern & Fig','timezone':'Europe/Berlin','slot_minutes':30,'reservation_duration_minutes':90,'cancellation_cutoff_minutes':120,
 'manager_user_ids':['manager'],'opening_hours':[{'weekday':'tue','opens':'18:00','closes':'23:00'}],
 'tables':[{'id':'window','label':'Window nook','capacity':2},{'id':'garden','label':'Garden side','capacity':2}], 'combinable':[['window','garden']]}], 'reservations':[]}
assert c.post('/_test/reset',json=fixture).status_code==204
manager=c.post('/auth/login',json={'email':'manager@example.test','password':'review-password'}).json()['token']
policy={'effective_from':'2030-01-01','slot_minutes':60,'reservation_duration_minutes':120,'cancellation_cutoff_minutes':30,
 'opening_hours':[{'weekday':'tue','opens':'18:00','closes':'23:00'}],'capacities':{'window':3,'garden':3}}

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch()
  page=await browser.new_page(viewport={'width':1440,'height':1000})
  await page.goto(base+'/login')
  await page.get_by_test_id('login-email').fill('diner@example.test')
  await page.get_by_test_id('login-password').fill('review-password')
  await page.get_by_test_id('login-submit').click()
  await expect(page.get_by_test_id('current-user')).to_have_text('Diner')
  assert c.post('/restaurants/fern/policies',json=policy,headers={'Authorization':'Bearer '+manager,'Idempotency-Key':'browser-policy'}).status_code==201
  await page.get_by_test_id('restaurant-select').select_option('fern')
  await page.get_by_test_id('date-input').fill('2030-01-01')
  await page.get_by_test_id('party-size-input').fill('5')
  await page.get_by_test_id('search-button').click()
  await expect(page.get_by_test_id('slot-window+garden-18:00')).to_have_attribute('data-available','true')
  await expect(page.get_by_test_id('slot-window-18:00')).to_have_attribute('data-available','false')
  await expect(page.get_by_test_id('slot-window-18:30')).to_have_count(0)
  availability=c.get('/availability',params={'restaurant_id':'fern','date':'2030-01-01','party_size':5}).json()
  row=page.locator('.seating-row').filter(has=page.get_by_test_id('slot-window+garden-18:00'))
  capacity_text=await row.locator('.capacity').inner_text()
  assert capacity_text=='Up to 6 guests', capacity_text
  unavailable_row=page.locator('.seating-row').filter(has=page.get_by_test_id('slot-window-18:00'))
  assert await unavailable_row.locator('.capacity').inner_text()=='Single table'
  await page.get_by_test_id('slot-window+garden-18:00').click()
  assert 'Cancellation terms are confirmed with your reservation.' in await page.locator('.booking-card > .fine-print').inner_text()
  await page.get_by_test_id('booking-submit').click()
  await expect(page.get_by_test_id('confirmation-reference')).to_be_visible()
  fineprint=await page.locator('.booking-card > .fine-print').inner_text()
  assert '30 minutes' in fineprint and '120 minutes' not in fineprint
  token=await page.evaluate("JSON.parse(sessionStorage.getItem('tablekeeper-session')).token")
  ref=await page.get_by_test_id('confirmation-reference').inner_text()
  record=c.get('/reservations/'+ref,headers={'Authorization':'Bearer '+token}).json()
  assert record['accepted_terms']['cancellation_cutoff_minutes']==30
  assert record['ends_at'][11:16]=='20:00'
  await expect(page.get_by_test_id('confirmation-tables')).to_contain_text('Window nook + Garden side')
  result={'grid_follows_published_policy':True,'available_option':availability['slots'][0]['available_options'][0],
          'displayed_capacity':capacity_text,'displayed_booking_fineprint':fineprint,
          'accepted_cutoff_minutes':record['accepted_terms']['cancellation_cutoff_minutes'],
          'accepted_ends_at':record['ends_at'],'confirmation_details':await page.get_by_test_id('confirmation-details').inner_text()}
  await page.screenshot(path=str(out/'policy-confirmation-1440.png'),full_page=True)
  await page.set_viewport_size({'width':375,'height':812})
  assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  await page.screenshot(path=str(out/'policy-confirmation-375.png'),full_page=True)
  # A newer policy cannot rewrite an original receipt's accepted cutoff.
  later=dict(policy,cancellation_cutoff_minutes=10)
  assert c.post('/restaurants/fern/policies',json=later,headers={'Authorization':'Bearer '+manager,'Idempotency-Key':'later-browser-policy'}).status_code==201
  await page.get_by_test_id('booking-submit').click()
  await expect(page.get_by_test_id('confirmation-reference')).to_have_text(ref)
  assert '30 minutes' in await page.locator('.booking-card > .fine-print').inner_text()
  await page.get_by_role('link',name='View or manage reservation').click()
  await expect(page.get_by_test_id('reservation-tables')).to_contain_text('Window nook + Garden side')
  result['lookup_detail']=await page.get_by_test_id('reservation-detail').inner_text()
  (out/'policy-ui.json').write_text(json.dumps(result,indent=2))
  print(json.dumps(result,indent=2))
  print('PASS authoritative/neutral capacity, neutral pending cutoff, accepted cutoff after success/replay, 375/1440 rendering')
  await browser.close()

asyncio.run(main())
