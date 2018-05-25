"""Support Redmine's JSON-REST interface.

API docs:
    - http://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from . import Redmine, RedmineElastic
from .._jsonrest import JsonREST


class RedmineJson(Redmine, JsonREST):

    _service = 'redmine-json'
    _ext = 'json'


class RedmineElasticJson(RedmineElastic, JsonREST):

    _service = 'redmine-elastic-json'
    _ext = 'json'
