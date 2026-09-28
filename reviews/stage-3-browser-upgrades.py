"""Lost-response browser continuity from real earlier service exports to stage 3."""
import asyncio
import sys
import httpx
from playwright.async_api import async_playwright, expect

target=sys.argv[1].rstrip('/')
sources=[(1,sys.argv[2].rstrip('/')),(2,sys.argv[3].rstrip('/'))]
fixture={'users':[{'id':'ada','email':'ada@example.test','password':'review-password','display_name':'Ada'}],
 'restaurants':[{'id':'r','name':'Upgrade room','timezone':'Europe/Berlin','slot_minutes':30,'reservation_duration_minutes':90,'cancellation_cutoff_minutes':120,
 'opening_hours':[{'weekday':'tue','opens':'18:00','closes':'23:00'}],
 'tables':[{'id':'a','label':'Window','capacity':2},{'id':'b','label':'Garden','capacity':2}], 'combinable':[['a','b']]}], 'reservations':[]}

async def scenario(browser, stage, source):
 assert httpx.post(source+'/_test/reset',json=fixture).status_code==204
 page=await browser.new_page()
 upgraded=False
 attempts=[]
 async def transport(route):
  req=route.request
  path=req.url[len(target):]
  if path.startswith('/static/') or path in ['/','/login','/signup','/lookup']:
   await route.continue_(); return
  if not upgraded:
   response=await route.fetch(url=source+path)
   if path=='/reservations' and req.method=='POST':
    attempts.append((req.post_data,req.headers['idempotency-key']))
    assert response.status==201
    await route.abort('failed'); return
   await route.fulfill(response=response)
  else:
   if path=='/reservations' and req.method=='POST': attempts.append((req.post_data,req.headers['idempotency-key']))
   await route.continue_()
 await page.route(target+'/**',transport)
 await page.goto(target+'/login')
 await page.get_by_test_id('login-email').fill('ada@example.test')
 await page.get_by_test_id('login-password').fill('review-password')
 await page.get_by_test_id('login-submit').click()
 await page.get_by_test_id('restaurant-select').select_option('r')
 await page.get_by_test_id('date-input').fill('2030-01-01')
 await page.get_by_test_id('party-size-input').fill('2' if stage==1 else '3')
 await page.get_by_test_id('search-button').click()
 await page.get_by_test_id('slot-a-18:00' if stage==1 else 'slot-a+b-18:00').click()
 await page.get_by_test_id('booking-submit').click()
 await expect(page.get_by_test_id('booking-uncertain')).to_be_visible()
 snapshot=httpx.get(source+'/_test/export').content
 imported=httpx.post(target+'/_test/import',content=snapshot)
 assert imported.status_code==204, imported.text
 upgraded=True
 await page.get_by_test_id('booking-submit').click()
 await expect(page.get_by_test_id('confirmation-reference')).to_be_visible()
 await expect(page.get_by_test_id('booking-uncertain')).to_have_count(0)
 await expect(page.get_by_test_id('current-user')).to_have_text('Ada')
 assert 'Cancellation terms are confirmed with your reservation.' in await page.locator('.booking-card > .fine-print').inner_text()
 await expect(page.get_by_test_id('confirmation-tables')).to_contain_text('Window')
 if stage==2: await expect(page.get_by_test_id('confirmation-tables')).to_contain_text('Garden')
 assert attempts[0]==attempts[1]
 ref=await page.get_by_test_id('confirmation-reference').inner_text()
 await page.get_by_role('link',name='View or manage reservation').click()
 await expect(page.get_by_test_id('reservation-status')).to_have_text('confirmed')
 token=await page.evaluate("JSON.parse(sessionStorage.getItem('tablekeeper-session')).token")
 headers={'Authorization':'Bearer '+token,'Idempotency-Key':'adopt-imported'}
 adopted=httpx.post(target+'/series',json={'anchor_reference':ref,'count':2,'interval_weeks':1},headers=headers)
 assert adopted.status_code==201, adopted.text
 assert adopted.json()['occurrences'][0]['reference']==ref
 assert adopted.json()['occurrences'][0]['reservation']['accepted_terms']['policy_version']==0
 await page.close()
 print(f'PASS actual stage-{stage}→3 import: same browser token/pending body/key, old receipt labels/reference, lookup, imported-anchor adoption')

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch()
  for stage,source in sources: await scenario(browser,stage,source)
  await browser.close()

asyncio.run(main())
