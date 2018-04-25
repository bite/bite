from .. import args


class BitbucketOpts(args.ServiceOpts):

    _service = 'bitbucket'


@args.subcmd(BitbucketOpts)
class Search(args.Search):
    pass
