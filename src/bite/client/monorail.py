import argparse
from copy import deepcopy
import datetime
from itertools import chain
from operator import attrgetter
import os
import re
import stat
import sys
from urllib.parse import urlencode

import dateutil.parser
from dateutil.relativedelta import *
from snakeoil.demandload import demandload

from . import Cli
from ..rfc3339 import datetimetostr

demandload('bite:const')


class Monorail(Cli):
    """CLI for Monorail service."""

    _service = 'monorail'

    def _search_params(self, **kw):
        query = {}
        query_list = []
        options_log = []

        for k, v in ((k, v) for (k, v) in kw.items() if v):
            if k == 'query':
                query_list.append(v)
                options_log.append('  advanced query: {}'.format(v))
            if k == 'attachment':
                query_list.append('attachment:{}'.format(v))
                options_log.append('  attachment: {}'.format(v))
            if k == 'blocked':
                query_list.append('is:blocked')
                options_log.append('  blocked: yes')
            elif k == 'owner':
                if v != 'none':
                    query_list.append('owner:{}'.format(v))
                    options_log.append('  owner: {}'.format(v))
                else:
                    query_list.append('-has:owner')
                    options_log.append('  owner: None')
            elif k == 'blocked_on':
                options_log.append('  blocked on: {}'.format(str(v)))
                for issue in v:
                    query_list.append('blockedon:{}'.format(issue))
            elif k == 'has':
                options_log.append('  has: {}'.format(', '.join(v)))
                for field in v:
                    if field.startswith('no-'):
                        query_list.append('-has:{}'.format(field[3:]))
                    else:
                        query_list.append('has:{}'.format(field))
            elif k == 'blocking':
                options_log.append('  blocking: {}'.format(str(v)))
                for issue in v:
                    query_list.append('blocking:{}'.format(issue))
            elif k == 'cc':
                options_log.append('  cc: {}'.format(str(v)))
                for cc in v:
                    query_list.append('cc:{}'.format(cc))
            elif k == 'commenter':
                options_log.append('  commenter: {}'.format(str(v)))
                for commenter in v:
                    query_list.append('commentby:{}'.format(commenter))
            elif k == 'reporter':
                query_list.append('author:{}'.format(v))
                options_log.append('  reporter: {}'.format(v))
            elif k == 'opened'  or k == 'modified' or k == 'closed':
                (string, (date_min, date_max)) = v
                if date_min is not None:
                    query_list.append('{}-after:{}'.format(k, date_min.replace('-', '/')))
                if date_max is not None:
                    query_list.append('{}-before:{}'.format(k, date_max.replace('-', '/')))
                if k == 'closed':
                    query['can'] = 'all'
                options_log.append('  {}: {}'.format(k, string))
            elif k == 'published'  or k == 'updated':
                (string, (date_min, date_max)) = v
                if date_min is not None:
                    query['{}-min'.format(k)] = date_min
                if date_max is not None:
                    query['{}-max'.format(k)] = date_max
                options_log.append('  {}: {}'.format(k, string))
            elif k == 'label':
                options_log.append('  label: {}'.format(', '.join(v)))
                for label in v:
                    query_list.append('label:{}'.format(label))
            elif k == 'stars':
                (stars_str, stars_query) = v
                options_log.append('  stars: {}'.format(str(stars_str)))
                if isinstance(stars_query, str):
                    query_list.append(stars_query)
                elif isinstance(stars_query, list):
                    query_list.append(self.build_or_query(stars_query, 'stars', ors=True, equal=True))
            elif k == 'milestone':
                options_log.append('  milestone: {}'.format(str(v)))
                query_list.append(self.build_or_query(v, 'milestone'))
            elif k == 'type':
                options_log.append('  type: {}'.format(str(v)))
                query_list.append(self.build_or_query(v, 'type'))
            elif k == 'attr':
                for item in v:
                    (attr, value) = item.split(':')
                    options_log.append('  {}: {}'.format(attr, str(value)))
                    query_list.append(item)
            elif k == 'status':
                options_log.append('  status: {}'.format(', '.join(v)))
                status_list = []
                for status in v:
                    if status == 'all':
                        query['can'] = 'all'
                    elif status == 'open':
                        query['can'] = 'open'
                    elif status == 'closed':
                        query_list.append('-is:open')
                        query['can'] = 'all'
                    else:
                        status_list.append(status)
                if status_list:
                    query_list.append(self.build_or_query(status_list, 'status'))
                    query['can'] = 'all'

        # default: search all text fields (summary, description, and comment)
        if kw['terms']:
            search_terms = '{}'.format(' '.join(kw['terms']))
            if kw['summary']:
                options_log.append('  summary: {}'.format(search_terms))
                query_list.append('summary:{}'.format(search_terms))
            if kw['description']:
                options_log.append('  description: {}'.format(search_terms))
                query_list.append('description:{}'.format(search_terms))
            if kw['comment']:
                options_log.append('  comment: {}'.format(search_terms))
                query_list.append('comment:{}'.format(search_terms))
            if not kw['summary'] and not kw['description'] and not kw['comment']:
                query_list.append(search_terms)
                options_log.append('  terms: {}'.format(search_terms))

        if query_list:
            query['q'] = ' '.join(query_list)

        if not 'fields' in kw or kw['fields'] is None:
            fields = ['id', 'owner', 'title']
        else:
            fields = kw['fields']
            options_log.append('  {}: {}'.format('Fields', ' '.join(fields)))

        if query:
            if kw['limit'] is None:
                kw['limit'] = 250
            if kw['offset'] is None:
                kw['offset'] = 1

            query['max-results'] = kw['limit']
            query['start-index'] = kw['offset']

            # default: search open issues only
            if 'can' not in query:
                query['can'] = 'open'

            if kw['sort']:
                options_log.append('  Sort: {}'.format(kw['sort']))

            if kw['url']:
                browser_args = deepcopy(query)
                if kw['sort'] is not None:
                    browser_args['sort'] = kw['sort']
                del browser_args['max-results']
                if 'can' in browser_args:
                    if browser_args['can'] == 'all':
                        browser_args['can'] = 1
                    elif browser_args['can'] == 'open':
                        browser_args['can'] = 2

                options_log.append('URL: https://code.google.com/p/{}/issues/list?{}'.format(self.service.project_name, urlencode(browser_args)))
        else:
            raise RuntimeError('Please specify search terms or options')

        return (options_log, fields, query)

    def build_or_query(self, search_list, search_str, ors=False, equal=False, filler_str=','):
        if ors:
            if equal:
                search_list = ['{}={}'.format(search_str, item) for item in search_list]
            else:
                search_list = ['{}:{}'.format(search_str, item) for item in search_list]
            filler_str = ' OR '
            prefix = ''
        else:
            prefix = '{}:'.format(search_str)

        return '{}{}'.format(prefix, filler_str.join(map(str, search_list)))

    def search(self, dry_run, **kw):
        (search_options, fields, params) = self.search_params(**kw)

        if kw['fields'] is None:
            kw['fields'] = fields

        self.log('Searching for {}s with the following options:'.format(self.service.item))
        for line in search_options:
            self.log(line)

        if dry_run: return

        (issues, results, more_results) = self.service.search(params)

        if not issues:
            self.log('No issues found.')
        else:
            if more_results:
                if kw['sort'] is None:
                    self.print_search(issues, **kw)
                else:
                    issues = list(issues)
                while more_results:
                    (more_issues, _, more_results) = self.service.search(url=more_results)
                    if kw['sort'] is None:
                        self.print_search(more_issues, **kw)
                    else:
                        issues.extend(more_issues)
                if kw['sort'] is not None:
                    self.print_search(issues, **kw)
            else:
                self.print_search(issues, **kw)

            self.log('{} issue(s) found.'.format(results))

    def _print_item(self, issues, get_comments, get_attachments, get_updates, **kw):
        """ Format and print the Issue object in a command line environment. """
        for issue in issues:
            print('=' * const.COLUMNS)
            print(str(issue))

            if get_attachments and issue.attachments:
                print()
                for a in issue.attachments:
                    id = a.id
                    size = a.size
                    name = a.filename
                    print('Attachment: [{}] [{}] ({})'.format(id, name, size))

            if get_comments:
                for comment in issue.comments:
                    print()
                    self._print_lines(str(comment))

                    if get_updates and comment.changes is not None:
                        print()
                        for field, change in comment.changes['updates'].items():
                            if isinstance(change, list):
                                change = ' '.join(change)
                            print('{}: {}'.format(field, change))

    def output(self, issue, field):
        value = getattr(issue, field)

        if field == 'cc' and isinstance(value, list):
            return list(map(self.service._desuffix, value))
        elif isinstance(value, str):
            return self.service._desuffix(value)
        else:
            return value

    def print_search(self, issues, fields, output, **kw):
        if kw['sort'] is not None:
            sort = kw['sort']
            if sort.startswith('-'):
                reverse = True
                sort = sort[1:]
            else:
                reverse = False
            issues = sorted(issues, key=attrgetter(sort), reverse=reverse)

        if output is None:
            if fields == ['id', 'owner', 'title']:
                output = '{} {:<20} {}'
            else:
                output = ' '.join(['{}' for x in fields])

        for issue in issues:
            if output == '-':
                for field in fields:
                    value = getattr(issue, field)
                    if value is None:
                        continue
                    if isinstance(value, list):
                        print('\n'.join(map(str, value)))
                    else:
                        print(value)
            else:
                values = [self.output(issue, field) for field in fields]
                line = output.format(*values)
                print(line[:const.COLUMNS])
