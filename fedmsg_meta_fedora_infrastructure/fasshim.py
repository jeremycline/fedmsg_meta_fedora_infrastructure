import collections
import logging
import threading
from hashlib import sha256, md5

from dogpile.cache import make_region
try:
    from six.moves.urllib import parse
except ImportError:
    # Really really old 'six' doesn't have this move.. so we fall back to
    # python-2 only usage.  If we're on an old 'six', then we can assume that
    # we must also be on an old Python.
    import urllib as parse
import fedora.client
import fedora.client.fas2


_log = logging.getLogger(__name__)

_fas_cache = {}
_fas_cache_lock = threading.Lock()


#: The dogpile cache region used to cache results from FAS. By default, it uses
#: a dictionary backend to cache results. Call ``configure`` on it with
#: ``replace_existing_backend=True``to alter its configuration. Be aware this will
#: destroy any existing cached values. If you opt to use a non-memory backend, you
#: need to handle error cases that may arise from your chosen backend (e.g. connection
#: exceptions).
fas_region = make_region().configure('dogpile.cache.memory')


def _ordered_query_params(params):
    # if OrderedDict is available, preserver order of params
    #  to make this easily testable on PY3
    if hasattr(collections, 'OrderedDict'):
        retval = collections.OrderedDict(params)
    else:
        retval = dict(params)
    return retval


# https://github.com/fedora-infra/fedmsg_meta_fedora_infrastructure/issues/320
hardcoded_avatars = {
    'bodhi': 'https://apps.fedoraproject.org/img/icons/bodhi-{size}.png',
    'koschei': 'https://apps.fedoraproject.org/img/icons/koschei-{size}.png',
    # Taskotron may have a new logo at some point.  Check this out:
    # https://mashaleonova.wordpress.com/2015/08/18/a-logo-for-taskotron/
    # Ask tflink before actually putting this in place though.  we need
    # a nice small square version.  It'll look great!
    # In the meantime, we can use this temporary logo.
    'taskotron': 'https://apps.fedoraproject.org/img/icons/taskotron-{size}.png'
}


def avatar_url(username, size=64, default='retro'):
    if username in hardcoded_avatars:
        return hardcoded_avatars[username].format(size=size)
    openid = "http://%s.id.fedoraproject.org/" % username
    return avatar_url_from_openid(openid, size, default)


def avatar_url_from_openid(openid, size=64, default='retro', dns=False):
    """
    Our own implementation since fas doesn't support this nicely yet.
    """

    if dns:
        # This makes an extra DNS SRV query, which can slow down our webapps.
        # It is necessary for libravatar federation, though.
        import libravatar
        return libravatar.libravatar_url(
            openid=openid,
            size=size,
            default=default,
        )
    else:
        params = _ordered_query_params([('s', size), ('d', default)])
        query = parse.urlencode(params)
        hash = sha256(openid.encode('utf-8')).hexdigest()
        return "https://seccdn.libravatar.org/avatar/%s?%s" % (hash, query)


def avatar_url_from_email(email, size=64, default='retro', dns=False):
    """
    Our own implementation since fas doesn't support this nicely yet.
    """

    if dns:
        # This makes an extra DNS SRV query, which can slow down our webapps.
        # It is necessary for libravatar federation, though.
        import libravatar
        return libravatar.libravatar_url(
            email=email,
            size=size,
            default=default,
        )
    else:
        params = _ordered_query_params([('s', size), ('d', default)])
        query = parse.urlencode(params)
        hash = md5(email.encode('utf-8')).hexdigest()
        return "https://seccdn.libravatar.org/avatar/%s?%s" % (hash, query)


def _search_fas(search_string, fas_credentials, by_email=False):
    """
    Search FAS with the given search string.

    Args:
        search_string (str): The string to search FAS with.
        fas_credentials (dict): A dictionary containing at least two keys,
            'username' and 'password', used to authenticate with FAS. Provide a
            'base_url' key to specify which FAS instance to query (defaults to
            'https://admin.fedoraproject.org/accounts/')
        by_email (bool): Set this to ``True`` if the search string is an email
            address.
    """
    url = fas_credentials.get('base_url', 'https://admin.fedoraproject.org/accounts/')
    fasclient = fedora.client.fas2.AccountSystem(
        base_url=url,
        username=fas_credentials['username'],
        password=fas_credentials['password'],
    )
    req_params = {'search': search_string}
    if by_email:
        req_params['by_email'] = 1

    _log.info("Querying %s with %r", url, req_params)
    response = fasclient.send_request('/user/list', req_params=req_params, auth=True)

    if not response['people']:
        raise ValueError('There is no FAS account that matches "{}"'.format(str(req_params)))

    # Warm up the cache with whatever we get. Although the ``cache_on_arguments``
    # decorator will populate the cache for either the email or the ircnick, this
    # does both to save a second request.
    email_key_func = fas_region.function_key_generator(None, email2fas)
    nick_key_func = fas_region.function_key_generator(None, nick2fas)
    for person in response['people']:
        fasname = response['username']
        email = response.get('email')
        ircnick = response.get('ircnick')
        if email:
            fas_region.set(email_key_func(email), fasname)
        if ircnick:
            fas_region.set(nick_key_func(ircnick), fasname)

    return response['people']


@fas_region.cache_on_arguments()
def nick2fas(nickname, fas_credentials=None, **config):
    """
    Get a Fedora Account System username from an IRC nickname.

    Args:
        nickname (str): The user's IRC nickname to lookup in FAS.
        fas_credentials (dict): A dictionary containing two keys, 'username'
            and 'password', used to authenticate with FAS.

    Raises:
        ValueError: When the IRC nickname provided results in no accounts or
            when it results in more than one account.
        fedora.client.ServerError: When a server error occurs during the
            request.
    """
    people = _search_fas(nickname, fas_credentials, by_email=False)
    if len(people) > 1:
        raise ValueError('The provided nickname, {}, returns multiple users'
                         ' in the search'.format(nickname))
    return people[0]['username']


@fas_region.cache_on_arguments()
def email2fas(email, fas_credentials=None, **config):
    """
    Get a Fedora Account System username from an IRC nickname.

    Args:
        nickname (str): The user's IRC nickname to lookup in FAS.
        fas_credentials (dict): A dictionary containing two keys, 'username'
            and 'password', used to authenticate with FAS.
    """
    if email.endswith('@fedoraproject.org'):
        return email.rsplit('@', 1)[0]

    people = _search_fas(email, fas_credentials, by_email=True)
    if len(people) > 1:
        raise ValueError('The provided email, {}, returns multiple users'
                         ' in the search'.format(email))
    return people[0]['username']
