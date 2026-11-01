import test, { after, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { homedir } from 'node:os';
import { join } from 'node:path';

// Use the host's existing harness, never install dependencies into the plugin.
const requireHost = createRequire(process.env.HERMES_DESKTOP_PACKAGE || join(process.env.HERMES_SOURCE || join(homedir(), '.hermes', 'hermes-agent'), 'apps', 'desktop', 'package.json'));
const React = requireHost('react');
const { JSDOM } = requireHost('jsdom');
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://desktop.test' });
for (const name of ['window', 'document', 'HTMLElement', 'HTMLDialogElement', 'MutationObserver']) globalThis[name] = dom.window[name];
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// jsdom does not implement the browser's modal top layer; test dialog contents and dismissal separately.
dom.window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
const { render, fireEvent, waitFor, cleanup, within } = requireHost('@testing-library/react');
const query = requireHost('@tanstack/react-query');
const atom = initial => { let value = initial; const listeners = new Set(); return { get: () => value, set: next => { value = next; for (const listener of listeners) listener(); }, subscribe: fn => { listeners.add(fn); return () => listeners.delete(fn); } }; };
let epoch = 1;
const host = { state: { connectionId: atom('local'), profile: atom('default'), focusedSessionOwner: atom(null), gateway: atom('open') }, composer: { insertText: async () => false } };
globalThis.__githubProjectsSDK = { ...query, host, gatewayActivationEpoch: () => epoch, useValue: a => React.useSyncExternalStore(a.subscribe, a.get), Button: props => React.createElement('button', { type: 'button', ...props }), Input: props => React.createElement('input', props), Textarea: props => React.createElement('textarea', props), ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'sidebarNav' };
const sdkNames = 'host,useValue,useQuery,useMutation,useQueryClient,gatewayActivationEpoch,Button,Input,Textarea,ROUTES_AREA,SIDEBAR_NAV_AREA';
const sdkURL = 'data:text/javascript;base64,' + Buffer.from(`export const {${sdkNames}} = globalThis.__githubProjectsSDK;`).toString('base64');
const source = await readFile(new URL('../desktop/plugin.js', import.meta.url), 'utf8');
const loadedSource = source.replace("'@hermes/plugin-sdk'", JSON.stringify(sdkURL)).replace("'react'", JSON.stringify(pathToFileURL(requireHost.resolve('react')).href)).replace("'react/jsx-runtime'", JSON.stringify(pathToFileURL(requireHost.resolve('react/jsx-runtime')).href));
const plugin = await import('data:text/javascript;base64,' + Buffer.from(loadedSource).toString('base64'));
const clients = [];
afterEach(() => { cleanup(); for (const client of clients.splice(0)) client.clear(); host.state.connectionId.set('local'); host.state.profile.set('default'); host.state.focusedSessionOwner.set(null); epoch = 1; });
after(() => dom.window.close());
const fixture = () => ({ project: { id: 'P1', title: 'Shipping', url: 'https://github.com/orgs/acme/projects/1' }, status_field: { id: 'S1', options: [{ id: 'todo', name: 'Todo' }, { id: 'done', name: 'Done' }] }, items: [
  { id: 'I1', kind: 'Issue', title: 'Fix login', body: 'Keep sessions safe', url: 'https://github.com/acme/app/issues/7', number: 7, repository: 'acme/app', status: null, updatedAt: 'v1', labels: ['security'], assignees: ['sam'] },
  { id: 'I2', kind: 'PullRequest', title: 'Review fix', body: '', url: 'https://github.com/acme/app/pull/8', number: 8, repository: 'acme/app', status: 'todo', labels: [], assignees: [] },
  { id: 'I3', kind: 'DraftIssue', title: 'Draft idea', body: '', url: null, number: null, repository: null, status: 'todo', labels: [], assignees: [] }
] });
const setup = ({ projectList, projectError } = {}) => {
  const board = fixture(); const calls = []; const opened = [];
  const issue = { title: 'Fix login', body: 'Keep sessions safe', updatedAt: 'v1', state: 'OPEN', labels: [{ name: 'security' }], assignees: [{ login: 'sam' }], comments: [] };
  const ctx = { os: { openExternal: async url => { opened.push(url); return true; }, writeClipboard: async () => true }, rest: async (path, options) => {
    assert.equal(path, '/call?profile=default'); assert.equal(options.method, 'POST'); const { operation, arguments: args } = options.body; calls.push({ operation, args });
    let data;
    if (operation === 'projects') {
      if (projectError) return { ok: false, error: projectError };
      data = { viewer: 'sam', projects: projectList || [{ number: 1, title: 'Shipping', owner: 'acme', url: board.project.url }, { number: 1, title: 'Personal tasks', owner: 'sam', url: 'https://github.com/users/sam/projects/1' }], warnings: [] };
    }
    else if (operation === 'board') data = structuredClone(board);
    else if (operation === 'issue') data = structuredClone(issue);
    else if (operation === 'move') { board.items.find(i => i.id === args.item_id).status = args.option_id; data = { status: args.option_id }; }
    else if (operation === 'update_issue') { Object.assign(issue, { title: args.title, body: args.body, labels: args.labels.map(name => ({ name })), assignees: args.assignees.map(login => ({ login })), updatedAt: 'v2' }); data = structuredClone(issue); }
    else if (operation === 'comment') { issue.comments.push({ id: 'C1', author: { login: 'sam' }, body: args.body }); data = { id: 'C1' }; }
    else if (operation === 'issue_state') { issue.state = args.state; issue.updatedAt = 'v3'; data = structuredClone(issue); }
    else if (operation === 'create_issue') data = { url: 'https://github.com/acme/app/issues/9' };
    else throw new Error(`Unexpected ${operation}`);
    return { ok: true, data };
  } };
  const client = new query.QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 } } });
  clients.push(client);
  const ui = render(React.createElement(query.QueryClientProvider, { client }, React.createElement(plugin.BoardPage, { ctx, scope: plugin.scopeKey() })));
  return { ...ui, ctx, calls, opened, board, issue };
};
const loadBoard = async ui => {
  fireEvent.click(await ui.findByRole('button', { name: 'Shipping acme · #1' })); await ui.findByText('Fix login');
  await waitFor(() => assert.equal(ui.getByRole('button', { name: 'Refresh board' }).disabled, false));
};

