/* Same-origin browser client. A pending attempt owns immutable body text + key. */
(() => {
  'use strict';
  const main = document.getElementById('main');
  const navigation = document.getElementById('navigation');
  let session = null;
  try { session = JSON.parse(sessionStorage.getItem('tablekeeper-session')); } catch (_) { /* Storage may be unavailable. */ }
  if (!session || !session.token || typeof session.display_name !== 'string') session = null;
  let routeVersion = 0;
  let searchVersion = 0;
  let lookupVersion = 0;
  let search = null;
  let selection = null;
  let restaurants = [];

  function element(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'class') node.className = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
      else if (value !== false && value != null) node.setAttribute(key, value === true ? '' : String(value));
    }
    for (const child of children.flat()) if (child != null) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }
  const text = (tag, className, content) => element(tag, {class: className}, content);
  function notice(host, message, testid, kind = 'error') {
    const attrs = {class: `notice ${kind}`, role: kind === 'error' ? 'alert' : 'status'};
    if (testid) attrs['data-testid'] = testid;
    host.append(element('div', attrs, message));
  }
  function loading(host, message) { host.replaceChildren(element('div', {class: 'loading', role: 'status'}, message)); }
  function field(label, id, attrs = {}) {
    const input = element(attrs.tag || 'input', {id, 'data-testid': id, ...attrs});
    input.removeAttribute('tag');
    return {input, node: element('div', {class: 'field'}, element('label', {for: id}, label), input)};
  }
  class ApiError extends Error {
    constructor(status, data) { super(data?.error?.message || 'Your request could not be completed. Please try again.'); this.status = status; this.code = data?.error?.code; }
  }
  async function api(path, options = {}) {
    const headers = {'Content-Type': 'application/json', ...options.headers};
    if (session) headers.Authorization = `Bearer ${session.token}`;
    const response = await fetch(path, {...options, headers});
    let data;
    try { data = await response.json(); } catch (_) { throw new Error('The response could not be read.'); }
    if (!response.ok) throw new ApiError(response.status, data);
    return data;
  }
  function saveSession(value) {
    session = value;
    try { if (value) sessionStorage.setItem('tablekeeper-session', JSON.stringify(value)); else sessionStorage.removeItem('tablekeeper-session'); } catch (_) { /* The current page session still works. */ }
    renderNavigation();
  }
  function navigate(path) {
    history.pushState({}, '', path);
    renderRoute();
    window.scrollTo({top: 0, behavior: 'instant'});
    main.focus({preventScroll: true});
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    const url = new URL(link.href, location.href);
    if (url.origin === location.origin && ['/', '/login', '/signup', '/lookup'].includes(url.pathname) && !url.hash) {
      event.preventDefault(); navigate(url.pathname + url.search);
    }
  });
  window.addEventListener('popstate', renderRoute);
  function renderNavigation() {
    navigation.replaceChildren();
    for (const [href, label] of [['/', 'Find a table'], ['/lookup', 'My reservation']]) {
      navigation.append(element('a', {href, class: 'nav-link', 'aria-current': location.pathname === href ? 'page' : null}, label));
    }
    if (session) {
      navigation.append(text('span', 'user-name', session.display_name));
      navigation.lastChild.dataset.testid = 'current-user';
      navigation.append(element('button', {type: 'button', class: 'nav-button', 'data-testid': 'logout-button', onclick: () => { saveSession(null); renderRoute(); }}, 'Log out'));
    } else {
      navigation.append(element('a', {href: '/login', class: 'nav-link', 'aria-current': location.pathname === '/login' ? 'page' : null}, 'Log in'));
      navigation.append(element('a', {href: '/signup', class: 'nav-button'}, 'Sign up'));
    }
  }
  function renderRoute() {
    routeVersion++; searchVersion++; lookupVersion++; search = null; selection = null;
    main.replaceChildren(); renderNavigation();
    if (location.pathname === '/signup' || location.pathname === '/login') renderAuth(location.pathname === '/signup');
    else if (location.pathname === '/lookup') renderLookup();
    else renderSearch();
  }
  function intro(eyebrow, heading, description) {
    return element('section', {class: 'intro-panel'}, text('span', 'eyebrow', eyebrow), text('h1', '', heading), text('p', '', description), element('div', {class: 'intro-note'}, element('span', {'aria-hidden': 'true'}, '✳'), 'The best evenings start with a table.'));
  }
  function renderAuth(signup) {
    document.title = `${signup ? 'Sign up' : 'Log in'} — Tablekeeper`;
    const mode = signup ? 'signup' : 'login';
    const card = element('section', {class: 'form-card'}, text('h2', '', signup ? 'Make yourself at home.' : 'Good to see you again.'), text('p', '', signup ? 'Create an account to reserve your next gathering.' : 'Log in to book a table or manage your reservation.'));
    const form = element('form');
    const email = field('Email address', `${mode}-email`, {type: 'email', autocomplete: 'email', required: true, placeholder: 'you@example.com'});
    const password = field('Password', `${mode}-password`, {type: 'password', autocomplete: signup ? 'new-password' : 'current-password', required: true, ...(signup ? {minlength: 8} : {})});
    let name;
    if (signup) { name = field('Your name', 'signup-display-name', {autocomplete: 'name', required: true, placeholder: 'What should we call you?'}); form.append(name.node); }
    form.append(email.node, password.node);
    const submit = element('button', {class: 'primary', type: 'submit', 'data-testid': `${mode}-submit`}, signup ? 'Create account →' : 'Log in →');
    const feedback = element('div', {'aria-live': 'polite'});
    form.append(submit); card.append(form, feedback, element('p', {class: 'form-switch'}, signup ? 'Already have an account? ' : 'New around here? ', element('a', {href: signup ? '/login' : '/signup'}, signup ? 'Log in' : 'Create an account')));
    main.append(element('div', {class: 'split-page'}, intro('A place for you', signup ? 'More evenings.\nMore together.' : 'Your table\nis waiting.', 'A familiar face, a favourite place, or something entirely new. Make room for your next good evening.'), card));
    form.addEventListener('submit', async event => {
      event.preventDefault(); feedback.replaceChildren(); submit.disabled = true;
      const version = routeVersion;
      const body = {email: email.input.value, password: password.input.value};
      if (signup) body.display_name = name.input.value;
      submit.textContent = signup ? 'Creating account…' : 'Logging in…';
      try {
        const data = await api(`/auth/${mode}`, {method: 'POST', body: JSON.stringify(body)});
        if (version !== routeVersion) return;
        saveSession(data); navigate('/');
      } catch (error) {
        if (version === routeVersion) notice(feedback, error instanceof ApiError ? error.message : 'We could not connect. Please try again.', 'auth-error');
      } finally { submit.disabled = false; submit.textContent = signup ? 'Create account →' : 'Log in →'; }
    });
  }

  function empty(host, heading, description, testid) {
    host.replaceChildren(element('div', {class: 'empty-state', ...(testid ? {'data-testid': testid} : {})}, element('span', {class: 'empty-icon', 'aria-hidden': 'true'}, '✳'), text('h3', '', heading), text('p', '', description)));
  }
  function tableIds(record) { return record.table_ids || (record.table_id ? [record.table_id] : []); }
  function tableLabels(restaurant, ids) { return ids.map(id => restaurant.tables.find(t => t.id === id)?.label || id).join(' + '); }
  function readableDate(value) {
    const [y, m, d] = value.split('-').map(Number);
    const date = new Date(0); date.setUTCFullYear(y, m - 1, d); date.setUTCHours(12);
    return new Intl.DateTimeFormat('en', {weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC'}).format(date);
  }
  function renderSearch() {
    document.title = 'Tablekeeper — A place at the table';
    const hero = element('section', {class: 'hero'}, element('div', {class: 'hero-copy'}, text('span', 'eyebrow', 'For the moments worth sharing'), element('h1', {}, 'Good company.', element('br'), element('em', {}, 'We’ll keep a table.')), text('p', '', 'Pick a place. Bring your people. Find a little time to sit down together.')), element('div', {class: 'hero-art', 'aria-hidden': 'true'}, element('div', {class: 'table-art'}, element('span', {class: 'chair one'}), element('span', {class: 'chair two'}), element('span', {class: 'plate'}), element('span', {class: 'vase'}), element('span', {class: 'plate'})), text('span', 'art-note', 'Pull up a chair.')));
    const form = element('form', {class: 'search-panel', 'aria-label': 'Search for a table'});
    const restaurant = field('THE RESTAURANT', 'restaurant-select', {tag: 'select', required: true});
    restaurant.input.append(element('option', {value: ''}, 'Loading restaurants…'));
    const today = new Date();
    const date = field('THE DATE', 'date-input', {type: 'date', required: true});
    date.input.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    const party = field('YOUR PARTY', 'party-size-input', {type: 'number', min: 1, step: 1, required: true, value: 2});
    const button = element('button', {type: 'submit', class: 'primary', 'data-testid': 'search-button'}, 'Find a table →');
    form.append(restaurant.node, date.node, party.node, button);
    const feedback = element('div', {'aria-live': 'polite'});
    const results = element('section', {class: 'results-column', 'aria-label': 'Available tables', 'aria-live': 'polite'});
    const booking = element('aside', {class: 'booking-card', 'aria-label': 'Your table'});
    main.append(hero, form, element('div', {class: 'search-hint'}, element('span', {}, 'A little planning. A lovely evening.'), element('span', {}, 'All times are local to the restaurant.')), feedback, element('div', {class: 'workspace'}, results, booking));
    empty(results, 'Where shall we meet?', 'Choose a restaurant, date and party size to see the tables waiting for you.');
    renderBookingPlaceholder(booking);
    const version = routeVersion;
    api('/restaurants').then(data => {
      if (version !== routeVersion) return;
      restaurants = data.restaurants;
      restaurant.input.replaceChildren(...restaurants.map(r => element('option', {value: r.id}, r.name)));
      if (!restaurants.length) {
        restaurant.input.append(element('option', {value: ''}, 'No restaurants available'));
        notice(feedback, 'There are no restaurants to browse right now. Please check back soon.', null, 'info');
      }
    }).catch(() => {
      if (version !== routeVersion) return;
      restaurant.input.replaceChildren(element('option', {value: ''}, 'Could not load restaurants'));
      notice(feedback, element('span', {}, 'We could not load restaurants. ', element('button', {class: 'secondary', type: 'button', onclick: renderRoute}, 'Try again')), null);
    });
    form.addEventListener('submit', event => {
      event.preventDefault();
      runSearch({restaurant_id: restaurant.input.value, date: date.input.value, party_size: party.input.value}, {results, booking, feedback});
    });
  }
  async function runSearch(query, hosts, preserveSelection = false) {
    const generation = ++searchVersion;
    const page = routeVersion;
    const savedSelection = selection;
    hosts.feedback.replaceChildren();
    if (!preserveSelection) { selection = null; search = null; renderBookingPlaceholder(hosts.booking); }
    loading(hosts.results, 'Finding a place for you…');
    try {
      const [restaurant, availability] = await Promise.all([
        api(`/restaurants/${encodeURIComponent(query.restaurant_id)}`),
        api(`/availability?${new URLSearchParams(query)}`)
      ]);
      if (generation !== searchVersion || page !== routeVersion) return;
      search = {query: {...query}, restaurant, availability, hosts};
      if (preserveSelection && selection !== savedSelection) return;
      renderResults();
    } catch (error) {
      if (generation !== searchVersion || page !== routeVersion) return;
      empty(hosts.results, 'Let’s try that again.', 'Your search could not be completed. Check your choices and try again.');
      notice(hosts.feedback, error instanceof ApiError ? error.message : 'We could not connect to the restaurant. Please try again.', null);
    }
  }
  function renderResults() {
    const {restaurant, availability, query, hosts} = search;
    const summary = element('div', {class: 'results-head'}, element('div', {}, text('span', 'eyebrow', 'Make an evening of it'), text('h2', '', restaurant.name), text('p', '', `${readableDate(query.date)} · ${query.party_size} ${Number(query.party_size) === 1 ? 'guest' : 'guests'} · ${restaurant.timezone}`)), element('div', {class: 'legend'}, element('span', {}, element('i', {class: 'dot'}), 'Available'), element('span', {}, element('i', {class: 'dot unavailable'}), 'Unavailable')));
    hosts.results.replaceChildren(summary);
    if (!availability.slots.length) {
      const box = element('div'); empty(box, 'A quiet day here.', 'There are no booking times on this date. Try another day for your gathering.', 'no-slots'); hosts.results.append(box); return;
    }
    const grid = element('div', {class: 'seating-list', 'data-testid': 'availability-grid'});
    const choices = restaurant.tables.map(t => ({ids: [t.id]}));
    for (const pair of restaurant.combinable || []) {
      if (availability.slots.some(slot => (slot.available_options || []).some(option => option.table_ids.length === 2 && pair.every(id => option.table_ids.includes(id))))) {
        choices.push({ids: pair});
      }
    }
    for (const choice of choices) {
      const label = tableLabels(restaurant, choice.ids);
      const name = element('span', {class: 'seating-name'}, choice.ids.length > 1 ? label : `Table ${label}`);
      if (choice.ids.length > 1) name.append(text('span', 'pair-badge', 'Together as one'));
      // Restaurant detail retains fixture capacities; the dated options are authoritative.
      const option = availability.slots.flatMap(slot => slot.available_options || []).find(option => option.table_ids.length === choice.ids.length && choice.ids.every(id => option.table_ids.includes(id)));
      const capacityLabel = option ? `Up to ${option.capacity} guests` : (choice.ids.length === 1 ? 'Single table' : 'Two tables together');
      const row = element('section', {class: 'seating-row'}, element('div', {class: 'seating-row-head'}, name, text('span', 'capacity', capacityLabel)));
      const times = element('div', {class: 'seat-times'});
      for (const slot of availability.slots) {
        const available = choice.ids.length === 1 ? slot.available_table_ids.includes(choice.ids[0]) : (slot.available_options || []).some(o => o.table_ids.length === choice.ids.length && choice.ids.every(id => o.table_ids.includes(id)));
        const time = slot.starts_at_local.slice(11, 16);
        const selected = selection && selection.restaurant.id === restaurant.id && selection.local === slot.starts_at_local && selection.ids.join('|') === choice.ids.join('|');
        const cell = element('button', {type: 'button', class: 'slot', 'data-testid': `slot-${choice.ids.join('+')}-${time}`, 'data-available': String(available), 'aria-disabled': String(!available), 'aria-pressed': String(Boolean(selected)), 'aria-label': `${label}, ${time}, ${available ? 'available' : 'unavailable'}`, onclick: () => {
          if (!available) return;
          if (!session) { hosts.feedback.replaceChildren(); notice(hosts.feedback, element('span', {}, 'Please ', element('a', {href: '/login'}, 'log in'), ' to reserve your table.'), 'auth-error'); return; }
          hosts.feedback.replaceChildren();
          selection = {restaurant, ids: [...choice.ids], local: slot.starts_at_local, party: String(query.party_size), pending: null, revision: 0, attempt: 0, hosts, user: session.user_id};
          renderResults(); renderBooking();
          if (window.innerWidth < 691) hosts.booking.scrollIntoView({behavior: 'smooth', block: 'start'});
        }}, time);
        times.append(cell);
      }
      row.append(times); grid.append(row);
    }
    hosts.results.append(grid);
  }
  function renderBookingPlaceholder(host) {
    host.replaceChildren(text('span', 'eyebrow', 'Your evening starts here'), text('h2', '', 'A place at the table.'), element('span', {class: 'table-symbol', 'aria-hidden': 'true'}, '✳'), text('p', '', 'Choose an available time and we’ll save a place for you and your favourite people.'), text('p', 'fine-print', 'Your table is reserved only after you receive a confirmation.'));
  }
  function newKey() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
  }
  function renderBooking() {
    const chosen = selection;
    const host = chosen.hosts.booking;
    const form = element('form', {'data-testid': 'booking-form'});
    const summary = element('div', {class: 'booking-summary', 'data-testid': 'booking-summary'}, text('strong', '', chosen.restaurant.name), element('br'), `Table ${tableLabels(chosen.restaurant, chosen.ids)}`, element('br'), `${chosen.local.slice(0, 10)} · ${chosen.local.slice(11)} (local time)`);
    const party = field('Number of guests', 'booking-party-size', {type: 'number', min: 1, step: 1, required: true, value: chosen.party});
    const submit = element('button', {class: 'primary', type: 'submit', 'data-testid': 'booking-submit'}, 'Reserve this table →');
    const feedback = element('div', {'aria-live': 'polite'});
    const neutralTerms = `Times are local to ${chosen.restaurant.timezone}. Cancellation terms are confirmed with your reservation.`;
    const fineprint = text('p', 'fine-print', neutralTerms);
    form.append(summary, party.node, submit);
    host.replaceChildren(text('span', 'eyebrow', 'One lovely evening'), text('h2', '', 'Make it a date.'), form, feedback, fineprint);
    party.input.addEventListener('input', () => { chosen.party = party.input.value; chosen.revision++; chosen.pending = null; feedback.replaceChildren(); fineprint.textContent = neutralTerms; submit.textContent = 'Reserve this table →'; });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!session || session.user_id !== chosen.user) { feedback.replaceChildren(); notice(feedback, 'Please log in before reserving this table.', 'booking-error'); return; }
      if (!chosen.pending) {
        const body = {restaurant_id: chosen.restaurant.id, ...(chosen.ids.length === 1 ? {table_id: chosen.ids[0]} : {table_ids: chosen.ids}), starts_at_local: chosen.local, party_size: Number(chosen.party)};
        chosen.pending = {body: JSON.stringify(body), key: newKey()};
      }
      const pending = chosen.pending;
      const revision = chosen.revision;
      const attempt = ++chosen.attempt;
      const isCurrent = () => selection === chosen && revision === chosen.revision && attempt === chosen.attempt;
      feedback.replaceChildren(); fineprint.textContent = neutralTerms; submit.disabled = true; submit.textContent = 'Reserving your table…';
      try {
        const reservation = await api('/reservations', {method: 'POST', headers: {'Idempotency-Key': pending.key}, body: pending.body});
        if (!isCurrent()) return;
        if (!reservation.reference) throw new Error('Missing confirmation');
        // The POST receipt stays immutable. Current seating is a separate, optional read.
        const showConfirmation = (details, current, note) => {
          const cutoff = details.accepted_terms?.cancellation_cutoff_minutes;
          fineprint.textContent = neutralTerms;
          if (Number.isInteger(cutoff) && cutoff >= 0) fineprint.textContent = `Times are local to ${chosen.restaurant.timezone}. Under ${current ? 'this reservation’s' : 'the original booking’s'} accepted terms, cancellation and changes close ${cutoff} minutes before its start.`;
          const labels = tableLabels(chosen.restaurant, tableIds(details));
          const cancelled = current && details.status === 'cancelled';
          const confirmation = element('section', {class: 'confirmation', 'data-testid': 'confirmation', role: 'status'}, text('span', 'eyebrow', current ? (cancelled ? 'Reservation cancelled' : '✓ Your table is reserved') : '✓ Original booking confirmed'), text('h3', '', cancelled ? 'Your plans have changed.' : 'See you at the table.'), text('p', '', 'Your confirmation reference'), element('strong', {class: 'confirmation-reference', 'data-testid': 'confirmation-reference'}, reservation.reference), element('p', {'data-testid': 'confirmation-details'}, `${current ? 'Current details' : 'Original booking details'} · ${chosen.restaurant.name} · ${labels} · ${details.starts_at_local}`), element('p', {'data-testid': 'confirmation-tables'}, `${current ? 'Your tables' : 'Original tables'}: ${labels}`), text('p', '', current ? `Current status: ${details.status}` : note), element('a', {href: `/lookup?reference=${encodeURIComponent(reservation.reference)}`}, 'View or manage reservation →'));
          feedback.replaceChildren(confirmation);
        };
        showConfirmation(reservation, false, 'Your booking succeeded. Checking current reservation details…');
        submit.textContent = 'Reservation confirmed · check again';
        submit.disabled = false;
        try {
          const current = await api(`/reservations/${encodeURIComponent(reservation.reference)}`);
          if (!isCurrent()) return;
          if (current.reference !== reservation.reference || !current.starts_at_local || !tableIds(current).length) throw new Error('Invalid current details');
          showConfirmation(current, true);
        } catch (_) {
          if (!isCurrent()) return;
          showConfirmation(reservation, false, 'Your booking succeeded, but current reservation details are unavailable. The original details above may have changed. Check again or open your reservation to refresh them.');
        }
      } catch (error) {
        if (!isCurrent()) return;
        if (error instanceof ApiError) {
          notice(feedback, error.code === 'table_unavailable' ? 'That table was just taken. We’ve refreshed the times below; your choices are still here so you can choose another table.' : error.message, 'booking-error');
          if (error.code === 'table_unavailable' && search) runSearch(search.query, chosen.hosts, true);
          submit.textContent = 'Try reservation again →';
        } else {
          notice(feedback, 'We couldn’t confirm the response. Your table may already be reserved. Retry without changing these details to safely recover your confirmation.', 'booking-uncertain', 'uncertain');
          submit.textContent = 'Retry confirmation →';
        }
      } finally {
        if (selection === chosen && attempt === chosen.attempt) {
          submit.disabled = false;
          if (revision !== chosen.revision) submit.textContent = 'Reserve this table →';
        }
      }
    });
  }

  function renderLookup() {
    document.title = 'Your reservation — Tablekeeper';
    const card = element('section', {class: 'form-card'}, text('h2', '', 'Find your reservation.'), text('p', '', 'Use the reference from your confirmation. Log in with the account you used to book.'));
    const form = element('form');
    const reference = field('Confirmation reference', 'lookup-reference-input', {required: true, autocomplete: 'off', placeholder: 'e.g. AB12CD', autocapitalize: 'characters'});
    reference.input.value = new URLSearchParams(location.search).get('reference') || '';
    const submit = element('button', {type: 'submit', class: 'primary', 'data-testid': 'lookup-submit'}, 'Find reservation →');
    const feedback = element('div', {'aria-live': 'polite'});
    const detail = element('div'); form.append(reference.node, submit); card.append(form, feedback, detail);
    main.append(element('div', {class: 'split-page'}, intro('The evening, all arranged', 'Plans worth\nkeeping.', 'Your reservation details, all in one place. Check your table or let the restaurant know your plans have changed.'), card));
    async function lookup() {
      const generation = ++lookupVersion;
      const page = routeVersion;
      feedback.replaceChildren(); detail.replaceChildren();
      if (!session) { notice(feedback, element('span', {}, 'Please ', element('a', {href: '/login'}, 'log in'), ' to view your reservation.'), 'reservation-error'); return; }
      const ref = reference.input.value.trim().toUpperCase();
      loading(detail, 'Finding your reservation…'); submit.disabled = true;
      try {
        const record = await api(`/reservations/${encodeURIComponent(ref)}`);
        const restaurant = await api(`/restaurants/${encodeURIComponent(record.restaurant_id)}`);
        if (page !== routeVersion || generation !== lookupVersion) return;
        showReservation(record, restaurant, detail, feedback, generation);
      } catch (error) {
        if (page !== routeVersion || generation !== lookupVersion) return;
        detail.replaceChildren();
        notice(feedback, error instanceof ApiError ? (error.status === 404 ? 'We couldn’t find that reservation for your account. Check the reference and try again.' : error.message) : 'We could not connect. Please try again.', 'reservation-error');
      } finally { submit.disabled = false; }
    }
    form.addEventListener('submit', event => { event.preventDefault(); lookup(); });
    if (reference.input.value && session) lookup();
  }
  function showReservation(record, restaurant, host, feedback, generation) {
    const detail = element('section', {class: 'reservation-card', 'data-testid': 'reservation-detail'});
    const status = element('span', {class: `status-pill ${record.status}`, 'data-testid': 'reservation-status'}, record.status);
    const labels = tableLabels(restaurant, tableIds(record));
    const list = element('dl', {class: 'detail-list'}, element('dt', {}, 'Reference'), element('dd', {}, record.reference), element('dt', {}, 'Tables'), element('dd', {'data-testid': 'reservation-tables'}, labels), element('dt', {}, 'Date & time'), element('dd', {}, record.starts_at_local.replace('T', ' · ')), element('dt', {}, 'Guests'), element('dd', {}, record.party_size));
    detail.append(status, text('h3', '', restaurant.name), list, text('p', 'fine-print', `Local time · ${restaurant.timezone}`));
    if (record.status !== 'cancelled') {
      const cancel = element('button', {type: 'button', class: 'secondary', 'data-testid': 'reservation-cancel-button'}, 'Cancel reservation');
      cancel.style.marginTop = '20px';
      cancel.addEventListener('click', async () => {
        const page = routeVersion; cancel.disabled = true; cancel.textContent = 'Cancelling…'; feedback.replaceChildren();
        try {
          const updated = await api(`/reservations/${encodeURIComponent(record.reference)}/cancel`, {method: 'POST', body: '{}'});
          if (page !== routeVersion || generation !== lookupVersion) return;
          showReservation(updated, restaurant, host, feedback, generation);
          notice(feedback, 'Your reservation is cancelled. We hope to see you another time.', null, 'success');
        } catch (error) {
          if (page === routeVersion && generation === lookupVersion) notice(feedback, error instanceof ApiError ? (error.code === 'cutoff_passed' ? 'This reservation is too close to its start time to cancel.' : error.message) : 'We could not confirm the cancellation. Look up the reservation again to check its status.', 'reservation-error');
        } finally { cancel.disabled = false; cancel.textContent = 'Cancel reservation'; }
      });
      detail.append(cancel);
    }
    host.replaceChildren(detail);
  }
  renderRoute();
})();
