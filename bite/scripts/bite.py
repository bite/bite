from signal import signal, SIGPIPE, SIG_DFL, SIGINT
import sys

from bite import parse_args, get_service
from bite.exceptions import CliError, CommandError, RequestError


def main(args):
    signal(SIGPIPE, SIG_DFL)
    signal(SIGINT, SIG_DFL)

    try:
        initial_args, args_list = parse_args()
        service_name = initial_args['service']
        service = get_service(service_name, module_name='bite.services', **initial_args)
        initial_args['service'] = service
        client = get_service(service_name, module_name='bite.cli', **initial_args)
        for args in args_list:
            cmd = getattr(client, args['fcn'])
            cmd(**args)

        #client.run(args, **initial_args)

    except (CliError, CommandError, RequestError) as e:
        print('bite: error: {}'.format(e))
        sys.exit(1)
    except:
        raise
