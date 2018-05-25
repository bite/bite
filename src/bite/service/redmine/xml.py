"""Support Redmine's XML-REST interface.

API docs:
    - http://www.redmine.org/projects/redmine/wiki/Rest_api
"""

from . import Redmine, RedmineElastic
from .._xmlrest import XmlREST


class RedmineXml(Redmine, XmlREST):

    _service = 'redmine-xml'
    _ext = 'xml'


class RedmineElasticXml(RedmineElastic, XmlREST):

    _service = 'redmine-elastic-xml'
    _ext = 'xml'
