from dateutil.parser import parse as parsetime

from . import Bugzilla

class BugzillaBzapi(Bugzilla):

    def parse_search(self, **kw):
        params = {}
        options_log = []
        for k, v in ((k, v) for (k, v) in kw.iteritems() if v):
            if k in self.service.attributes:
                if k == 'creation_time' or k == 'last_change_time':
                    params[k] = v[1]
                    options_log.append('  {}: {} (since {} UTC)'.format(self.service.attributes[k], v[0], parsetime(v[1])))
                elif k == 'status':
                    params[k] = []
                    for status in v:
                        if status.lower() == 'all':
                            params[k].extend(['UNCONFIRMED', 'NEW', 'CONFIRMED', 'ASSIGNED', 'IN_PROGRESS', 'REOPENED', 'RESOLVED', 'VERIFIED'])
                        elif status.lower() == 'open':
                            params[k].extend(['UNCONFIRMED', 'NEW', 'CONFIRMED', 'ASSIGNED', 'IN_PROGRESS', 'REOPENED'])
                        elif status.lower() == 'closed':
                            params[k].extend(['RESOLVED', 'VERIFIED'])
                        else:
                            params[k].append(status)
                    options_log.append('  {}: {}'.format(self.service.attributes[k], ', '.join(params[k])))
                else:
                    params[k] = v
                    options_log.append('  {}: {}'.format(self.service.attributes[k], ', '.join(v)))
            elif k == 'terms':
                params['summary'] = v
                options_log.append('  {}: {}'.format('Summary', ', '.join(v)))
            elif k == 'order':
                if v == 'id':
                    params['order'] = 'Bug Number'
                elif v == 'importance':
                    params['order'] = 'Importance'
                elif v == 'assignee':
                    params['order'] = 'Assignee'
                elif v == 'modified':
                    params['order'] = 'Last Changed'
                options_log.append('  {}: {}'.format('Sort by', v))

        if not params.keys():
            raise RuntimeError('Please specify search terms or options')

        if not 'status' in params.keys():
            params['status'] = ['UNCONFIRMED', 'NEW', 'CONFIRMED', 'ASSIGNED', 'IN_PROGRESS', 'REOPENED']
            options_log.append('  {}: {}'.format('Status', ', '.join(params['status'])))

        if kw['fields'] is None:
            fields = ['id', 'assigned_to', 'summary']
        else:
            fields = kw['fields']

        params['include_fields'] = [','.join(fields)]
        return (options_log, fields, params)
