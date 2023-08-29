
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

class ITunesFeedException(BaseException):
    pass


@registry.feed_handler.register
def itunes_feed_handler(channel, max_episodes, config):
    m = re.match(r'https?://(podcasts|itunes).apple.com/(?:[^/]*/)?podcast/.*id(?P<podcast_id>[0-9]+).*$', channel.url, re.I)
    if m is None:
        return None

    logger.debug('Detected iTunes feed.')

    if m.group('podcast_id').isnumeric == False or int(m.group('podcast_id')) < 0:
       logger.debug('Invalid podcast_id extracted from provided URL')
       return None

    itunes_lookup_url = 'https://itunes.apple.com/lookup?entity=podcast&id=' + m.group('podcast_id')
    try:
        jsonData = util.read_json(itunes_lookup_url)

        if jsonData['resultCount'] != 1:
            raise ITunesFeedException('Unsupported number of results: ' + str(jsonData['resultCount']))

        if not util.validate_url(jsonData['results'][0]['feedUrl']):
            raise ITunesFeedException('Could not resolve real feed URL from iTunes feed.\nDetected URL: ' + jsonData['results'][0]['feedUrl'])

        logger.info('Resolved iTunes feed URL: {} -> {}'.format(channel.url, jsonData['results'][0]['feedUrl']))
        channel.url = jsonData['results'][0]['feedUrl']

        # Delegate further processing of the feed to the normal podcast parser
        # by returning None (will try the next handler in the resolver chain)
        return None
    except Exception as ex:
        logger.warn('Cannot resolve iTunes feed: {}'.format(str(ex)))
        raise
