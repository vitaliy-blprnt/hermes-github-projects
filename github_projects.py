"""Stateless GitHub service. All requests use the gateway's inherited gh identity.

Optimistic guards are read-before-write checks, not atomic GitHub preconditions.
A write is never retried: errors after submission require reconciliation.
"""

import json
import re
import subprocess


class GitHubError(Exception):
    """Validation, GitHub, concurrency, or verification failure."""


MAX_PAGES = 1000
PAGE_INFO = 'pageInfo { hasNextPage endCursor }'
OWNER_FRAGMENTS = '... on User { %s } ... on Organization { %s }'


def _request(endpoint, method='GET', payload=None, write=False):
    command = ['gh', 'api', endpoint, '--method', method]
    if payload is not None:
        command += ['--input', '-']
    try:
        result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise GitHubError('gh failed: ' + (result.stderr.strip() or str(result.returncode)))
        value = json.loads(result.stdout)
        if isinstance(value, dict) and value.get('errors'):
            raise GitHubError('GitHub GraphQL errors: ' + json.dumps(value['errors']))
        return value
    except (OSError, subprocess.SubprocessError, ValueError, GitHubError) as error:
        suffix = '; write outcome uncertain: reconcile with GitHub before retrying' if write else ''
        raise GitHubError(str(error) + suffix) from error


def _graphql(query, variables, write=False):
    response = _request('graphql', 'POST', {'query': query, 'variables': variables}, write)
    if not isinstance(response, dict) or not isinstance(response.get('data'), dict):
        raise GitHubError('Missing GraphQL data')
    return response['data']


def _pages(fetch):
    cursor, seen = None, set()
    for _ in range(MAX_PAGES):
        connection = fetch(cursor)
        if not isinstance(connection, dict) or not isinstance(connection.get('nodes'), list):
            raise GitHubError('Malformed GitHub connection')
        yield from connection['nodes']
        info = connection.get('pageInfo', {})
        if not isinstance(info.get('hasNextPage'), bool):
            raise GitHubError('Missing pagination information')
        if not info['hasNextPage']:
            return
        cursor = info.get('endCursor')
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            raise GitHubError('GitHub pagination cursor did not advance')
        seen.add(cursor)
    raise GitHubError('GitHub pagination limit exceeded; results not returned')


def _rest_pages(endpoint):
    values = []
    for page in range(1, MAX_PAGES + 1):
        batch = _request(f'{endpoint}?per_page=100&page={page}')
        if not isinstance(batch, list):
            raise GitHubError('Malformed GitHub list')
        if len(batch) > 100:
            raise GitHubError('Unexpected GitHub page size')
        if batch and values and batch == values[-len(batch):]:
            raise GitHubError('GitHub pagination repeated a page')
        values.extend(batch)
        if len(batch) < 100:
            return values
    raise GitHubError('GitHub pagination limit exceeded; results not returned')


def _text(value, name, empty=False):
    if not isinstance(value, str) or ('\x00' in value) or (not empty and not value.strip()):
        raise GitHubError(f'{name} must be a {"possibly empty " if empty else "nonempty "}string')
    return value


def _positive(value, name):
    if type(value) is not int or value <= 0:
        raise GitHubError(f'{name} must be a positive integer')
    return value


def _owner(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})', value):
        raise GitHubError('Invalid owner')
    return value


def _repo(value):
    if not isinstance(value, str) or value.count('/') != 1:
        raise GitHubError('repo must be owner/name')
    owner, name = value.split('/')
    _owner(owner)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or name in ('.', '..'):
        raise GitHubError('Invalid repository name')
    return value


def _strings(value, name):
    if not isinstance(value, list):
        raise GitHubError(f'{name} must be an array of strings')
    for item in value:
        _text(item, name)
    if len(set(value)) != len(value):
        raise GitHubError(f'{name} must not contain duplicates')
    return value


def _owner_id(owner):
    result = _request('users/' + owner)
    if not isinstance(result, dict) or not result.get('node_id'):
        raise GitHubError('GitHub owner not found')
    return result['node_id']


