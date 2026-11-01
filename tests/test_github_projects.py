"""Service tests: the gh subprocess is mocked; fixtures contain only invented data."""

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import github_projects as service


def reply(value):
    return subprocess.CompletedProcess([], 0, json.dumps(value), '')


def connection(nodes, more=False, cursor=None):
    return {'nodes': nodes, 'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}


def graph_node(value):
    return reply({'data': {'node': value}})


def issue_fixture(**changes):
    value = {'id': 42, 'node_id': 'ISSUE', 'number': 7, 'title': 'Example issue', 'body': 'Example body',
             'html_url': 'https://github.com/example/demo/issues/7', 'state': 'open',
             'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z',
             'closed_at': None, 'user': {'login': 'example-user', 'node_id': 'USER'},
             'labels': [{'name': 'bug'}], 'assignees': [{'login': 'example-user'}]}
    value.update(changes)
    return value


def item_fixture(kind='Issue', status='todo'):
    content = {'id': 'ISSUE', '__typename': kind, 'title': 'Example issue', 'body': 'Example body',
               'url': 'https://github.com/example/demo/issues/7', 'number': 7,
               'repository': {'nameWithOwner': 'example/demo'}, 'updatedAt': '2026-01-01T00:00:00Z',
               'labels': connection([{'name': 'bug'}]), 'assignees': connection([{'login': 'example-user'}])}
    if kind == 'DraftIssue':
        for key in ('url', 'number', 'repository', 'labels'):
            del content[key]
    return {'id': 'ITEM', 'updatedAt': '2026-01-01T00:00:00Z', 'content': content,
            'fieldValueByName': {'optionId': status} if status else None}


def board_replies(items=None, fields=None):
    if fields is None:
        fields = [{'__typename': 'ProjectV2SingleSelectField', 'name': 'Status', 'id': 'FIELD',
                   'options': [{'id': 'todo', 'name': 'Todo'}, {'id': 'done', 'name': 'Done'}]}]
    return [reply({'node_id': 'OWNER'}),
            graph_node({'projectV2': {'id': 'PROJECT', 'title': 'Example board', 'url': 'https://example.test/project'}}),
            graph_node({'fields': connection(fields)}), graph_node({'items': connection(items if items is not None else [item_fixture()])})]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        patcher = patch('github_projects.subprocess.run')
        self.gh = patcher.start()
        self.addCleanup(patcher.stop)

    def queue(self, *values):
        self.gh.side_effect = values

    def issue_queue(self, before=None, after=None):
        values = [reply(before or issue_fixture()), reply([])]
        if after is not None:
            values.extend([reply({}), reply(after), reply([])])
        self.queue(*values)

    def payload(self, index=-1):
        return json.loads(self.gh.call_args_list[index].kwargs['input'])

    def test_default_projects_discover_viewer_and_organizations(self):
        self.queue(reply({'login': 'example'}), reply([{'login': 'team'}]))
        with patch.object(service, '_projects', side_effect=lambda owner: {'projects': [{'owner': owner, 'number': 1, 'title': owner, 'url': 'https://github.com'}]}):
            result = service.execute('projects', {})
        self.assertEqual(result['viewer'], 'example')
        self.assertEqual([p['owner'] for p in result['projects']], ['example', 'team'])
        self.assertEqual(result['warnings'], [])

    def test_default_projects_retains_own_list_when_org_discovery_denied(self):
        self.queue(reply({'login': 'example'}), subprocess.CompletedProcess([], 1, '', 'organization access denied'))
        with patch.object(service, '_projects', return_value={'projects': [{'owner': 'example', 'number': 1}]}):
            result = service.execute('projects', {})
        self.assertEqual(len(result['projects']), 1)
        self.assertIn('organization access denied', result['warnings'][0])

    def test_import_by_path_without_package_registration(self):
        spec = importlib.util.spec_from_file_location('standalone_plugin', Path(service.__file__))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(module.GitHubError):
            module.execute('unknown', {})

    def test_unknown_operation(self):
        for operation in ('delete_everything', None, []):
            with self.subTest(operation=operation), self.assertRaises(service.GitHubError):
                service.execute(operation, {})
        self.gh.assert_not_called()

    def test_input_validation_before_subprocess(self):
        cases = [('projects', {'owner': '../bad'}), ('projects', {'owner': 'example', 'extra': 1}),
                 ('issue', {'repo': 'example/demo', 'number': True}),
                 ('issue', {'repo': 'example/../demo', 'number': 1}),
                 ('issue', {'repo': 'example/demo', 'number': 0}),
                 ('update_issue', {'repo': 'example/demo', 'number': 7, 'title': 'New'}),
                 ('update_issue', {'repo': 'example/demo', 'number': 7, 'expected_updated_at': 'x'}),
                 ('update_issue', {'repo': 'example/demo', 'number': 7, 'labels': 'bug', 'expected_updated_at': 'x'}),
                 ('update_issue', {'repo': 'example/demo', 'number': 7, 'labels': ['bug', 'bug'], 'expected_updated_at': 'x'}),
                 ('comment', {'repo': 'example/demo', 'number': 7, 'body': ''}),
                 ('issue_state', {'repo': 'example/demo', 'number': 7, 'state': 'deleted', 'expected_updated_at': 'x'}),
                 ('move', {'owner': 'example', 'number': 1, 'item_id': 'ITEM', 'option_id': 'done'}),
                 ('move', {'owner': 'example', 'number': 1, 'item_id': 'ITEM', 'option_id': 'done', 'expected_status': 1}),
                 ('projects', []), ('projects', {1: 'example'})]
        for operation, arguments in cases:
            with self.subTest(operation=operation, arguments=arguments), self.assertRaises(service.GitHubError):
                service.execute(operation, arguments)
        self.gh.assert_not_called()

    def test_projects_paginate(self):
        self.queue(reply({'node_id': 'OWNER'}),
                   graph_node({'projectsV2': connection([{'number': 1, 'title': 'One', 'url': 'https://example.test/1'}], True, 'next')}),
                   graph_node({'projectsV2': connection([{'number': 2, 'title': 'Two', 'url': 'https://example.test/2'}])}))
        result = service.execute('projects', {'owner': 'example'})
        self.assertEqual([p['number'] for p in result['projects']], [1, 2])
        self.assertEqual(result['projects'][0]['owner'], 'example')
        self.assertEqual(self.payload()['variables']['cursor'], 'next')
        self.assertNotIn('shell', self.gh.call_args.kwargs)
        self.assertEqual(self.gh.call_args.args[0][0:3], ['gh', 'api', 'graphql'])
        self.assertNotIn('env', self.gh.call_args.kwargs)

    def test_graphql_errors_even_with_data_and_successful_exit(self):
        self.queue(reply({'node_id': 'OWNER'}), reply({'data': {'node': {}}, 'errors': [{'message': 'Not allowed'}]}))
        with self.assertRaisesRegex(service.GitHubError, 'GraphQL errors'):
            service.execute('projects', {'owner': 'example'})

    def test_process_and_json_errors(self):
        for response in (subprocess.CompletedProcess([], 1, '', 'denied'),
                         subprocess.CompletedProcess([], 0, 'not json', ''),
                         subprocess.TimeoutExpired('gh', 60), FileNotFoundError('gh not installed')):
            with self.subTest(response=response):
                self.queue(response)
                with self.assertRaises(service.GitHubError):
                    service.execute('projects', {'owner': 'example'})

    def test_graphql_pagination_loop_and_missing_cursor(self):
        for cursor in (None, 'same'):
            self.queue(reply({'node_id': 'OWNER'}),
                       graph_node({'projectsV2': connection([], True, cursor)}),
                       graph_node({'projectsV2': connection([], True, cursor)}))
            with self.assertRaisesRegex(service.GitHubError, 'cursor'):
                service.execute('projects', {'owner': 'example'})

    def test_pagination_cap_is_an_error(self):
        self.queue(reply({'node_id': 'OWNER'}), graph_node({'projectsV2': connection([], True, 'a')}))
        with patch.object(service, 'MAX_PAGES', 1), self.assertRaisesRegex(service.GitHubError, 'limit'):
            service.execute('projects', {'owner': 'example'})

    def test_board_normalizes_issue_pull_request_and_draft(self):
        self.queue(*board_replies([item_fixture(), item_fixture('PullRequest'), item_fixture('DraftIssue', None)]))
        board = service.execute('board', {'owner': 'example', 'number': 1})
        self.assertEqual(board['status_field']['id'], 'FIELD')
        self.assertEqual([item['kind'] for item in board['items']], ['Issue', 'PullRequest', 'DraftIssue'])
        item = board['items'][0]
        self.assertEqual(set(item), {'id', 'kind', 'title', 'body', 'url', 'number', 'repository', 'status', 'updatedAt', 'labels', 'assignees'})
        self.assertEqual(item['labels'], ['bug'])
        self.assertEqual(item['assignees'], ['example-user'])
        self.assertIsNone(board['items'][2]['number'])
        self.assertIsNone(board['items'][2]['status'])
        self.assertEqual(board['items'][2]['labels'], [])

    def test_board_paginates_fields_items_and_nested_connections(self):
        first = item_fixture()
        first['content']['labels'] = connection([{'name': 'bug'}], True, 'labels-next')
        first['content']['assignees'] = connection([{'login': 'example-user'}], True, 'users-next')
        sequence = board_replies([first])
        field = sequence[2]
        self.queue(sequence[0], sequence[1], graph_node({'fields': connection([], True, 'fields-next')}), field,
                   graph_node({'items': connection([first], True, 'items-next')}), graph_node({'items': connection([item_fixture('DraftIssue')])}),
                   graph_node({'labels': connection([{'name': 'help'}])}), graph_node({'assignees': connection([{'login': 'another-user'}])}))
        board = service.execute('board', {'owner': 'example', 'number': 1})
        self.assertEqual(len(board['items']), 2)
        self.assertEqual(board['items'][0]['labels'], ['bug', 'help'])
        self.assertEqual(board['items'][0]['assignees'], ['example-user', 'another-user'])
        self.assertEqual(self.payload()['variables']['cursor'], 'users-next')

    def test_inaccessible_project_or_content_fails_explicitly(self):
        self.queue(reply({'node_id': 'OWNER'}), graph_node({'projectV2': None}))
        with self.assertRaisesRegex(service.GitHubError, 'not found'):
            service.execute('board', {'owner': 'example', 'number': 1})
        self.queue(*board_replies([{'id': 'ITEM', 'content': None}]))
        with self.assertRaisesRegex(service.GitHubError, 'partial board'):
            service.execute('board', {'owner': 'example', 'number': 1})
        self.queue(*board_replies(fields=[]))
        with self.assertRaisesRegex(service.GitHubError, 'Status'):
            service.execute('board', {'owner': 'example', 'number': 1})

    def test_issue_with_all_comment_pages(self):
        comment = {'id': 1, 'node_id': 'COMMENT', 'body': 'Example comment', 'html_url': 'https://example.test/comment',
                   'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z', 'user': {'login': 'example-user'}}
        self.queue(reply(issue_fixture()), reply([dict(comment, id=i, node_id=f'C{i}') for i in range(100)]), reply([comment]))
        issue = service.execute('issue', {'repo': 'example/demo', 'number': 7})
        self.assertEqual(len(issue['comments']), 101)
        self.assertEqual(issue['updatedAt'], '2026-01-01T00:00:00Z')
        self.assertEqual(issue['state'], 'OPEN')
        self.assertIn('page=2', self.gh.call_args.args[0][2])

    def test_issue_rejects_pull_request(self):
        self.queue(reply(issue_fixture(pull_request={})))
        with self.assertRaisesRegex(service.GitHubError, 'pull request'):
            service.execute('issue', {'repo': 'example/demo', 'number': 7})

    def test_stale_issue_rejected_without_write(self):
        self.issue_queue()
        with self.assertRaisesRegex(service.GitHubError, 'Stale'):
            service.execute('update_issue', {'repo': 'example/demo', 'number': 7, 'title': 'New', 'expected_updated_at': 'old'})
        self.assertEqual(self.gh.call_count, 2)

    def test_update_sets_exact_arrays_and_empty_body(self):
        self.issue_queue(after=issue_fixture(title='New', body='', labels=[], assignees=[]))
        result = service.execute('update_issue', {'repo': 'example/demo', 'number': 7, 'title': 'New', 'body': '',
                                  'labels': [], 'assignees': [], 'expected_updated_at': '2026-01-01T00:00:00Z'})
        self.assertEqual(result['title'], 'New')
        self.assertEqual(self.payload(2), {'title': 'New', 'body': '', 'labels': [], 'assignees': []})
        self.assertEqual(self.gh.call_args_list[2].args[0][4], 'PATCH')

    def test_update_readback_mismatch_requires_reconciliation(self):
        self.issue_queue(after=issue_fixture())
        with self.assertRaisesRegex(service.GitHubError, 'reconcile'):
            service.execute('update_issue', {'repo': 'example/demo', 'number': 7, 'title': 'New', 'expected_updated_at': '2026-01-01T00:00:00Z'})
        self.assertEqual(self.gh.call_count, 5)

    def test_uncertain_write_not_retried(self):
        self.queue(reply(issue_fixture()), reply([]), subprocess.TimeoutExpired('gh', 60))
        with self.assertRaisesRegex(service.GitHubError, 'reconcile'):
            service.execute('issue_state', {'repo': 'example/demo', 'number': 7, 'state': 'CLOSED', 'expected_updated_at': '2026-01-01T00:00:00Z'})
        self.assertEqual(self.gh.call_count, 3)

    def test_issue_state_verifies_readback(self):
        self.issue_queue(after=issue_fixture(state='closed'))
        result = service.execute('issue_state', {'repo': 'example/demo', 'number': 7, 'state': 'CLOSED', 'expected_updated_at': '2026-01-01T00:00:00Z'})
        self.assertEqual(result['state'], 'CLOSED')
        self.assertEqual(self.payload(2), {'state': 'closed'})

    def test_comment_verifies_exact_created_comment(self):
        comment = {'id': 81, 'body': 'A comment', 'html_url': 'https://example.test/comment'}
        self.queue(reply(issue_fixture()), reply([]), reply(comment), reply(comment))
        result = service.execute('comment', {'repo': 'example/demo', 'number': 7, 'body': 'A comment'})
        self.assertEqual(result['comment'], comment)
        self.assertEqual(self.gh.call_args.args[0][2], 'repos/example/demo/issues/comments/81')

    def test_malformed_postwrite_readback_requires_reconciliation(self):
        self.queue(reply(issue_fixture()), reply([]), reply({'id': 81}), reply([]))
        with self.assertRaisesRegex(service.GitHubError, 'reconcile'):
            service.execute('comment', {'repo': 'example/demo', 'number': 7, 'body': 'A comment'})

    def test_comment_readback_mismatch(self):
        self.queue(reply(issue_fixture()), reply([]), reply({'id': 81}), reply({'id': 81, 'body': 'other'}))
        with self.assertRaisesRegex(service.GitHubError, 'reconcile'):
            service.execute('comment', {'repo': 'example/demo', 'number': 7, 'body': 'A comment'})

    def test_move_checks_membership_option_and_expected_status(self):
        for overrides, message in (({'item_id': 'OTHER'}, 'member'), ({'option_id': 'missing'}, 'option'), ({'expected_status': None}, 'Stale')):
            self.queue(*board_replies())
            args = {'owner': 'example', 'number': 1, 'item_id': 'ITEM', 'option_id': 'done', 'expected_status': 'todo'}
            args.update(overrides)
            start = self.gh.call_count
            with self.assertRaisesRegex(service.GitHubError, message):
                service.execute('move', args)
            self.assertEqual(self.gh.call_count - start, 4)

    def test_move_uses_discovered_field_and_verifies(self):
        self.queue(*board_replies([item_fixture(status=None)]), reply({'data': {'updateProjectV2ItemFieldValue': {'projectV2Item': {'id': 'ITEM'}}}}),
                   *board_replies([item_fixture(status='done')]))
        result = service.execute('move', {'owner': 'example', 'number': 1, 'item_id': 'ITEM', 'option_id': 'done', 'expected_status': None})
        self.assertEqual(result['item']['status'], 'done')
        self.assertEqual(self.payload(4)['variables'], {'project': 'PROJECT', 'field': 'FIELD', 'item': 'ITEM', 'option': 'done'})

    def test_move_readback_failure(self):
        self.queue(*board_replies(), reply({'data': {'updateProjectV2ItemFieldValue': {'projectV2Item': {'id': 'ITEM'}}}}), *board_replies())
        with self.assertRaisesRegex(service.GitHubError, 'reconcile'):
            service.execute('move', {'owner': 'example', 'number': 1, 'item_id': 'ITEM', 'option_id': 'done', 'expected_status': 'todo'})

    def test_create_issue_and_project_membership_verified(self):
        self.queue(*board_replies([]), reply(issue_fixture()), reply({'data': {'addProjectV2ItemById': {'item': {'id': 'ITEM'}}}}),
                   reply(issue_fixture()), reply([]), *board_replies())
        result = service.execute('create_issue', {'repo': 'example/demo', 'title': 'Example issue', 'body': 'Example body',
                                  'labels': ['bug'], 'assignees': ['example-user'], 'owner': 'example', 'project_number': 1})
        self.assertEqual(result['issue']['number'], 7)
        self.assertEqual(result['item']['id'], 'ITEM')
        self.assertEqual(self.payload(5)['variables'], {'project': 'PROJECT', 'content': 'ISSUE'})

    def test_create_partial_failure_is_not_retried(self):
        self.queue(*board_replies([]), reply(issue_fixture()), reply({'errors': [{'message': 'Cannot add'}]}))
        with self.assertRaisesRegex(service.GitHubError, 'reconcile') as caught:
            service.execute('create_issue', {'repo': 'example/demo', 'title': 'Example issue', 'body': '',
                            'owner': 'example', 'project_number': 1})
        self.assertIn(issue_fixture()['html_url'], str(caught.exception))
        self.assertIn('Do not create a duplicate', str(caught.exception))
        self.assertEqual(self.gh.call_count, 6)
        self.assertEqual(self.payload(4)['labels'], [])
        self.assertEqual(self.payload(4)['assignees'], [])

    def test_rest_pagination_cap_and_loop(self):
        for cap in (1, 3):
            batch = list(range(100))
            self.queue(reply(issue_fixture()), reply(batch), reply(batch))
            with patch.object(service, 'MAX_PAGES', cap), self.assertRaisesRegex(service.GitHubError, 'limit|repeated'):
                service.execute('issue', {'repo': 'example/demo', 'number': 7})


if __name__ == '__main__':
    unittest.main()
