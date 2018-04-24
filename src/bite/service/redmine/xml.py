"""Support Redmine's XML-REST interface.

API docs:
    - http://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from . import Redmine
from .._xmlrest import XmlREST


class RedmineXml(Redmine, XmlREST):

    _service = 'redmine-xml'
    _ext = 'xml'
