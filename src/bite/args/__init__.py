import sys

from ..argparser import string_list, parse_filters

def base_options(parser, method):
    group = parser.add_argument_group('{} options'.format(method.capitalize()))
    try:
        getattr(sys.modules[__name__], method)(group)
    except AttributeError:
        pass
    return group

def generic_receive(parser):
    parser.add_argument('-f', '--fields',
        type=string_list,
        metavar='FIELD | FIELD,FIELD,...',
        help='fields to output')
    parser.add_argument('--filter',
        action=parse_filters,
        dest='filters',
        metavar='FILTER | FILTER,FILTER,...',
        help='Only show items matching a given filter')

def generic_send(parser):
    parser.add_argument('--ask',
        action='store_true',
        help='require confirmation before submitting modifications')

def search(parser):
    parser.add_argument('--limit',
        type=int,
        help='Limit the number of records returned in a search')
    parser.add_argument('--offset',
        type=int,
        help='Set the start position for a search')

def get(parser):
    parser.add_argument('-a', '--no-attachments',
        action='store_false',
        help='do not show attachments',
        dest='get_attachments')
    parser.add_argument('-c', '--no-comments',
        action='store_false',
        help='do not show comments',
        dest='get_comments')
    parser.add_argument('-B', '--browser',
        action='store_true',
        help="open item page in a browser")

def attachments(parser):
    parser.add_argument('-U', '--url',
        dest='output_url',
        action='store_true',
        help='output the URL of the attachment')
    parser.add_argument('-V', '--view',
        action='store_true',
        help='output attachment data')
    parser.add_argument('-B', '--browser',
        action='store_true',
        help="open item page in a browser")
    parser.add_argument('-I', '--item-id',
        action='store_true',
        help='search by item ID(s) rather than attachment ID(s)')

def attach(parser):
    parser.add_argument('-d', '--description',
        help='a long description of the attachment',
        dest='comment')
    parser.add_argument('-t', '--title',
        help='a short description of the attachment (default: filename)',
        dest='summary')

def modify(parser):
    parser.add_argument('-C', '--comment-editor',
        action='store_true',
        help='add comment via default editor')
    parser.add_argument('-F', '--comment-from',
        help='add comment from file. If -C is also specified, '
            'the editor will be opened with this file as its contents')

def create(parser):
    parser.add_argument('-F' , '--description-from',
        help='description from contents of file')
    parser.add_argument('--append-command',
        help='append the output of a command to the description')
    parser.add_argument('--batch',
        action='store_true',
        help='do not prompt for any values')
