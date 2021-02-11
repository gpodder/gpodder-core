#
# gPodder - A media aggregator and podcast client
# Copyright (c) 2005-2020 The gPodder Team
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

# Soundcloud.com API client module for gPodder
# Thomas Perl <thp@gpodder.org>; 2009-11-03

import email
import json
import logging
logger = logging.getLogger(__name__)
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import gpodder
from gpodder import model, util, registry, directory

# _ = qsTr

# gPodder's consumer key for the Soundcloud API
CONSUMER_KEY = 'zrweghtEtnZLpXf3mlm8mQ'


def soundcloud_parsedate(s):
    """Parse a string into a unix timestamp

    Only strings provided by Soundcloud's API are
    parsed with this function (2009/11/03 13:37:00).
    """
    m = re.match(r'(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}):(\d{2})', s)
    return time.mktime(tuple([int(x) for x in m.groups()] + [0, 0, -1]))


def get_param(s, param='filename', header='content-disposition'):
    """Get a parameter from a string of headers

    By default, this gets the "filename" parameter of
    the content-disposition header. This works fine
    for downloads from Soundcloud.
    """
    msg = email.message_from_string(s)
    if header in msg:
        value = msg.get_param(param, header=header)
        decoded_list = email.header.decode_header(value)
        value = []
        for part, encoding in decoded_list:
            if encoding:
                value.append(part.decode(encoding))
            else:
                value.append(str(part))
        return ''.join(value)

    return None


def get_metadata(url):
    """Get file download metadata

    Returns a (size, type, name) from the given download
    URL. Will use the network connection to determine the
    metadata via the HTTP header fields.
    """
    track_fp = util.urlopen(url)
    headers = track_fp.info()
    filesize = headers['content-length'] or '0'
    filetype = headers['content-type'] or 'application/octet-stream'
    headers_s = '\n'.join('%s:%s' % (k, v) for k, v in list(headers.items()))
    filename = get_param(headers_s) or os.path.basename(os.path.dirname(url))
    track_fp.close()
    return filesize, filetype, filename


class SoundcloudUser(object):
    def __init__(self, username):
        self.username = username
        self.cache = {}

    def get_user_info(self):
        global CONSUMER_KEY
        key = ':'.join((self.username, 'user_info'))

        if key not in self.cache:
            json_url = 'https://api.soundcloud.com/users/%s.json?consumer_key=%s' % (self.username, CONSUMER_KEY)
            logger.debug('get_user_info url: %s', json_url)
            user_info = json.loads(util.urlopen(json_url).read().decode('utf-8'))
            self.cache[key] = user_info

        return self.cache[key]

    def get_coverart(self):
        user_info = self.get_user_info()
        avatar_url = user_info.get('avatar_url', None)
        if avatar_url:
            # Soundcloud API by default returns the URL to "large" artwork - 100x100
            # by replacing "-large" with "-original" in the URL we get unresized files.
            return avatar_url.replace("-large", "-original")
        return avatar_url

    def get_user_id(self):
        user_info = self.get_user_info()
        return user_info.get('id', None)

    def get_username(self):
        user_info = self.get_user_info()
        return user_info.get('username', None)

    def get_tracks(self, feed, channel):
        """Get a generator of tracks from a SC user

        The generator will give you a dictionary for every
        track it can find for its user."""
        global CONSUMER_KEY

        json_url = ('https://api.soundcloud.com/users/%(user)s/%(feed)s.'
                    'json?consumer_key=%'
                    '(consumer_key)s&limit=200&linked_partitioning=1'
                    % {"user": self.get_user_id(),
                       "feed": feed,
                       "consumer_key": CONSUMER_KEY})

        logger.debug('get_tracks url: %s', json_url)

        json_tracks = json.loads(util.urlopen(json_url).read().decode('utf-8'))
        tracks = [track for track in json_tracks['collection'] if track['streamable'] or track['downloadable']]

        try:
            while(json_tracks['next_href'] != ''):
                next_url = json_tracks['next_href']
                logger.debug('get page: %s', next_url)
                json_tracks = json.loads(util.urlopen(next_url).read().decode('utf-8'))
                tracks += [track for track in json_tracks['collection'] if track['streamable'] or track['downloadable']]
        except:
            logger.debug('No pagination/end of pagination for this feed.')

        logger.debug('Starting to add %d tracks, this may take a while.', len(tracks))

        self.cache['episodes'] = { episode.guid:
                                   { "filesize": episode.file_size,
                                     "filetype": episode.mime_type,
                                   } for episode in channel.episodes
                                 }

        read_from_cache = 0
        logger.debug('%d Episodes in database for Soundcloud:%s', len(self.cache['episodes']), self.username)

        for track in tracks:
            # Prefer stream URL (MP3), fallback to download URL
            base_url = track.get('stream_url') if track['streamable'] else track.get('download_url')
            if base_url:
                url = base_url + '?consumer_key=%(consumer_key)s' % {'consumer_key': CONSUMER_KEY}
            else:
                logger.debug('Skipping track with no base_url')
                continue

            track_guid = track.get('permalink', track.get('id'))

            if track_guid not in self.cache['episodes']:
                filesize, filetype, filename = get_metadata(url)
            else:
                filesize = self.cache['episodes'][track_guid]['filesize']
                filetype = self.cache['episodes'][track_guid]['filetype']
                read_from_cache += 1

            artwork_url = track.get('artwork_url')
            if artwork_url:
                artwork_url = artwork_url.replace("-large", "-original")

            yield {
                'title': track.get('title', track.get('permalink')) or ('Unknown track'),
                'link': track.get('permalink_url') or 'https://soundcloud.com/' + self.username,
                'description': track.get('description') or ('No description available'),
                'url': url,
                'file_size': int(filesize),
                'mime_type': filetype,
                'guid': track_guid,
                'published': soundcloud_parsedate(track.get('created_at', None)),
                'total_time': int(track.get('duration') / 1000),
                'episode_art_url' : artwork_url,
            }

        logger.debug('Read %d episodes from %d cached episodes', read_from_cache, len(self.cache['episodes']))