test('native contribution contract and scoped calls reject errors and late cross-host replies', async () => {
  const registered = []; plugin.default.register({ register: c => registered.push(c) });
  assert.equal(plugin.default.id, 'github-projects'); assert.equal(plugin.default.defaultEnabled, false);
  assert.deepEqual(registered.map(c => c.area), ['routes', 'sidebarNav']);
  await assert.rejects(plugin.call({ rest: async () => ({ ok: false, error: 'Missing project scope: full error' }) }, plugin.scopeKey(), 'board', {}), /Missing project scope: full error/);
  let resolve; const pending = plugin.call({ rest: () => new Promise(r => { resolve = r; }) }, plugin.scopeKey(), 'board', {});
  host.state.connectionId.set('remote'); resolve({ ok: true, data: fixture() }); await assert.rejects(pending, /changed while/);
  host.state.connectionId.set('local'); const scope = plugin.scopeKey(); epoch++;
  await assert.rejects(plugin.call({ rest: () => assert.fail('must not call new host') }, scope, 'move', {}), /changed/);
});

test('multiplexed gateway calls the focused profile, not the default socket owner', async () => {
  host.state.focusedSessionOwner.set({ connectionId: 'local', profile: '30walls' });
  const scope = plugin.scopeKey();
  assert.equal(scope[2], '30walls');
  let requested;
  await plugin.call({ rest: async path => { requested = path; return { ok: true, data: {} }; } }, scope, 'projects', {});
  assert.equal(requested, '/call?profile=30walls');
  host.state.focusedSessionOwner.set({ connectionId: 'remote', profile: 'private' });
  assert.notEqual(plugin.scopeKey()[2], 'private');
});

test('columns preserve native status order, no-status, unknown values and filter labels/assignees', () => {
  const board = fixture(); board.items.push({ ...board.items[0], id: 'I4', status: 'removed' });
  assert.deepEqual(plugin.columnsFor(board).map(c => c.id), [null, 'todo', 'done', 'removed']);
  assert.equal(plugin.columnsFor(board, 'SAM')[0].items[0].id, 'I1');
  assert.equal(plugin.columnsFor(board, 'security')[0].items.length, 1);
});

