#
# gpodder.plugins.podcast: Faster Podcast Parser module for gPodder (2012-12-29)
# Copyright (c) 2012, 2013, Thomas Perl <m@thp.io>
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

from gpodder import registry
from gpodder import util

import podcastparser

import urllib.request
import urllib.error
import urllib.parse
import re

import logging

logger = logging.getLogger(__name__)


class PodcastParserFeed(object):
    # Maximum number of pages for paged feeds
    PAGED_FEED_MAX_PAGES = 50

    def __init__(self, channel, max_episodes):
        url = channel.authenticate_url(channel.url)

        logger.info('Parsing via podcastparser: %s', url)

        headers = {}
        if channel.http_etag:
            headers['If-None-Match'] = channel.http_etag
        if channel.http_last_modified:
            headers['If-Modified-Since'] = channel.http_last_modified

        try:
            stream = util.urlopen(url, headers)
            self.status = 200
            info = stream.info()
            self.etag = info.get('etag')
            self.modified = info.get('last-modified')
            self.parsed = podcastparser.parse(url, stream, max_episodes)
            self._handle_paged_feed(max_episodes)
        except urllib.error.HTTPError as error:
            self.status = error.code
            if error.code == 304:
                logger.info('Not modified')
            else:
                logger.warn('Feed update failed: %s', error)
                raise error

            self.etag = None
            self.modified = None
            self.parsed = None

    def was_updated(self):
        return (self.status == 200)

    def get_etag(self, default):
        return self.etag or default

    def get_modified(self, default):
        return self.modified or default

    def get_title(self):
        return self.parsed['title']

    def get_image(self):
        return self.parsed.get('cover_url')

    def get_link(self):
        return self.parsed.get('link', '')

    def get_type(self):
        return self.parsed.get('type', 'episodic')

    def get_description(self):
        return self.parsed.get('description', '')

    def get_payment_url(self):
        return self.parsed.get('payment_url')

    def _handle_paged_feed(self, max_episodes):
        page = 2
        remaining_episodes = max_episodes - len(self.parsed['episodes'])
        while ('paged_feed_next' in self.parsed and
                page < self.PAGED_FEED_MAX_PAGES and
                remaining_episodes > 0):
            # Take the next page from the paged feed
            url = self.parsed['paged_feed_next']
            del self.parsed['paged_feed_next']

            if not url:
                break

            try:
                logger.debug('Downloading page %d from %s', page, url)
                stream = util.urlopen(url)
                parsed = podcastparser.parse(url, stream, remaining_episodes)
                added_episodes = len(parsed['episodes'])
                remaining_episodes -= added_episodes
                logger.debug('Page %d contains %d additional episodes', page,
                             added_episodes)
                self.parsed['episodes'].extend(parsed['episodes'])

                # Next iteration if we still have a next page
                if 'paged_feed_next' in parsed:
                    self.parsed['paged_feed_next'] = parsed['paged_feed_next']
            except Exception as e:
                logger.warn('Error while fetching feed page %d from %s: %s', page, url, e)
                # Give up, don't try to download additional pages here
                break

            page += 1

    def _pick_enclosure(self, episode_dict):
        if not episode_dict['enclosures']:
            del episode_dict['enclosures']
            return False

        # FIXME: Pick the right enclosure from multiple ones
        episode_dict.update(episode_dict['enclosures'][0])
        del episode_dict['enclosures']

        return True

    def get_new_episodes(self, channel):
        existing_guids = dict((episode.guid, episode) for episode in channel.episodes)
        seen_guids = [entry['guid'] for entry in self.parsed['episodes']]
        new_episodes = []

        for episode_dict in self.parsed['episodes']:
            if not self._pick_enclosure(episode_dict):
                continue

            episode = existing_guids.get(episode_dict['guid'])
            if episode is None:
                episode = channel.episode_factory(episode_dict.items())
                new_episodes.append(episode)
                logger.info('Found new episode: %s', episode.guid)
            else:
                episode.update_from_dict(episode_dict)
                logger.info('Updating existing episode: %s', episode.guid)
            episode.save()

        return new_episodes, seen_guids


class PodcastParserEnclosureFallbackFeed(PodcastParserFeed):
    # Implement this in a subclass to determine a fallback enclosure
    # for feeds that don't list their media files as enclosures
    def _get_enclosure_url(self, episode_dict):
        return None

    def _pick_enclosure(self, episode_dict):
        if not episode_dict['enclosures']:
            url = self._get_enclosure_url(episode_dict)
            if url is not None:
                del episode_dict['enclosures']
                episode_dict['url'] = url
                return True

        return super(PodcastParserEnclosureFallbackFeed, self)._pick_enclosure(episode_dict)


class PodcastParserLinkFallbackFeed(PodcastParserEnclosureFallbackFeed):
    # Tries to use the episode link if the URL looks like an audio/video file
    # link for episodes that do not have enclosures

    def _get_enclosure_url(self, episode_dict):
        url = episode_dict.get('link')
        if url is not None:
            base, extension = util.filename_from_url(url)
            if util.file_type_by_extension(extension) in ('audio', 'video'):
                logger.debug('Using link for enclosure URL: %s', url)
                return url

        return None


@registry.fallback_feed_handler.register
def podcast_parser_handler(channel, max_episodes, config):
    return PodcastParserLinkFallbackFeed(channel, max_episodes)


@registry.url_shortcut.register
def podcast_resolve_url_shortcut():
    return {'fb': 'http://feeds.feedburner.com/%s'}