def _projects(owner):
    owner_id = _owner_id(owner)
    selection = 'projectsV2(first:100, after:$cursor) { nodes { number title url } ' + PAGE_INFO + ' }'
    query = 'query($id:ID!, $cursor:String) { node(id:$id) { ' + OWNER_FRAGMENTS % (selection, selection) + ' } }'
    def fetch(cursor):
        node = _graphql(query, {'id': owner_id, 'cursor': cursor}).get('node')
        return node.get('projectsV2') if node else None
    return {'projects': [dict(project, owner=owner) for project in _pages(fetch)]}


def _discover_projects():
    viewer = _owner(_request('user')['login'])
    projects = _projects(viewer)['projects']
    warnings = []
    try:
        organizations = _rest_pages('user/orgs')
    except GitHubError as error:
        organizations = []
        warnings.append(f'Organization discovery incomplete: {error}')
    for organization in organizations:
        owner = _owner(organization['login'])
        try:
            projects.extend(_projects(owner)['projects'])
        except GitHubError as error:
            warnings.append(f'Projects for {owner} could not be loaded: {error}')
    return {'viewer': viewer, 'projects': projects, 'warnings': warnings}


def _project(owner, number):
    selection = 'projectV2(number:$number) { id title url }'
    query = 'query($id:ID!, $number:Int!) { node(id:$id) { ' + OWNER_FRAGMENTS % (selection, selection) + ' } }'
    node = _graphql(query, {'id': _owner_id(owner), 'number': number}).get('node')
    if not node or not node.get('projectV2'):
        raise GitHubError('Project not found or not accessible')
    return node['projectV2']


def _project_connection(project_id, field, selection):
    query = ('query($id:ID!, $cursor:String) { node(id:$id) { ... on ProjectV2 { '
             + field + '(first:100, after:$cursor) { nodes { ' + selection + ' } ' + PAGE_INFO + ' } } } }')
    def fetch(cursor):
        node = _graphql(query, {'id': project_id, 'cursor': cursor}).get('node')
        return node.get(field) if node else None
    return list(_pages(fetch))


def _people_or_labels(content, field, fragment):
    first = content[field]
    selection = 'name' if field == 'labels' else 'login'
    query = ('query($id:ID!, $cursor:String) { node(id:$id) { ... on ' + fragment + ' { '
             + field + '(first:100, after:$cursor) { nodes { ' + selection + ' } ' + PAGE_INFO + ' } } } }')
    def fetch(cursor):
        if cursor is None:
            return first
        node = _graphql(query, {'id': content['id'], 'cursor': cursor}).get('node')
        return node.get(field) if node else None
    return [node[selection] for node in _pages(fetch)]


def _board(owner, number):
    project = _project(owner, number)
    fields = _project_connection(project['id'], 'fields',
        '__typename ... on ProjectV2Field { id name } ... on ProjectV2IterationField { id name } '
        '... on ProjectV2SingleSelectField { id name options { id name } }')
    statuses = [field for field in fields if field.get('name') == 'Status' and field.get('__typename') == 'ProjectV2SingleSelectField']
    if len(statuses) != 1:
        raise GitHubError('Project must have exactly one Status single-select field')
    status = {'id': statuses[0]['id'], 'options': statuses[0]['options']}
    people = 'assignees(first:100) { nodes { login } ' + PAGE_INFO + ' }'
    labels = 'labels(first:100) { nodes { name } ' + PAGE_INFO + ' }'
    common = 'id title body url number updatedAt repository { nameWithOwner } ' + labels + ' ' + people
    selection = ('id updatedAt fieldValueByName(name:"Status") { ... on ProjectV2ItemFieldSingleSelectValue { optionId } } '
                 'content { __typename ... on Issue { ' + common + ' } ... on PullRequest { ' + common + ' } '
                 '... on DraftIssue { id title body updatedAt ' + people + ' } }')
    items = []
    for item in _project_connection(project['id'], 'items', selection):
        content = item.get('content')
        if not content:
            raise GitHubError('Project contains inaccessible or redacted content; refusing partial board')
        kind = content['__typename']
        if kind not in ('Issue', 'PullRequest', 'DraftIssue'):
            raise GitHubError('Unsupported project item kind')
        value = item.get('fieldValueByName')
        items.append({'id': item['id'], 'kind': kind, 'title': content['title'], 'body': content.get('body') or '',
                      'url': content.get('url'), 'number': content.get('number'),
                      'repository': (content.get('repository') or {}).get('nameWithOwner'),
                      'status': value.get('optionId') if value else None,
                      'updatedAt': content['updatedAt'],
                      'labels': _people_or_labels(content, 'labels', kind) if kind != 'DraftIssue' else [],
                      'assignees': _people_or_labels(content, 'assignees', kind)})
    return {'project': project, 'status_field': status, 'items': items}


