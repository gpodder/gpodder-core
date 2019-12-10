#
# gPodder: Media and podcast aggregator
# Copyright (c) 2005-2019 Thomas Perl and the gPodder Team
#
# gPodder is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# gPodder is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  gpodder.youtube - YouTube and related magic
#  Justin Forest <justin.forest@gmail.com> 2008-10-13
#

import gpodder

from gpodder import util
from gpodder import registry
from gpodder import directory
from gpodder.plugins import podcast

import os.path

import logging
logger = logging.getLogger(__name__)

import re
import json
import urllib.request
import urllib.parse
import urllib.error


# http://en.wikipedia.org/wiki/YouTube#Quality_and_codecs
# format id, (preferred ids, path(?), description) # video bitrate, audio bitrate
formats = [
    # WebM VP8 video, Vorbis audio
    # Fallback to an MP4 version of same quality.
    # Try 34 (FLV 360p H.264 AAC) if 18 (MP4 360p) fails.
    # Fallback to 6 or 5 (FLV Sorenson H.263 MP3) if all fails.
    (46, ([46, 37, 45, 22, 44, 35, 43, 18, 6, 34, 5], '45/1280x720/99/0/0',
          'WebM 1080p (1920x1080)')),
    (45, ([45, 22, 44, 35, 43, 18, 6, 34, 5],         '45/1280x720/99/0/0',
          'WebM 720p (1280x720)')),
    (44, ([44, 35, 43, 18, 6, 34, 5],                 '44/854x480/99/0/0',
          'WebM 480p (854x480)')),
    (43, ([43, 18, 6, 34, 5],                         '43/640x360/99/0/0',
          'WebM 360p (640x360)')),

    # MP4 H.264 video, AAC audio
    # Try 35 (FLV 480p H.264 AAC) between 720p and 360p because there's no MP4 480p.
    # Try 34 (FLV 360p H.264 AAC) if 18 (MP4 360p) fails.
    # Fallback to 6 or 5 (FLV Sorenson H.263 MP3) if all fails.
    (38, ([38, 37, 22, 35, 18, 34, 6, 5], '38/1920x1080/9/0/115', 'MP4 4K 3072p (4096x3072)')),
    (37, ([37, 22, 35, 18, 34, 6, 5],     '37/1920x1080/9/0/115', 'MP4 HD 1080p (1920x1080)')),
    (22, ([22, 35, 18, 34, 6, 5],         '22/1280x720/9/0/115',  'MP4 HD 720p (1280x720)')),
    (18, ([18, 34, 6, 5],                 '18/640x360/9/0/115',   'MP4 360p (640x360)')),

    # FLV H.264 video, AAC audio
    # Does not check for 360p MP4.
    # Fallback to 6 or 5 (FLV Sorenson H.263 MP3) if all fails.
    (35, ([35, 34, 6, 5], '35/854x480/9/0/115',   'FLV 480p (854x480)')),  # 1 - 0.80 Mbps, 128 kbps
    (34, ([34, 6, 5],     '34/640x360/9/0/115',   'FLV 360p (640x360)')),  # 0.50 Mbps, 128 kbps

    # FLV Sorenson H.263 video, MP3 audio
    (6, ([6, 5],         '5/480x270/7/0/0',      'FLV 270p (480x270)')),  # 0.80 Mbps,  64 kbps
    (5, ([5],            '5/320x240/7/0/0',      'FLV 240p (320x240)')),  # 0.25 Mbps,  64 kbps
]
formats_dict = dict(formats)

V3_API_ENDPOINT = 'https://www.googleapis.com/youtube/v3'
CHANNEL_VIDEOS_XML = 'https://www.youtube.com/feeds/videos.xml'


class YouTubeError(Exception):
    pass


def get_fmt_ids(youtube_config):
    fmt_ids = youtube_config.preferred_fmt_ids
    if not fmt_ids:
        format = formats_dict.get(youtube_config.preferred_fmt_id)
        if format is None:
            fmt_ids = []
        else:
            fmt_ids, path, description = format

    return fmt_ids


