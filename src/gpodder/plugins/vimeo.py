#
# gpodder.plugins.vimeo: Vimeo download magic (2012-01-03)
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

from gpodder import util
from gpodder import registry

from gpodder.plugins import podcast

import logging
logger = logging.getLogger(__name__)

import re

VIMEOCOM_RE = re.compile(r'http[s]?://vimeo\.com/(\d+)$', re.IGNORECASE)
VIMEOCHANNEL_RE = re.compile(r'http[s]?://vimeo\.com/(channels/[^/]+|\d+)$', re.IGNORECASE)
MOOGALOOP_RE = re.compile(r'http[s]?://vimeo\.com/moogaloop\.swf\?clip_id=(\d+)$', re.IGNORECASE)
VIMEO_VIDEO_RE = re.compile(r'http[s]?://vimeo.com/channels/(?:[^/])+/(\d+)$', re.IGNORECASE)
SIGNATURE_RE = re.compile(r'"timestamp":(\d+),"signature":"([^"]+)"')
DATA_CONFIG_RE = re.compile(r'data-config-url="([^"]+)"')

# List of qualities, from lowest to highest
FILEFORMAT_RANKING = ['mobile', 'sd', 'hd']


class VimeoError(BaseException):
    pass


@registry.download_url.register
def vimeo_resolve_download_url(episode, config):
    url = episode.url

    video_id = get_vimeo_id(url)

    if video_id is None:
        return None

    web_url = 'http://vimeo.com/%s' % video_id
    web_data = util.urlopen(web_url).read().decode('utf-8')
    data_config_frag = DATA_CONFIG_RE.search(web_data)

    if data_config_frag is None:
        raise VimeoError('Cannot get data config from Vimeo')

    data_config_url = data_config_frag.group(1).replace('&amp;', '&')

    def get_urls(data_config_url):
        data_config = util.read_json(data_config_url)
        for fileinfo in data_config['request']['files'].values():
            if not isinstance(fileinfo, dict):
                continue

            for fileformat, keys in fileinfo.items():
                if not isinstance(keys, dict):
                    continue

                yield (fileformat, keys['url'])

    fileformat_to_url = dict(get_urls(data_config_url))

    preferred_fileformat = config.plugins.vimeo.fileformat
    if preferred_fileformat is not None and preferred_fileformat in fileformat_to_url:
        logger.debug('Picking preferredformat: %s', preferred_fileformat)
        return fileformat_to_url[preferred_fileformat]

    def fileformat_sort_key_func(fileformat):
        if fileformat in FILEFORMAT_RANKING:
            return FILEFORMAT_RANKING.index(fileformat)

        return 0

    for fileformat in sorted(fileformat_to_url, key=fileformat_sort_key_func, reverse=True):
        logger.debug('Picking best format: %s', fileformat)
        return fileformat_to_url[fileformat]


def get_vimeo_id(url):
    result = MOOGALOOP_RE.match(url)
    if result is not None:
        return result.group(1)

    result = VIMEOCOM_RE.match(url)
    if result is not None:
        return result.group(1)

    result = VIMEO_VIDEO_RE.match(url)
    if result is not None:
        return result.group(1)

    return None


def is_video_link(url):
    return (get_vimeo_id(url) is not None)


def get_real_channel_url(url):
    result = VIMEOCHANNEL_RE.match(url)
    if result is not None:
        return 'http://vimeo.com/%s/videos/rss' % result.group(1)

    return None


def get_real_cover(url):
    return None


class PodcastParserVimeoFeed(podcast.PodcastParserEnclosureFallbackFeed):
    def _get_enclosure_url(self, episode_dict):
        if is_video_link(episode_dict['link']):
            return episode_dict['link']

        return None


@registry.feed_handler.register
def vimeo_feed_handler(channel, max_episodes, config):
    url = get_real_channel_url(channel.url)
    if url is None:
        return None

    logger.info('Vimeo feed resolved: {} -> {}'.format(channel.url, url))
    channel.url = url

    return PodcastParserVimeoFeed(channel, max_episodes)


@registry.episode_basename.register
def vimeo_resolve_episode_basename(episode, sanitized):
    if sanitized and is_video_link(episode.url):
        return sanitized


@registry.podcast_title.register
def vimeo_resolve_podcast_title(podcast, new_title):
    VIMEO_PREFIX = 'Vimeo / '
    if new_title.startswith(VIMEO_PREFIX):
        return new_title[len(VIMEO_PREFIX):] + ' on Vimeo'


@registry.content_type.register
def vimeo_resolve_content_type(episode):
    if is_video_link(episode.url):
        return 'video'