def _issue(repo, number):
    base = f'repos/{repo}/issues/{number}'
    issue = _request(base)
    if not isinstance(issue, dict) or not issue.get('node_id'):
        raise GitHubError('Issue not found')
    if 'pull_request' in issue:
        raise GitHubError('Expected an issue, not a pull request')
    def person(value):
        return {'login': value['login'], 'id': value.get('node_id'), 'url': value.get('html_url')}
    comments = _rest_pages(base + '/comments')
    return {'id': issue['node_id'], 'number': issue['number'], 'title': issue['title'], 'body': issue.get('body') or '',
            'url': issue['html_url'], 'state': issue['state'].upper(), 'createdAt': issue['created_at'],
            'updatedAt': issue['updated_at'], 'closedAt': issue.get('closed_at'), 'author': person(issue['user']),
            'repository': {'nameWithOwner': repo}, 'labels': [{'name': label['name'], 'id': label.get('node_id'),
            'color': label.get('color'), 'description': label.get('description')} for label in issue.get('labels', [])],
            'assignees': [person(user) for user in issue.get('assignees', [])],
            'comments': [{'id': comment['node_id'], 'body': comment['body'], 'url': comment['html_url'],
                          'createdAt': comment['created_at'], 'updatedAt': comment['updated_at'],
                          'author': person(comment['user'])} for comment in comments]}


def _verify_issue(issue, changes):
    for key, expected in changes.items():
        actual = issue[key]
        if key in ('labels', 'assignees'):
            actual = sorted(item['name' if key == 'labels' else 'login'].casefold() for item in actual)
            expected = sorted(item.casefold() for item in expected)
        if actual != expected:
            raise GitHubError('Write readback mismatch for ' + key)
    return issue