@registry.download_url.register
def youtube_resolve_download_url(episode, config):
    url = episode.url
    preferred_fmt_ids = get_fmt_ids(config.plugins.youtube)

    if not preferred_fmt_ids:
        preferred_fmt_ids, _, _ = formats_dict[22]  # MP4 720p

    vid = get_youtube_id(url)
    if vid is None:
        return None

    page = None
    url = 'https://www.youtube.com/get_video_info?&el=detailpage&video_id=' + vid

    while page is None:
        req = util.http_request(url, method='GET')
        if 'location' in req.msg:
            url = req.msg['location']
        else:
            page = req.read().decode('utf-8')

    # Try to find the best video format available for this video
    # (http://forum.videohelp.com/topic336882-1800.html#1912972)
    def find_urls(page):
        r4 = re.search('.*&url_encoded_fmt_stream_map=([^&]+)&.*', page)
        if r4 is not None:
            fmt_url_map = urllib.parse.unquote(r4.group(1))
            for fmt_url_encoded in fmt_url_map.split(','):
                video_info = urllib.parse.parse_qs(fmt_url_encoded)
                yield (int(video_info['itag'][0]), video_info['url'][0])
        else:
            error_info = urllib.parse.parse_qs(page)
            error_message = util.remove_html_tags(error_info['reason'][0])
            raise YouTubeError('Cannot download video: %s' % error_message)

    fmt_id_url_map = sorted(find_urls(page), reverse=True)

    if not fmt_id_url_map:
        raise YouTubeError('fmt_url_map not found for video ID "%s"' % vid)

    # Default to the highest fmt_id if we don't find a match below
    _, url = fmt_id_url_map[0]

    formats_available = set(fmt_id for fmt_id, url in fmt_id_url_map)
    fmt_id_url_map = dict(fmt_id_url_map)

    for id in preferred_fmt_ids:
        id = int(id)
        if id in formats_available:
            format = formats_dict.get(id)
            if format is not None:
                _, _, description = format
            else:
                description = 'Unknown'

            logger.info('Found YouTube format: %s (fmt_id=%d)', description, id)
            return fmt_id_url_map[id]


def get_youtube_id(url):
    r = re.compile('http[s]?://(?:[a-z]+\.)?youtube\.com/v/(.*)\.swf', re.IGNORECASE).match(url)
    if r is not None:
        return r.group(1)

    r = re.compile('http[s]?://(?:[a-z]+\.)?youtube\.com/watch\?v=([^&]*)',
                   re.IGNORECASE).match(url)
    if r is not None:
        return r.group(1)

    r = re.compile('http[s]?://(?:[a-z]+\.)?youtube\.com/v/(.*)[?]', re.IGNORECASE).match(url)
    if r is not None:
        return r.group(1)

    return None


def is_video_link(url):
    return (get_youtube_id(url) is not None)


def is_youtube_guid(guid):
    return guid.startswith('tag:youtube.com,2008:video:')


def for_each_feed_pattern(func, url, fallback_result):
    """
    Try to find the username for all possible YouTube feed/webpage URLs
    Will call func(url, channel) for each match, and if func() returns
    a result other than None, returns this. If no match is found or
    func() returns None, return fallback_result.
    """
    CHANNEL_MATCH_PATTERNS = [
        'http[s]?://(?:[a-z]+\.)?youtube\.com/user/([a-z0-9]+)',
        'http[s]?://(?:[a-z]+\.)?youtube\.com/profile?user=([a-z0-9]+)',
        'http[s]?://(?:[a-z]+\.)?youtube\.com/channel/([-_a-zA-Z0-9]+)',
        'http[s]?://(?:[a-z]+\.)?youtube\.com/rss/user/([a-z0-9]+)/videos\.rss',
        'http[s]?://gdata.youtube.com/feeds/users/([^/]+)/uploads',
        'http[s]?://(?:[a-z]+\.)?youtube\.com/feeds/videos.xml\?channel_id=([-_a-zA-Z0-9]+)',
    ]

    for pattern in CHANNEL_MATCH_PATTERNS:
        m = re.match(pattern, url, re.IGNORECASE)
        if m is not None:
            result = func(url, m.group(1))
            if result is not None:
                return result

    return fallback_result


