import { test as base, expect } from '@playwright/test';

const test = base.extend({
  page: async ({ page }, runTest) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await runTest(page);
    expect(errors).toEqual([]);
  },
});
const docId = '10000000-0000-4000-8000-000000000001';
const convId = '20000000-0000-4000-8000-000000000001';
const source = { document_id: docId, chunk_index: 0, filename: 'launch.txt', page_number: null };
const doc = { id: docId, filename: 'launch.txt', status: 'ready', file_size: 35, total_chunks: 1 };
const conv = { id: convId, title: 'Launch details', created_at: '2026-09-14T10:00:00', updated_at: '2026-09-14T10:00:00' };

async function mockApi(page, { signedIn = true, messages = [] } = {}) {
  const state = { signedIn, messages, sent: null };
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (path === '/api/auth/me') return state.signedIn ? reply({ email: 'review@example.com', csrf_token: 'test-csrf' }) : reply({ detail: 'Please sign in.' }, 401);
    if (path === '/api/auth/login') { state.signedIn = true; return reply({ email: 'review@example.com', csrf_token: 'test-csrf' }); }
    if (path === '/api/auth/logout') { state.signedIn = false; return route.fulfill({ status: 204 }); }
    if (path === '/api/documents/') return reply({ documents: [doc], has_more: false });
    if (path.endsWith('/chunks')) return reply([{ ...source, content: 'The launch date is 14 September 2026.' }]);
    if (path === '/api/chat/') return reply([conv]);
    if (path.endsWith('/message')) {
      state.sent = request.postDataJSON();
      expect(request.headers()['x-csrf-token']).toBe('test-csrf');
      expect(request.headers()['x-requested-with']).toBe('DocMind');
      state.messages = [{ id: 'message-1', role: 'assistant', content: 'The launch is on 14 September 2026.', sources: [source], created_at: '2026-09-14T10:00:00' }];
      return reply(state.messages[0]);
    }
    if (path.endsWith('/history')) return reply({ ...conv, messages: state.messages, has_more: false });
    return reply({ detail: 'Unhandled mock route' }, 404);
  });
  return state;
}

test('sign in and sign out without persistent browser credentials', async ({ page }) => {
  await mockApi(page, { signedIn: false });
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill('review@example.com');
  await page.getByLabel('Password', { exact: true }).fill('review-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Chat Workspace' })).toBeVisible();
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
});

test('blank summary submits mode and selected document and opens real source text', async ({ page }) => {
  const state = await mockApi(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Chat Workspace' })).toBeVisible();
  await page.getByLabel('Mode:').selectOption('summary');
  await page.locator('summary').click();
  await page.getByRole('checkbox', { name: 'launch.txt' }).check();
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('The launch is on 14 September 2026.', { exact: true })).toBeVisible();
  expect(state.sent.query_mode).toBe('summary');
  expect(state.sent.content).toBe('');
  expect(state.sent.document_ids).toEqual([docId]);
  expect(state.sent.request_id).toMatch(/^[0-9a-f-]{36}$/);
  await page.getByRole('button', { name: 'launch.txt (Chunk 1)' }).click();
  await expect(page.getByText('The launch date is 14 September 2026.', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/workspace.png', fullPage: true });
});

test('summary selection errors are visible and mobile layout stays within viewport', async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByLabel('Mode:').selectOption('summary');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('alert')).toContainText('Select exactly one ready document');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