def _write_action(action):
    try:
        return action()
    except (GitHubError, KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        raise GitHubError(str(error) + '; reconcile with GitHub before retrying; no automatic retry performed') from error


def _change_issue(repo, number, changes, expected):
    before = _issue(repo, number)
    if before['updatedAt'] != expected:
        raise GitHubError('Stale issue: updatedAt differs; refresh before editing')
    def write():
        payload = {key: value.lower() if key == 'state' else value for key, value in changes.items()}
        _request(f'repos/{repo}/issues/{number}', 'PATCH', payload, write=True)
        return _verify_issue(_issue(repo, number), changes)
    return _write_action(write)


def _create(repo, title, body, labels, assignees, owner, number):
    board = _board(owner, number)
    def write():
        created = _request(f'repos/{repo}/issues', 'POST',
                           {'title': title, 'body': body, 'labels': labels, 'assignees': assignees}, write=True)
        try:
            data = _graphql('mutation($project:ID!, $content:ID!) { addProjectV2ItemById(input:{projectId:$project, contentId:$content}) { item { id } } }',
                            {'project': board['project']['id'], 'content': created['node_id']}, write=True)
            item_id = data['addProjectV2ItemById']['item']['id']
            issue = _verify_issue(_issue(repo, created['number']), {'title': title, 'body': body, 'labels': labels, 'assignees': assignees})
            fresh = _board(owner, number)
            item = next((item for item in fresh['items'] if item['id'] == item_id), None)
            if not item or item['number'] != issue['number'] or item['repository'].casefold() != repo.casefold():
                raise GitHubError('Created issue project membership not verified')
            return {'issue': issue, 'item': item}
        except (GitHubError, KeyError, TypeError, ValueError, AttributeError) as error:
            target = created.get('html_url') or f'{repo}#{created.get("number", "unknown")}'
            raise GitHubError(f'Issue created at {target}, but project attachment or readback failed: {error}. Do not create a duplicate.') from error
    return _write_action(write)


def _comment(repo, number, body):
    _issue(repo, number)
    def write():
        created = _request(f'repos/{repo}/issues/{number}/comments', 'POST', {'body': body}, write=True)
        comment = _request(f'repos/{repo}/issues/comments/{_positive(created["id"], "comment id")}')
        if comment.get('body') != body or comment.get('id') != created['id']:
            raise GitHubError('Comment readback mismatch')
        return {'comment': comment}
    return _write_action(write)


def _move(owner, number, item_id, option_id, expected):
    board = _board(owner, number)
    item = next((item for item in board['items'] if item['id'] == item_id), None)
    if item is None:
        raise GitHubError('Item is not a member of this project')
    if option_id not in {option['id'] for option in board['status_field']['options']}:
        raise GitHubError('Unknown Status option')
    if item['status'] != expected:
        raise GitHubError('Stale item: status differs; refresh before moving')
    def write():
        _graphql('mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) { updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:{singleSelectOptionId:$option}}) { projectV2Item { id } } }',
                 {'project': board['project']['id'], 'item': item_id, 'field': board['status_field']['id'], 'option': option_id}, write=True)
        fresh = _board(owner, number)
        found = next((entry for entry in fresh['items'] if entry['id'] == item_id), None)
        if not found or found['status'] != option_id:
            raise GitHubError('Status write readback mismatch')
        return {'item': found}
    return _write_action(write)


def execute(operation: str, arguments: dict) -> dict:
    """Execute one allowlisted operation or raise GitHubError.

    Reads return {projects}, the board contract, or an issue object respectively.
    update_issue/issue_state return the issue; create_issue returns {issue, item};
    comment returns {comment}; move returns {item}. Item kinds are the GraphQL
    names Issue, PullRequest, DraftIssue. Draft URL/number/repository are null.
    """
    schemas = {
        'projects': (set(), {'owner'}), 'board': ({'owner', 'number'}, set()),
        'issue': ({'repo', 'number'}, set()),
        'create_issue': ({'repo', 'title', 'body', 'owner', 'project_number'}, {'labels', 'assignees'}),
        'update_issue': ({'repo', 'number', 'expected_updated_at'}, {'title', 'body', 'labels', 'assignees'}),
        'comment': ({'repo', 'number', 'body'}, set()),
        'issue_state': ({'repo', 'number', 'state', 'expected_updated_at'}, set()),
        'move': ({'owner', 'number', 'item_id', 'option_id', 'expected_status'}, set()),
    }
    if not isinstance(operation, str) or operation not in schemas:
        raise GitHubError('Unsupported operation')
    if not isinstance(arguments, dict) or any(not isinstance(key, str) for key in arguments):
        raise GitHubError('arguments must be an object')
    required, optional = schemas[operation]
    if required - arguments.keys() or arguments.keys() - required - optional:
        raise GitHubError('Missing or unknown arguments for ' + operation)
    args = dict(arguments)
    for name, value in args.items():
        if name == 'owner':
            _owner(value)
        elif name == 'repo':
            _repo(value)
        elif name in ('number', 'project_number'):
            _positive(value, name)
        elif name in ('labels', 'assignees'):
            _strings(value, name)
        elif name == 'expected_status' and value is None:
            pass
        else:
            _text(value, name, empty=(name == 'body' and operation != 'comment'))
    if operation == 'issue_state' and args['state'] not in ('OPEN', 'CLOSED'):
        raise GitHubError('state must be OPEN or CLOSED')
    try:
        if operation == 'projects':
            return _projects(args['owner']) if 'owner' in args else _discover_projects()
        if operation == 'board':
            return _board(args['owner'], args['number'])
        if operation == 'issue':
            return _issue(args['repo'], args['number'])
        if operation == 'create_issue':
            return _create(args['repo'], args['title'], args['body'], args.get('labels', []), args.get('assignees', []), args['owner'], args['project_number'])
        if operation == 'comment':
            return _comment(args['repo'], args['number'], args['body'])
        if operation in ('update_issue', 'issue_state'):
            changes = {key: value for key, value in args.items() if key in ('title', 'body', 'labels', 'assignees', 'state')}
            if not changes:
                raise GitHubError('At least one issue change is required')
            return _change_issue(args['repo'], args['number'], changes, args['expected_updated_at'])
        return _move(args['owner'], args['number'], args['item_id'], args['option_id'], args['expected_status'])
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise GitHubError('Malformed GitHub response: ' + str(error)) from error
