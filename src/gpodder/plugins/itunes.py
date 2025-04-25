#
# gpodder.plugins.itunes: Resolve iTunes feed URLs (based on a gist by Yepoleb, 2014-03-09)
# Copyright (c) 2014-2025, Thomas Perl <m@thp.io>. E.S. Rosenberg (keeper-of-the-keys)
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
# 200 is the upper limit according to
# https://performance-partners.apple.com/search-api
PAGE_SIZE = 200

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
        offset = 0

        while True:
            json_url = f'https://itunes.apple.com/search?media=podcast&term={urllib.parse.quote(query)}&limit={PAGE_SIZE}&offset={offset}'
            json_data = util.read_json(json_url)

            if json_data['resultCount'] > 0:
                for entry in json_data['results']:
                    if entry.get('feedUrl') is None:
                        continue

                    title = entry['collectionName']
                    url = entry['feedUrl']
                    image = entry['artworkUrl100']

                    yield(directory.DirectoryEntry(title, url, image))
                    returned_res += 1

                offset = offset + json_data['resultCount']
            else:
            '''
            Unlike the podverse stop condition where we detect a resultCount smaller than the page size for apple we can only stop when 0 results
            are returned because the API seems to consistently return more than the page size and does this in an inconsistent fasion, most often
            returning 210 results but based on my observartion any number between page size and page size + 10 is possible.
            With an API that does not obey its own rules the only valid stop condition is no results.
            '''
                break
