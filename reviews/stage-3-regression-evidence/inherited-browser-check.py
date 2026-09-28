import asyncio
import json
from pathlib import Path
import httpx
from playwright.async_api import async_playwright, expect

BASE = 'http://127.0.0.1:65466'
OUT = Path('/Users/daphneyang/Desktop/GitHub/band-output/reviews/stage-3-regression-evidence')
OUT.mkdir(parents=True, exist_ok=True)
client = httpx.Client(base_url=BASE)
fixture = {'users': [{'id': 'ada', 'email': 'ada@example.test', 'password': 'correct horse', 'display_name': 'Ada'}], 'restaurants': [], 'reservations': []}
for rid, name in [('fern', 'The Fern & Fig'), ('olive', 'Olive House')]:
    fixture['restaurants'].append({'id': rid, 'name': name, 'timezone': 'Europe/Berlin', 'slot_minutes': 30, 'reservation_duration_minutes': 90, 'cancellation_cutoff_minutes': 120, 'opening_hours': [{'weekday': day, 'opens': '18:00', 'closes': '23:00'} for day in ['mon','tue','wed','thu','fri','sat']], 'tables': [{'id':'window','label':'Window nook','capacity':2},{'id':'garden','label':'Garden side','capacity':2},{'id':'round','label':'The round table','capacity':4}], 'combinable': [['window','garden']]})
assert client.post('/_test/reset', json=fixture).status_code == 204