class SoundcloudFeed(object):
    def __init__(self, username):
        self.username = username
        self.sc_user = SoundcloudUser(username)

    def was_updated(self):
        return True

    def get_etag(self, default):
        return default

    def get_modified(self, default):
        return default

    def get_title(self):
        return '%s on Soundcloud' % self.sc_user.get_username()

    def get_image(self):
        return self.sc_user.get_coverart()

    def get_link(self):
        return 'https://soundcloud.com/%s' % self.username

    def get_description(self):
        return 'Tracks published by %s on Soundcloud.' % self.username

    def get_payment_url(self):
        return None

    def get_new_episodes(self, channel):
        return self._get_new_episodes(channel, 'tracks')

    def _get_new_episodes(self, channel, track_type):
        tracks = [t for t in self.sc_user.get_tracks(track_type, channel)]
        existing_guids = dict((episode.guid, episode) for episode in channel.episodes)
        seen_guids = [track['guid'] for track in tracks]
        new_episodes = []

        for track in tracks:
            episode = existing_guids.get(track['guid'])

            if not episode:
                episode = channel.episode_factory(track.items())
                new_episodes.append(episode)
                logger.info('Found new episode: %s', episode.guid)
            else:
                episode.update_from_dict(track)
                logger.info('Updating existing episode: %s', episode.guid)
            episode.save()

        return new_episodes, seen_guids


class SoundcloudFavFeed(SoundcloudFeed):
    def __init__(self, username):
        super(SoundcloudFavFeed, self).__init__(username)

    def get_title(self):
        return '%s\'s favorites on Soundcloud' % self.username

    def get_link(self):
        return 'https://soundcloud.com/%s/favorites' % self.username

    def get_description(self):
        return 'Tracks favorited by %s on Soundcloud.' % self.username

    def get_new_episodes(self, channel):
        return self._get_new_episodes(channel, 'favorites')


@registry.feed_handler.register
def soundcloud_feed_handler(channel, max_episodes, config):
    m = re.match(r'https?://([a-z]+\.)?soundcloud\.com/([^/]+)$', channel.url, re.I)

    if m is not None:
        subdomain, username = m.groups()
        return SoundcloudFeed(username)


@registry.feed_handler.register
def soundcloud_fav_feed_handler(channel, max_episodes, config):
    m = re.match(r'https?://([a-z]+\.)?soundcloud\.com/([^/]+)/favorites', channel.url, re.I)

    if m is not None:
        subdomain, username = m.groups()
        return SoundcloudFavFeed(username)


@registry.url_shortcut.register
def soundcloud_resolve_url_shortcut():
    return {'sc': 'https://soundcloud.com/%s',
            'scfav': 'https://soundcloud.com/%s/favorites'}


@registry.directory.register_instance
class SoundcloudSearchProvider(directory.Provider):
    def __init__(self):
        self.name = 'Soundcloud search'
        self.kind = directory.Provider.PROVIDER_SEARCH
        self.priority = directory.Provider.PRIORITY_SECONDARY_SEARCH

    def on_search(self, query):
        json_url = 'https://api.soundcloud.com/users.json?q=%s&consumer_key=%s' % (urllib.parse.quote(query),
                                                                                  CONSUMER_KEY)
        return [directory.DirectoryEntry(entry['username'], entry['permalink_url'])
                for entry in util.read_json(json_url)]
