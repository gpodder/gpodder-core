
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

from gpodder import util, registry, directory

import re
import logging
import urllib.parse

logger = logging.getLogger(__name__)

class ITunesFeedException(Exception):
    pass


@registry.feed_handler.register
def itunes_feed_handler(channel, max_episodes, config):
    m = re.match(r'https?://(podcasts|itunes)\.apple\.com/(?:[^/]*/)?podcast/.*id(?P<podcast_id>[0-9]+).*$', channel.url, re.I)
    if m is None:
        return None

    logger.debug('Detected iTunes feed.')

    itunes_lookup_url = f'https://itunes.apple.com/lookup?entity=podcast&id={m.group("podcast_id")}'
    try:
        json_data = util.read_json(itunes_lookup_url)

        if len(json_data['results']) != 1:
            raise ITunesFeedException(f'Unsupported number of results: {str(len(json_data["results"]))}')

        feed_url = util.normalize_feed_url(json_data['results'][0]['feedUrl'])

        if not feed_url:
            raise ITunesFeedException(f'Could not resolve real feed URL from iTunes feed.\nDetected URL: {json_data["results"][0]["feedUrl"]}')

        logger.info(f'Resolved iTunes feed URL: {channel.url} -> {feed_url}')
        channel.url = feed_url

        # Delegate further processing of the feed to the normal podcast parser
        # by returning None (will try the next handler in the resolver chain)
        return None
    except Exception as ex:
        logger.warn(f'Cannot resolve iTunes feed: {str(ex)}')
        raise

@registry.directory.register_instance
class ApplePodcastsSearchProvider(directory.Provider):
    def __init__(self):
        self.name = 'Apple Podcasts'
        self.kind = directory.Provider.PROVIDER_SEARCH
        self.priority = directory.Provider.PRIORITY_SECONDARY_SEARCH

    def on_search(self, query):
        json_url = f'https://itunes.apple.com/search?media=podcast&term={urllib.parse.quote(query)}'

        return [directory.DirectoryEntry(entry['collectionName'], entry['feedUrl'], entry['artworkUrl100']) for entry in util.read_json(json_url)['results']]