def get_channels_for_user(username, api_key_v3):
    stream = util.urlopen('{0}/channels?forUsername={1}&part=id&key={2}'.format(V3_API_ENDPOINT, username, api_key_v3))
    data = json.loads(stream.read().decode('utf-8'))
    return ['{0}?channel_id={1}'.format(CHANNEL_VIDEOS_XML, item['id']) for item in data['items']]


def get_real_channel_url(url, api_key_v3):
    # Check if it's a YouTube feed, and if we have an API key, auto-resolve the channel
    if url and api_key_v3:
        _, user = for_each_feed_pattern(lambda url, channel: (url, channel), url, (None, None))
        if user is not None:
            logger.info('Getting channels for YouTube user %s', user)
            new_urls = get_channels_for_user(user, api_key_v3)
            logger.debug('YouTube channels retrieved: %r', new_urls)
            if len(new_urls) == 1:
                return new_urls[0]

    return None


@registry.cover_art.register
def youtube_resolve_cover_art(podcast):
    url = podcast.url
    r = re.compile('http://www\.youtube\.com/rss/user/([^/]+)/videos\.rss', re.IGNORECASE)
    m = r.match(url)

    if m is not None:
        username = m.group(1)
        api_url = 'http://gdata.youtube.com/feeds/api/users/%s?v=2' % username
        data = util.urlopen(api_url).read().decode('utf-8', 'ignore')
        match = re.search('<media:thumbnail url=[\'"]([^\'"]+)[\'"]/>', data)
        if match is not None:
            return match.group(1)

    return None


class PodcastParserYouTubeFeed(podcast.PodcastParserEnclosureFallbackFeed):
    def _get_enclosure_url(self, episode_dict):
        if is_video_link(episode_dict['link']):
            return episode_dict['link']

        return None


@registry.feed_handler.register
def youtube_feed_handler(channel, max_episodes, config):
    url = get_real_channel_url(channel.url, config.plugins.youtube.api_key_v3)
    if url is None:
        return None

    channel.url = url

    return PodcastParserYouTubeFeed(channel, max_episodes)


@registry.episode_basename.register
def youtube_resolve_episode_basename(episode, sanitized):
    if sanitized and is_video_link(episode.url):
        return sanitized


@registry.podcast_title.register
def youtube_resolve_podcast_title(podcast, new_title):
    YOUTUBE_PREFIX = 'Uploads by '
    if new_title.startswith(YOUTUBE_PREFIX):
        return new_title[len(YOUTUBE_PREFIX):] + ' on YouTube'


@registry.content_type.register
def youtube_resolve_content_type(episode):
    if is_video_link(episode.url):
        return 'video'


@registry.url_shortcut.register
def youtube_resolve_url_shortcut():
    return {'yt': 'http://www.youtube.com/rss/user/%s/videos.rss',
            # YouTube playlists. To get a list of playlists per-user, use:
            # https://gdata.youtube.com/feeds/api/users/<username>/playlists
            'ytpl': 'http://gdata.youtube.com/feeds/api/playlists/%s'}


@registry.directory.register_instance
class YouTubeSearchProvider(directory.Provider):
    def __init__(self):
        self.name = 'YouTube search'
        self.kind = directory.Provider.PROVIDER_SEARCH
        self.priority = directory.Provider.PRIORITY_SECONDARY_SEARCH

    def on_search(self, query):
        url = 'http://gdata.youtube.com/feeds/api/videos?alt=json&q=%s' % urllib.parse.quote(query)
        data = util.read_json(url)

        result = []

        seen_users = set()
        for entry in data['feed']['entry']:
            user = os.path.basename(entry['author'][0]['uri']['$t'])
            title = entry['title']['$t']
            url = 'http://www.youtube.com/rss/user/%s/videos.rss' % user
            if user not in seen_users:
                result.append(directory.DirectoryEntry(user, url))
                seen_users.add(user)

        return result