test('rendered board shows all kinds, moves via select and drag, searches and opens PR only', async () => {
  const ui = setup(); await loadBoard(ui);
  assert.ok(ui.getByText('No status (1)')); assert.ok(ui.getByText('Draft idea')); assert.ok(ui.getByText('Review fix'));
  assert.equal(ui.calls.some(c => ['move', 'update_issue'].includes(c.operation)), false);
  fireEvent.change(ui.getByLabelText('Status for Fix login'), { target: { value: 'done' } });
  await waitFor(() => assert.ok(ui.getByText('Done (1)')));
  assert.deepEqual(ui.calls.find(c => c.operation === 'move').args, { owner: 'acme', number: 1, item_id: 'I1', option_id: 'done', expected_status: null });
  await waitFor(() => assert.equal(ui.getByLabelText('Status for Fix login').disabled, false));
  fireEvent.drop(ui.getByRole('region', { name: 'No status' }), { dataTransfer: { getData: () => 'I1' } });
  assert.equal(ui.calls.filter(c => c.operation === 'move').length, 1);
  assert.equal(within(ui.getByLabelText('Status for Fix login')).getByText('No status').disabled, true);
  fireEvent.drop(ui.getByRole('region', { name: 'Todo' }), { dataTransfer: { getData: () => 'I1' } });
  await waitFor(() => assert.equal(ui.calls.filter(c => c.operation === 'move').length, 2));
  await waitFor(() => assert.equal(ui.getByLabelText('Status for Fix login').value, 'todo'));
  fireEvent.change(ui.getByLabelText('Search issues, labels, assignees'), { target: { value: 'nobody' } }); assert.ok(ui.getByText('No items match your search.'));
  fireEvent.change(ui.getByLabelText('Search issues, labels, assignees'), { target: { value: '' } });
  fireEvent.click(ui.getAllByText('Open on GitHub').find(button => !button.disabled)); await waitFor(() => assert.deepEqual(ui.opened, ['https://github.com/acme/app/pull/8']));
});

test('project browser auto-loads without writes, searches, refreshes and selects owner and number together', async () => {
  const ui = setup();
  assert.ok(ui.getByText('Loading projects…'));
  await ui.findByRole('button', { name: 'Shipping acme · #1' });
  assert.deepEqual(ui.calls, [{ operation: 'projects', args: {} }]);
  assert.equal(ui.getByText('Other owner').closest('details').open, false);
  fireEvent.change(ui.getByLabelText('Search projects'), { target: { value: 'missing' } });
  assert.ok(ui.getByText('No projects match your search.'));
  fireEvent.change(ui.getByLabelText('Search projects'), { target: { value: 'sam' } });
  assert.equal(ui.queryByRole('button', { name: 'Shipping acme · #1' }), null);
  fireEvent.click(ui.getByRole('button', { name: 'Personal tasks sam · #1' }));
  await ui.findByText('Fix login');
  assert.deepEqual(ui.calls.find(c => c.operation === 'board').args, { owner: 'sam', number: 1 });
  await waitFor(() => assert.equal(ui.getByText('Back to projects').disabled, false));
  fireEvent.click(ui.getByText('Back to projects'));
  fireEvent.change(ui.getByLabelText('Search projects'), { target: { value: '' } });
  fireEvent.click(ui.getByText('Refresh projects'));
  await waitFor(() => assert.equal(ui.calls.filter(c => c.operation === 'projects').length, 2));
  await waitFor(() => assert.equal(ui.getByText('Refresh projects').disabled, false));
  await loadBoard(ui);
  assert.deepEqual(ui.calls.filter(c => c.operation === 'board').at(-1).args, { owner: 'acme', number: 1 });
  assert.ok(ui.calls.every(c => ['projects', 'board'].includes(c.operation)));
});

test('project browser supports other owner and empty/error states', async () => {
  const ui = setup({ projectList: [] });
  await ui.findByText('No accessible projects found. Try another owner or check GitHub project access.');
  fireEvent.click(ui.getByText('Other owner'));
  fireEvent.change(ui.getByLabelText('GitHub owner or organization'), { target: { value: 'other' } });
  fireEvent.submit(ui.getByText('Load projects').closest('form'));
  await waitFor(() => assert.deepEqual(ui.calls.at(-1), { operation: 'projects', args: { owner: 'other' } }));
  await waitFor(() => assert.equal(ui.getByText('Refresh projects').disabled, false));
  fireEvent.click(ui.getByText('My projects'));
  await waitFor(() => assert.deepEqual(ui.calls.at(-1), { operation: 'projects', args: {} }));
  ui.unmount();
  const failed = setup({ projectError: 'GitHub denied project access' });
  await failed.findByRole('alert');
  assert.match(failed.getByRole('alert').textContent, /GitHub denied project access/);
});