async def main():
  async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page(viewport={'width':1440,'height':1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    await page.goto(BASE + '/login')
    await page.get_by_test_id('login-email').fill('ada@example.test')
    await page.get_by_test_id('login-password').fill('correct horse')
    await page.get_by_test_id('login-submit').click()
    await expect(page.get_by_test_id('current-user')).to_have_text('Ada')
    async def search(rid='fern', party='2', date='2030-01-01'):
      await page.get_by_test_id('restaurant-select').select_option(rid)
      await page.get_by_test_id('date-input').fill(date)
      await page.get_by_test_id('party-size-input').fill(party)
      await page.get_by_test_id('search-button').click()
      await expect(page.get_by_test_id('no-slots' if date == '2030-01-06' else 'availability-grid')).to_be_visible()
      await expect(page.locator('.results-head h2')).to_have_text('The Fern & Fig' if rid=='fern' else 'Olive House')
    await search()
    await page.get_by_test_id('slot-window-18:00').click()
    await page.screenshot(path=str(OUT/'desktop-selection.png'), full_page=True)
    await page.get_by_test_id('booking-submit').click()
    await expect(page.get_by_test_id('confirmation-reference')).to_be_visible()
    reference = await page.get_by_test_id('confirmation-reference').inner_text()
    await page.get_by_test_id('booking-submit').click()
    await expect(page.get_by_test_id('confirmation-reference')).to_have_text(reference)
    assert len(client.get('/_test/export').json()['state']['reservations']) == 1
    await page.screenshot(path=str(OUT/'desktop-confirmation.png'), full_page=True)
    await page.get_by_role('link', name='View or manage reservation').click()
    await expect(page.get_by_test_id('reservation-status')).to_have_text('confirmed')
    await page.get_by_test_id('reservation-cancel-button').click()
    await expect(page.get_by_test_id('reservation-status')).to_have_text('cancelled')
    await expect(page.get_by_test_id('reservation-cancel-button')).to_have_count(0)
    print('PASS login, single booking, unchanged repeat, lookup, cancel')

    await page.get_by_role('link', name='Find a table', exact=True).click()
    await search(party='4')
    await expect(page.get_by_test_id('slot-window-18:00')).to_have_attribute('data-available','false')
    await page.get_by_test_id('slot-window+garden-18:00').click()
    await expect(page.get_by_test_id('booking-summary')).to_contain_text('Window nook + Garden side')
    # Server commits the real request, but the connection loses its response.
    captured = []
    async def lose(route):
      captured.append((route.request.post_data, route.request.headers.get('idempotency-key')))
      await route.fetch()
      await route.abort('failed')
    await page.route('**/reservations', lose)
    await page.get_by_test_id('booking-submit').click()
    await expect(page.get_by_test_id('booking-uncertain')).to_be_visible()
    await expect(page.get_by_test_id('booking-error')).to_have_count(0)
    await expect(page.get_by_test_id('confirmation')).to_have_count(0)
    await page.screenshot(path=str(OUT/'desktop-uncertain.png'), full_page=True)
    await page.unroute('**/reservations', lose)
    exported = client.get('/_test/export').content
    assert client.post('/_test/import', content=exported).status_code == 204
    async def observe(route):
      captured.append((route.request.post_data, route.request.headers.get('idempotency-key')))
      await route.continue_()
    await page.route('**/reservations', observe)
    await page.get_by_test_id('booking-submit').click()
    await expect(page.get_by_test_id('confirmation-reference')).to_be_visible()
    await expect(page.get_by_test_id('booking-uncertain')).to_have_count(0)
    await expect(page.get_by_test_id('confirmation-tables')).to_contain_text('Window nook + Garden side')
    assert captured[0] == captured[1]
    await page.unroute('**/reservations', observe)
    await expect(page.get_by_test_id('current-user')).to_have_text('Ada')
    print('PASS combination committed-response loss, unchanged retry body/key, in-page import and identity')

    # Definitive conflict refresh keeps the form and edited inputs.
    await search(party='2', date='2030-01-02')
    await page.get_by_test_id('slot-window-18:00').click()
    await page.get_by_test_id('booking-party-size').fill('1')
    token = client.post('/auth/login',json={'email':'ada@example.test','password':'correct horse'}).json()['token']
    assert client.post('/reservations',json={'restaurant_id':'fern','table_id':'window','starts_at_local':'2030-01-02T18:00','party_size':2},headers={'Authorization':'Bearer '+token,'Idempotency-Key':'competitor'}).status_code == 201
    await page.get_by_test_id('booking-submit').click()
    await expect(page.get_by_test_id('booking-error')).to_be_visible()
    await expect(page.get_by_test_id('booking-party-size')).to_have_value('1')
    await expect(page.get_by_test_id('slot-window-18:00')).to_have_attribute('data-available','false')
    await expect(page.get_by_test_id('confirmation')).to_have_count(0)
    print('PASS conflict refresh preserves selected form and inputs')

    # Delay both metadata and availability A; B must win everywhere.
    release = asyncio.Event()
    async def delayed(route):
      if 'restaurant_id=fern' in route.request.url or route.request.url.endswith('/restaurants/fern'):
        response = await route.fetch()
        await release.wait()
        await route.fulfill(response=response)
      else: await route.continue_()
    await page.route('**/availability?**', delayed)
    await page.route('**/restaurants/*', delayed)
    await page.get_by_test_id('search-button').click()
    await page.get_by_test_id('restaurant-select').select_option('olive')
    await page.get_by_test_id('search-button').click()
    await expect(page.locator('.results-head h2')).to_have_text('Olive House')
    await page.get_by_test_id('slot-garden-19:00').click()
    release.set()
    await page.wait_for_timeout(250)
    await expect(page.locator('.results-head h2')).to_have_text('Olive House')
    await expect(page.get_by_test_id('booking-summary')).to_contain_text('Olive House')
    await page.unroute('**/availability?**', delayed)
    await page.unroute('**/restaurants/*', delayed)
    print('PASS out-of-order metadata and availability cannot overwrite newer grid/form')

    await page.set_viewport_size({'width':375,'height':812})
    await page.screenshot(path=str(OUT/'mobile-selection.png'), full_page=True)
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    await page.get_by_test_id('booking-submit').click()
    await expect(page.get_by_test_id('confirmation-reference')).to_be_visible()
    await page.screenshot(path=str(OUT/'mobile-confirmation.png'), full_page=True)
    await page.get_by_test_id('booking-party-size').fill('1')
    await page.get_by_test_id('booking-submit').click()
    await expect(page.get_by_test_id('booking-error')).to_be_visible()
    assert await page.get_by_test_id('booking-error').inner_text() != ''
    print('PASS mobile layout and edited field creates new request (occupied-slot refusal)')

    await search('olive', date='2030-01-06')
    await expect(page.get_by_test_id('no-slots')).to_be_visible()
    await expect(page.get_by_test_id('availability-grid')).to_have_count(0)
    await page.get_by_test_id('logout-button').click()
    await expect(page.get_by_test_id('current-user')).to_have_count(0)
    await search('olive')
    await page.get_by_test_id('slot-round-20:00').click()
    await expect(page.get_by_test_id('auth-error')).to_be_visible()
    await page.goto(BASE+'/signup')
    await page.get_by_test_id('signup-display-name').fill('Sam')
    await page.get_by_test_id('signup-email').fill('sam@example.test')
    await page.get_by_test_id('signup-password').fill('welcome-table')
    await page.get_by_test_id('signup-submit').click()
    await expect(page.get_by_test_id('current-user')).to_have_text('Sam')
    await page.goto(BASE+'/lookup')
    await expect(page.get_by_test_id('current-user')).to_have_text('Sam')
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    await page.screenshot(path=str(OUT/'mobile-lookup.png'),full_page=True)
    assert not errors, errors
    print('PASS closed day, public browsing/auth gate, signup, direct-route session, zero browser errors')
    await browser.close()

asyncio.run(main())
