
#
# gpodder.plugins.itunes: Resolve iTunes feed URLs (based on a gist by Yepoleb, 2014-03-09)
# Copyright (c) 2014, Thomas Perl <m@thp.io>
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
# OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.
#


import gpodder

from gpodder import util
from gpodder import registry

import re
import logging

logger = logging.getLogger(__name__)

ITUNES_DEFAULT_VERSION = '11.1.5'

ITUNES_FEEDURL_RE = {'10.7': r'feed-url="([^"]+)"',
                     '11.1.5': r'"feedUrl":\s*"([^"]+)"'}


class ITunesFeedException(BaseException):
    pass


@registry.feed_handler.register
def itunes_feed_handler(channel, max_episodes):
    m = re.match(r'https?://itunes.apple.com/(?:[^/]*/)?podcast/.+$', channel.url, re.I)
    if m is None:
        return None

    logger.debug('Detected iTunes feed.')
    version = ITUNES_DEFAULT_VERSION
    headers = {'User-agent': 'iTunes/{}'.format(version)}
    try:
        data = util.urlopen(channel.url, headers).read().decode('utf-8')
        m = re.search(ITUNES_FEEDURL_RE[version], data)
        if m is None:
            raise ITunesFeedException('Could not resolve real feed URL from iTunes feed.')

        url = m.group(1)
        logger.info('Resolved iTunes feed URL: {} -> {}'.format(channel.url, url))
        channel.url = url

        # Delegate further processing of the feed to the normal podcast parser
        # by returning None (will try the next handler in the resolver chain)
        return None
    except Exception as ex:
        logger.warn('Cannot resolve iTunes feed: {}'.format(str(ex)))
        raise