test('rendered issue editor saves with concurrency token, posts, closes/reopens and never submits chat', async () => {
  const ui = setup(); await loadBoard(ui); fireEvent.click(ui.getByText('Edit issue'));
  const dialog = await ui.findByRole('dialog'); const editor = within(dialog); await editor.findByDisplayValue('Keep sessions safe');
  await waitFor(() => assert.equal(editor.getByText('Save issue').disabled, false));
  fireEvent.change(editor.getByLabelText('Title'), { target: { value: 'Fix login safely' } }); fireEvent.click(editor.getByText('Save issue'));
  await editor.findByText('Saved and refreshed from GitHub.'); assert.equal(ui.calls.find(c => c.operation === 'update_issue').args.expected_updated_at, 'v1');
  fireEvent.change(editor.getByLabelText('New comment (Markdown)'), { target: { value: 'Reviewed the fix' } }); fireEvent.click(editor.getByText('Post comment'));
  await editor.findByText('Reviewed the fix'); await waitFor(() => assert.equal(editor.getByText('Close issue').disabled, false));
  fireEvent.click(editor.getByText('Close issue')); await editor.findByText('Reopen issue');
  await waitFor(() => assert.equal(editor.getByText('Reopen issue').disabled, false)); fireEvent.click(editor.getByText('Reopen issue')); await editor.findByText('Close issue');
  await waitFor(() => assert.equal(editor.getByText('Work on this').disabled, false));
  let draft = 'Existing user draft'; host.composer.insertText = async (target, text, options) => { assert.equal(target, null); assert.equal(options.mode, 'block'); draft += '\n' + text; return true; };
  fireEvent.click(editor.getByText('Work on this')); await editor.findByText(/Appended to the focused chat draft/);
  assert.ok(draft.startsWith('Existing user draft\n')); assert.match(draft, /Fix login safely/); assert.match(draft, /Work only on this explicitly selected issue/);
  assert.equal(ui.calls.filter(c => c.operation === 'issue_state')[1].args.expected_updated_at, 'v3');
});

test('clipboard fallback reports paste guidance and unavailable clipboard fails honestly', async () => {
  host.composer.insertText = async () => false;
  let copied; const result = await plugin.prepareWork({ os: { writeClipboard: async text => { copied = text; return true; } } }, 'task');
  assert.equal(copied, 'task'); assert.match(result, /paste after any existing draft/);
  await assert.rejects(plugin.prepareWork({ os: { writeClipboard: async () => false } }, 'task'), /clipboard is unavailable/);
});

test('rendered create issue sends all explicit fields and refreshes before closing', async () => {
  const ui = setup(); await loadBoard(ui); fireEvent.click(ui.getByText('New issue'));
  fireEvent.change(ui.getByLabelText('Repository (owner/name)'), { target: { value: 'acme/app' } }); fireEvent.change(ui.getByLabelText('Title'), { target: { value: 'New task' } });
  fireEvent.submit(ui.getByText('Create issue').closest('form')); await waitFor(() => assert.equal(ui.queryByText('Create GitHub issue and add to project') === null, true));
  assert.deepEqual(ui.calls.find(c => c.operation === 'create_issue').args, { repo: 'acme/app', title: 'New task', body: '', labels: [], assignees: [], owner: 'acme', project_number: 1 });
  assert.equal(ui.calls.at(-1).operation, 'board');
});

test('rendered empty and backend failure states retain full error', async () => {
  const ui = setup(); ui.board.items.length = 0; await loadBoard({ ...ui, findByText: async text => text === 'Fix login' ? null : ui.findByText(text) });
  assert.ok(ui.getByText('This project has no items. Create an issue or add items on GitHub.'));
  ui.ctx.rest = async () => ({ ok: false, error: 'GitHub denied access\nCheck projects scope and organization authorization.' });
  fireEvent.click(ui.getByRole('button', { name: 'Refresh board' }));
  await waitFor(() => assert.match(ui.getByRole('alert').textContent, /GitHub denied access\nCheck projects scope/));
});
