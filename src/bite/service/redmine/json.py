"""Support Redmine's JSON-REST interface.

API docs:
    - http://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from . import Redmine
from .._jsonrest import JsonREST


class RedmineJson(Redmine, JsonREST):

    _service = 'redmine-json'
    _ext = 'json'
