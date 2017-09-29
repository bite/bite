import sys

from bite.argparser import string_list, parse_filters

def generic_options(subparsers, get_actions, send_actions):
    # iterate through subparsers adding generic options for send/receive methods
    for method, parser in subparsers.choices.items():
        try:
            options = parser.add_argument_group('{} options'.format(method.capitalize()))
            getattr(sys.modules[__name__], method)(options)
        except AttributeError:
            pass
        if method in get_actions:
            generic_receive(options)
        elif method in send_actions:
            generic_send(options)

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

def attachment(parser):
    parser.add_argument('-u', '--url',
        action='store_true',
        help='output the URL of the attachment')
    parser.add_argument('-v', '--view',
        action='store_true',
        help='print attachment data')

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