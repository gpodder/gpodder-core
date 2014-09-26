#
# gPodder: Media and podcast aggregator
# Copyright (c) 2005-2014 Thomas Perl and the gPodder Team
# Copyright (c) 2011 Neal H. Walfield
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


#
#  gpodder.model - Core model classes for gPodder (2009-08-13)
#  Based on libpodcasts.py (thp, 2005-10-29)
#

import gpodder
from gpodder import util
from gpodder import coverart
from gpodder import download
from gpodder import registry

import logging
logger = logging.getLogger(__name__)

import os
import re
import glob
import shutil
import time
import datetime
import itertools

import hashlib
import string


class NoHandlerForURL(Exception):
    pass


def fetch_channel(channel, max_episodes):
    for resolver in (registry.feed_handler, registry.fallback_feed_handler):
        feed = resolver.resolve(channel, None, max_episodes)
        if feed is not None:
            return feed

    raise NoHandlerForURL(channel.url)


# Our podcast model:
#
# model -> podcast -> episode -> download/playback
#  podcast.parent == model
#  podcast.children == [episode, ...]
#  episode.parent == podcast
#
# - normally: episode.children = (None, None)
# - downloading: episode.children = (DownloadTask(), None)
# - playback: episode.children = (None, PlaybackTask())

EpisodeColumns = (
    'podcast_id',
    'title',
    'description',
    'url',
    'published',
    'guid',
    'link',
    'file_size',
    'mime_type',
    'state',
    'is_new',
    'archive',
    'download_filename',
    'total_time',
    'current_position',
    'current_position_updated',
    'last_playback',
    'payment_url',
    'chapters',
)

PodcastColumns = (
    'title',
    'url',
    'link',
    'description',
    'cover_url',
    'auth_username',
    'auth_password',
    'http_last_modified',
    'http_etag',
    'auto_archive_episodes',
    'download_folder',
    'pause_subscription',
    'section',
    'payment_url',
    'download_strategy',
    'sync_to_mp3_player',
)


class PodcastModelObject(object):
    """
    A generic base class for our podcast model providing common helper
    and utility functions.
    """
    __slots__ = ('id', 'parent', 'children')

    @classmethod
    def build_from_iterable(cls, iterable, *args):
        """
        Create a new object, passing "args" to the constructor
        and then updating the object with the values from the
        given iterable (should give (key, value) pairs).
        """
        o = cls(*args)

        for k, v in iterable:
            if not hasattr(o, k):
                logger.warn('Unknown attribute: %s', k)
                continue
            setattr(o, k, v)

        o.finalize_built_object()
        return o

    def finalize_built_object(self):
        """
        Carry out any post-build initialization of objects that
        have been built with build_from_iterable()
        """
        pass


class PodcastEpisode(PodcastModelObject):
    """holds data for one object in a channel"""
    MAX_FILENAME_LENGTH = 200

    UPDATE_KEYS = ('title', 'url', 'description', 'link', 'published', 'guid', 'file_size',
                   'payment_url')

    __schema__ = EpisodeColumns
    __slots__ = __schema__

    def __init__(self, channel):
        self.parent = channel
        self.podcast_id = self.parent.id
        self.children = None

        self.id = None
        self.url = ''
        self.title = ''
        self.file_size = 0
        self.mime_type = 'application/octet-stream'
        self.guid = ''
        self.description = ''
        self.link = ''
        self.published = 0
        self.download_filename = None
        self.payment_url = None
        self.chapters = []

        self.state = gpodder.STATE_NORMAL
        self.is_new = True
        self.archive = channel.auto_archive_episodes

        # Time attributes
        self.total_time = 0
        self.current_position = 0
        self.current_position_updated = 0

        # Timestamp of last playback time
        self.last_playback = 0

    @property
    def channel(self):
        return self.parent

    @property
    def db(self):
        return self.parent.parent.db

    @property
    def trimmed_title(self):
        """Return the title with the common prefix trimmed"""
        # Minimum amount of leftover characters after trimming. This
        # avoids things like "Common prefix 123" to become just "123".
        # If there are LEFTOVER_MIN or less characters after trimming,
        # the original title will be returned without trimming.
        LEFTOVER_MIN = 5

        # "Podcast Name - Title" and "Podcast Name: Title" -> "Title"
        for postfix in (' - ', ': '):
            prefix = self.parent.title + postfix
            if (self.title.startswith(prefix) and
                    len(self.title)-len(prefix) > LEFTOVER_MIN):
                return self.title[len(prefix):]

        regex_patterns = [
            # "Podcast Name <number>: ..." -> "<number>: ..."
            r'^%s (\d+: .*)' % re.escape(self.parent.title),

            # "Episode <number>: ..." -> "<number>: ..."
            r'Episode (\d+:.*)',
        ]

        for pattern in regex_patterns:
            if re.match(pattern, self.title):
                title = re.sub(pattern, r'\1', self.title)
                if len(title) > LEFTOVER_MIN:
                    return title

        # "#001: Title" -> "001: Title"
        if (not self.parent._common_prefix and re.match('^#\d+: ', self.title) and
                len(self.title)-1 > LEFTOVER_MIN):
            return self.title[1:]

        if (self.parent._common_prefix is not None and
                self.title.startswith(self.parent._common_prefix) and
                len(self.title)-len(self.parent._common_prefix) > LEFTOVER_MIN):
            return self.title[len(self.parent._common_prefix):]

        return self.title

    def download(self, progress_callback):
        task = download.DownloadTask(self)
        task.add_progress_callback(progress_callback)
        task.status = download.DownloadTask.QUEUED
        result = task.run()
        task.recycle()
        return result

    def download_progress(self):
        task = self.download_task
        if task is None:
            return 0.0
        elif not self.downloading:
            return 0.0

        return task.progress

    def _set_download_task(self, download_task):
        self.children = download_task

    def _get_download_task(self):
        return self.children

    download_task = property(_get_download_task, _set_download_task)

    @property
    def downloading(self):
        task = self.download_task
        if task is None:
            return False

        return task.status in (download.DownloadTask.DOWNLOADING,
                               download.DownloadTask.QUEUED,
                               download.DownloadTask.PAUSED)

    def save(self):
        self.db.save_episode(self)

    def on_downloaded(self, filename):
        self.state = gpodder.STATE_DOWNLOADED
        self.is_new = True
        self.file_size = os.path.getsize(filename)
        self.save()

    def playback_mark(self):
        self.is_new = False
        self.last_playback = int(time.time())
        self.save()

    def is_fresh(self):
        return self.is_new and self.state == gpodder.STATE_NORMAL

    def age_in_days(self):
        return util.file_age_in_days(self.local_filename(create=False, check_only=True))

    def delete(self):
        filename = self.local_filename(create=False, check_only=True)
        if filename is not None:
            util.delete_file(filename)

        self.state = gpodder.STATE_DELETED
        self.is_new = False
        self.save()

    def get_playback_url(self, allow_partial=False):
        """Local (or remote) playback/streaming filename/URL

        Returns either the local filename or a streaming URL that
        can be used to playback this episode.

        Also returns the filename of a partially downloaded file
        in case partial (preview) playback is desired.
        """
        url = self.local_filename(create=False)

        if (allow_partial and url is not None and
                os.path.exists(url + '.partial')):
            return url + '.partial'

        if url is None or not os.path.exists(url):
            url = registry.download_url.resolve(self, self.url, self.parent.model.core.config)

        return url

    def find_unique_file_name(self, filename, extension):
        # Remove leading and trailing whitespace + dots (to avoid hidden files)
        filename = filename.strip('.' + string.whitespace) + extension

        # Existing download folder names must not be used
        existing_names = [episode.download_filename for episode in self.parent.episodes
                          if episode is not self]

        for name in util.generate_names(filename):
            if name not in existing_names:
                return name

    def local_filename(self, create, force_update=False, check_only=False, template=None,
                       return_wanted_filename=False):
        """Get (and possibly generate) the local saving filename

        Pass create=True if you want this function to generate a
        new filename if none exists. You only want to do this when
        planning to create/download the file after calling this function.

        Normally, you should pass create=False. This will only
        create a filename when the file already exists from a previous
        version of gPodder (where we used md5 filenames). If the file
        does not exist (and the filename also does not exist), this
        function will return None.

        If you pass force_update=True to this function, it will try to
        find a new (better) filename and move the current file if this
        is the case. This is useful if (during the download) you get
        more information about the file, e.g. the mimetype and you want
        to include this information in the file name generation process.

        If check_only=True is passed to this function, it will never try
        to rename the file, even if would be a good idea. Use this if you
        only want to check if a file exists.

        If "template" is specified, it should be a filename that is to
        be used as a template for generating the "real" filename.

        The generated filename is stored in the database for future access.

        If return_wanted_filename is True, the filename will not be written to
        the database, but simply returned by this function (for use by the
        "import external downloads" feature).
        """
        if self.download_filename is None and (check_only or not create):
            return None

        ext = self.extension(may_call_local_filename=False)

        if not check_only and (force_update or not self.download_filename):
            # Avoid and catch gPodder bug 1440 and similar situations
            if template == '':
                logger.warn('Empty template. Report this podcast URL %s', self.channel.url)
                template = None

            # Try to find a new filename for the current file
            if template is not None:
                # If template is specified, trust the template's extension
                episode_filename, ext = os.path.splitext(template)
            else:
                episode_filename, _ = util.filename_from_url(self.url)
            fn_template = util.sanitize_filename(episode_filename, self.MAX_FILENAME_LENGTH)

            if 'redirect' in fn_template and template is None:
                # This looks like a redirection URL - force URL resolving!
                logger.warn('Looks like a redirection to me: %s', self.url)

                try:
                    auth_url = self.channel.authenticate_url(self.url)
                    resolved_url = util.urlopen(auth_url).geturl()

                    logger.info('Redirection resolved to: %s', resolved_url)
                    episode_filename, _ = util.filename_from_url(resolved_url)
                    fn_template = util.sanitize_filename(episode_filename, self.MAX_FILENAME_LENGTH)
                except Exception as e:
                    logger.warn('Cannot resolve redirection for %s', self.url, exc_info=True)

            sanitized_title = util.sanitize_filename(self.title, self.MAX_FILENAME_LENGTH)
            if fn_template == 'stream' and sanitized_title:
                fn_template = sanitized_title
            fn_template = registry.episode_basename.resolve(self, fn_template, sanitized_title)

            # If the basename is empty, use the md5 hexdigest of the URL
            if not fn_template or fn_template.startswith('redirect.'):
                logger.error('Report this feed: Podcast %s, episode %s', self.channel.url, self.url)
                fn_template = hashlib.md5(self.url).hexdigest()

            # Find a unique filename for this episode
            wanted_filename = self.find_unique_file_name(fn_template, ext)

            if return_wanted_filename:
                # return the calculated filename without updating the database
                return wanted_filename

            # The old file exists, but we have decided to want a different filename
            if self.download_filename and wanted_filename != self.download_filename:
                # there might be an old download folder crawling around - move it!
                new_file_name = os.path.join(self.channel.save_dir, wanted_filename)
                old_file_name = os.path.join(self.channel.save_dir, self.download_filename)
                if os.path.exists(old_file_name) and not os.path.exists(new_file_name):
                    logger.info('Renaming %s => %s', old_file_name, new_file_name)
                    os.rename(old_file_name, new_file_name)
                elif force_update and not os.path.exists(old_file_name):
                    # When we call force_update, the file might not yet exist when we
                    # call it from the downloading code before saving the file
                    logger.info('Choosing new filename: %s', new_file_name)
                else:
                    logger.warn('%s exists or %s does not', new_file_name, old_file_name)
                logger.info('Updating filename of %s to "%s".', self.url, wanted_filename)
            elif self.download_filename is None:
                logger.info('Setting download filename: %s', wanted_filename)
            self.download_filename = wanted_filename
            self.save()

        return os.path.join(self.channel.save_dir, self.download_filename)

    def extension(self, may_call_local_filename=True):
        filename, ext = util.filename_from_url(self.url)
        if may_call_local_filename:
            filename = self.local_filename(create=False)
            if filename is not None:
                filename, ext = os.path.splitext(filename)
        # if we can't detect the extension from the url fallback on the mimetype
        if ext == '' or util.file_type_by_extension(ext) is None:
            ext = util.extension_from_mimetype(self.mime_type)
        return ext

    def file_type(self):
        resolved_type = registry.content_type.resolve(self, None)
        if resolved_type is not None:
            return resolved_type

        return util.file_type_by_extension(self.extension())

    @property
    def sortdate(self):
        dt = datetime.datetime.fromtimestamp(self.published)
        return dt.strftime('%Y-%m-%d')

    def is_finished(self):
        """Return True if this episode is considered "finished playing"

        An episode is considered "finished" when there is a
        current position mark on the track, and when the
        current position is greater than 99 percent of the
        total time or inside the last 10 seconds of a track.
        """
        return (self.current_position > 0 and self.total_time > 0 and
                (self.current_position + 10 >= self.total_time or
                 self.current_position >= self.total_time*.99))

    def report_playback_event(self, position_from, position_to, duration):
        self.current_position = position_to
        self.total_time = duration
        self.current_position_updated = int(time.time())
        self.save()

    def update_from(self, episode):
        for k in self.UPDATE_KEYS:
            setattr(self, k, getattr(episode, k))

    def update_from_dict(self, episode_dict):
        for k in self.UPDATE_KEYS:
            if k in episode_dict:
                setattr(self, k, episode_dict[k])


class PodcastChannel(PodcastModelObject):
    __schema__ = PodcastColumns
    __slots__ = __schema__ + ('_common_prefix', '_updating')

    UNICODE_TRANSLATE = {ord('ö'): 'o', ord('ä'): 'a', ord('ü'): 'u'}

    # Enumerations for download strategy
    STRATEGY_DEFAULT, STRATEGY_LATEST = list(range(2))

    MAX_FOLDERNAME_LENGTH = 60
    SECONDS_PER_WEEK = 7*24*60*60
    EpisodeClass = PodcastEpisode

    def finalize_built_object(self):
        if self.id:
            self.children = list(sorted(self.db.load_episodes(self, self.episode_factory),
                                        key=lambda e: (e.published, e.id), reverse=True))
            self._determine_common_prefix()

    def __init__(self, model):
        self.parent = model
        self.children = []

        self.id = None
        self.url = None
        self.title = ''
        self.link = ''
        self.description = ''
        self.cover_url = None
        self.payment_url = None

        self.auth_username = ''
        self.auth_password = ''

        self.http_last_modified = None
        self.http_etag = None

        self.auto_archive_episodes = False
        self.download_folder = None
        self.pause_subscription = False

        self.section = 'other'
        self._common_prefix = None
        self._updating = False
        self.download_strategy = PodcastChannel.STRATEGY_DEFAULT

    @property
    def model(self):
        return self.parent

    @property
    def db(self):
        return self.parent.db

    @property
    def episodes(self):
        return self.children

    def rewrite_url(self, new_url):
        new_url = self.model.normalize_feed_url(new_url)
        if new_url is None:
            return None

        self.url = new_url
        self.http_etag = None
        self.http_last_modified = None
        self.save()
        return new_url

    def check_download_folder(self):
        """Check the download folder for externally-downloaded files

        This will try to assign downloaded files with episodes in the
        database.

        This will also cause missing files to be marked as deleted.
        """
        known_files = set()

        for episode in self.get_episodes(gpodder.STATE_DOWNLOADED):
            if episode.state == gpodder.STATE_DOWNLOADED:
                filename = episode.local_filename(create=False)
                if not os.path.exists(filename):
                    # File has been deleted by the user - simulate a
                    # delete event (also marks the episode as deleted)
                    logger.debug('Episode deleted: %s', filename)
                    episode.delete()
                    continue

                known_files.add(filename)

        existing_files = set(filename for filename in glob.glob(os.path.join(self.save_dir, '*'))
                             if not filename.endswith('.partial'))

        ignore_files = ['folder'+ext for ext in coverart.CoverDownloader.EXTENSIONS]

        external_files = existing_files.difference(list(known_files) +
                                                   [os.path.join(self.save_dir, ignore_file)
                                                    for ignore_file in ignore_files])
        if not external_files:
            return

        all_episodes = self.episodes

        for filename in external_files:
            found = False

            basename = os.path.basename(filename)
            existing = [e for e in all_episodes if e.download_filename == basename]
            if existing:
                existing = existing[0]
                logger.info('Importing external download: %s', filename)
                existing.on_downloaded(filename)
                continue

            for episode in all_episodes:
                wanted_filename = episode.local_filename(create=True, return_wanted_filename=True)
                if basename == wanted_filename:
                    logger.info('Importing external download: %s', filename)
                    episode.download_filename = basename
                    episode.on_downloaded(filename)
                    found = True
                    break

                wanted_base, wanted_ext = os.path.splitext(wanted_filename)
                target_base, target_ext = os.path.splitext(basename)
                if wanted_base == target_base:
                    # Filenames only differ by the extension
                    wanted_type = util.file_type_by_extension(wanted_ext)
                    target_type = util.file_type_by_extension(target_ext)

                    # If wanted type is None, assume that we don't know
                    # the right extension before the download (e.g. YouTube)
                    # if the wanted type is the same as the target type,
                    # assume that it's the correct file
                    if wanted_type is None or wanted_type == target_type:
                        logger.info('Importing external download: %s', filename)
                        episode.download_filename = basename
                        episode.on_downloaded(filename)
                        found = True
                        break

            if not found:
                logger.warn('Unknown external file: %s', filename)

    @classmethod
    def sort_key(cls, podcast):
        return re.sub('^the ', '', podcast.title.lower()).translate(cls.UNICODE_TRANSLATE)

    @classmethod
    def load(cls, model, url, create=True, authentication_tokens=None):
        for podcast in model.get_podcasts():
            if podcast.url == url:
                return podcast

        if create:
            tmp = cls(model)
            tmp.url = url
            if authentication_tokens is not None:
                tmp.auth_username = authentication_tokens[0]
                tmp.auth_password = authentication_tokens[1]

            # Save podcast, so it gets an ID assigned before
            # updating the feed and adding saving episodes
            tmp.save()

            try:
                tmp.update()
            except Exception as e:
                logger.debug('Fetch failed. Removing buggy feed.')
                tmp.unsubscribe()
                raise

            # Determine the section in which this podcast should appear
            tmp.section = tmp._get_content_type()

            # Determine a new download folder now that we have the title
            tmp.get_save_dir(force_new=True)

            # Mark episodes as downloaded if files already exist (bug 902)
            tmp.check_download_folder()

            # Determine common prefix of episode titles
            tmp._determine_common_prefix()

            tmp.save()

            return tmp

    def episode_factory(self, iterable):
        """
        This function takes an iterable containing (key, value) pairs for
        episodes and returns a new PodcastEpisode object that is connected
        to this object.

        Returns: A new PodcastEpisode object
        """
        return self.EpisodeClass.build_from_iterable(iterable, self)

    def _consume_updated_title(self, new_title):
        # Replace multi-space and newlines with single space (Maemo bug 11173)
        new_title = re.sub('\s+', ' ', new_title).strip()

        # Only update the podcast-supplied title when we
        # don't yet have a title, or if the title is the
        # feed URL (e.g. we didn't find a title before).
        if not self.title or self.title == self.url:
            self.title = registry.podcast_title.resolve(self, new_title, new_title)

    def _consume_metadata(self, title, link, description, cover_url, payment_url):
        self._consume_updated_title(title)
        self.link = link
        self.description = description
        self.cover_url = cover_url
        self.payment_url = payment_url
        self.save()

    def _consume_custom_feed(self, custom_feed):
        if not custom_feed.was_updated():
            return

        self._consume_metadata(custom_feed.get_title(),
                               custom_feed.get_link(),
                               custom_feed.get_description(),
                               custom_feed.get_image(),
                               custom_feed.get_payment_url())

        self.http_etag = custom_feed.get_etag(self.http_etag)
        self.http_last_modified = custom_feed.get_modified(self.http_last_modified)

        new_episodes, seen_guids = custom_feed.get_new_episodes(self)

        # Remove "unreachable" episodes - episodes that have not been
        # downloaded and that the feed does not list as downloadable anymore
        # Keep episodes that are currently being downloaded, though (bug 1534)
        if self.id is not None:
            episodes_to_purge = [episode for episode in self.children
                                 if episode.state != gpodder.STATE_DOWNLOADED and
                                 episode.guid not in seen_guids and not episode.downloading]

            for episode in episodes_to_purge:
                logger.debug('Episode removed from feed: %s (%s)', episode.title, episode.guid)
                self.db.delete_episode(episode)
                self.children.remove(episode)

        # Get most recent published of all episodes
        last_published = 0
        for episode in self.episodes:
            if episode.published > last_published:
                last_published = episode.published

        # Mark newly-found episodes as old in certain cases
        new_episodes.sort(key=lambda e: e.published, reverse=True)
        new_episodes_count = 0
        for episode in new_episodes:
            # Workaround for bug 340: If the episode has been
            # published earlier than one week before the most
            # recent existing episode, do not mark it as new.
            if episode.published < last_published - self.SECONDS_PER_WEEK:
                logger.debug('Episode with old date: %s', episode.title)
                episode.is_new = False
                episode.save()

            if episode.is_new:
                new_episodes_count += 1

                # Only allow a certain number of new episodes per update
                if (self.download_strategy == PodcastChannel.STRATEGY_LATEST
                        and new_episodes_count > 1):
                    episode.is_new = False
                    episode.save()

        # Add new episodes to children
        self.children.extend(new_episodes)

        # Sort episodes by pubdate, descending
        self.children.sort(key=lambda e: e.published, reverse=True)

    def update(self):
        if self._updating:
            logger.warn('Ignoring call to update() while already in progress')
            return

        self._updating = True
        try:
            max_episodes = self.model.core.config.limit.episodes
            old_url = self.url
            result = fetch_channel(self, max_episodes)
            if self.url != old_url:
                logger.info('URL updated: {} -> {}'.format(old_url, self.url))
            self._consume_custom_feed(result)

            # Download the cover art if it's not yet available
            self.model.core.cover_downloader.get_cover(self, download=True)

            self.save()

            # Re-determine the common prefix for all episodes
            self._determine_common_prefix()
        finally:
            self._updating = False

    def unsubscribe(self):
        self.remove_downloaded()
        self.db.delete_podcast(self)
        self.model._remove_podcast(self)

    def save(self):
        if self.download_folder is None:
            self.get_save_dir()

        self.db.save_podcast(self)
        self.model._append_podcast(self)

    def get_statistics(self):
        assert self.id

        total = len(self.episodes)

        deleted, new, downloaded, unplayed = 0, 0, 0, 0
        for episode in self.episodes:
            if episode.state == gpodder.STATE_DELETED:
                deleted += 1
            elif episode.state == gpodder.STATE_NORMAL:
                if episode.is_new:
                    new += 1
            elif episode.state == gpodder.STATE_DOWNLOADED:
                downloaded += 1
                if episode.is_new:
                    unplayed += 1

        return (total, deleted, new, downloaded, unplayed)

    @property
    def group_by(self):
        if not self.section:
            self.section = self._get_content_type()
            self.save()

        return self.section

    def _get_content_type(self):
        audio, video, other = 0, 0, 0
        for episode in self.episodes:
            content_type = episode.file_type()
            if content_type == 'audio':
                audio += 1
            elif content_type == 'video':
                video += 1
            else:
                other += 1

        if audio >= video:
            return 'audio'
        elif video > other:
            return 'video'

        return 'other'

    def authenticate_url(self, url):
        return util.url_add_authentication(url, self.auth_username, self.auth_password)

    def rename(self, new_title):
        new_title = new_title.strip()
        if self.title == new_title:
            return

        new_folder_name = self.find_unique_folder_name(new_title)
        if new_folder_name and new_folder_name != self.download_folder:
            new_folder = os.path.join(self.model.core.downloads, new_folder_name)
            old_folder = os.path.join(self.model.core.downloads, self.download_folder)
            if os.path.exists(old_folder):
                if not os.path.exists(new_folder):
                    # Old folder exists, new folder does not -> simply rename
                    logger.info('Renaming %s => %s', old_folder, new_folder)
                    os.rename(old_folder, new_folder)
                else:
                    # Both folders exist -> move files and delete old folder
                    logger.info('Moving files from %s to %s', old_folder, new_folder)
                    for file in glob.glob(os.path.join(old_folder, '*')):
                        shutil.move(file, new_folder)
                    logger.info('Removing %s', old_folder)
                    shutil.rmtree(old_folder, ignore_errors=True)
            self.download_folder = new_folder_name

        self.title = new_title
        self.save()

    def _determine_common_prefix(self):
        # We need at least 2 episodes for the prefix to be "common" ;)
        if len(self.children) < 2:
            self._common_prefix = ''
            return

        prefix = os.path.commonprefix([x.title for x in self.children])
        # The common prefix must end with a space - otherwise it's not
        # on a word boundary, and we might end up chopping off too much
        if prefix and prefix[-1] != ' ':
            prefix = prefix[:prefix.rfind(' ')+1]

        self._common_prefix = prefix

    def get_episodes(self, state):
        return [e for e in self.children if e.state == state]

    def find_unique_folder_name(self, download_folder):
        # Remove trailing dots to avoid errors on Windows (bug 600)
        # Also remove leading dots to avoid hidden folders on Linux
        download_folder = download_folder.strip('.' + string.whitespace)

        # Existing download folder names must not be used
        existing_names = [podcast.download_folder for podcast in self.model.get_podcasts()
                          if podcast is not self]

        for folder_name in util.generate_names(download_folder):
            if folder_name not in existing_names:
                return folder_name

    def get_save_dir(self, force_new=False):
        if self.download_folder is None or force_new:
            # we must change the folder name, because it has not been set manually
            fn_template = util.sanitize_filename(self.title, self.MAX_FOLDERNAME_LENGTH)

            if not fn_template:
                fn_template = util.sanitize_filename(self.url, self.MAX_FOLDERNAME_LENGTH)

            # Find a unique folder name for this podcast
            download_folder = self.find_unique_folder_name(fn_template)

            # Try renaming the download folder if it has been created previously
            if self.download_folder is not None:
                old_folder = os.path.join(self.model.core.downloads, self.download_folder)
                new_folder = os.path.join(self.model.core.downloads, download_folder)
                try:
                    os.rename(old_folder, new_folder)
                except Exception as ex:
                    logger.info('Cannot rename old download folder: %s', old_folder, exc_info=True)

            logger.info('Updating download_folder of %s to %s', self.url, download_folder)
            self.download_folder = download_folder
            self.save()

        save_dir = os.path.join(self.model.core.downloads, self.download_folder)

        # Create save_dir if it does not yet exist
        if not util.make_directory(save_dir):
            logger.error('Could not create save_dir: %s', save_dir)

        return save_dir

    save_dir = property(fget=get_save_dir)

    def remove_downloaded(self):
        shutil.rmtree(self.save_dir, True)

    @property
    def cover_file(self):
        return os.path.join(self.save_dir, 'folder')


class Model(object):
    PodcastClass = PodcastChannel

    def __init__(self, core):
        self.core = core
        self.db = self.core.db
        self.children = None

    def _append_podcast(self, podcast):
        if podcast not in self.children:
            self.children.append(podcast)

    def _remove_podcast(self, podcast):
        self.children.remove(podcast)

    def podcast_factory(self, iterable):
        return self.PodcastClass.build_from_iterable(iterable, self)

    def get_podcasts(self):
        if self.children is None:
            self.children = self.db.load_podcasts(self.podcast_factory)

            # Check download folders for changes (bug 902)
            for podcast in self.children:
                podcast.check_download_folder()

        return self.children

    def load_podcast(self, url, create=True, authentication_tokens=None):
        assert all(url != podcast.url for podcast in self.get_podcasts())
        return self.PodcastClass.load(self, url, create, authentication_tokens)

    def get_prefixes(self):
        return {k: v for s in registry.url_shortcut.each() for k, v in s.items()}

    def normalize_feed_url(self, url):
        for prefix, expansion in self.get_prefixes().items():
            if url.startswith(prefix + ':'):
                old_url = url
                url = expansion % (url[len(prefix) + 1:],)
                logger.info('Expanding prefix {} -> {}'.format(old_url, url))
                break

        return util.normalize_feed_url(url)

    @classmethod
    def podcast_sort_key(cls, podcast):
        return cls.PodcastClass.sort_key(podcast)

    @classmethod
    def episode_sort_key(cls, episode):
        return episode.published

    @classmethod
    def sort_episodes_by_pubdate(cls, episodes, reverse=False):
        """Sort a list of PodcastEpisode objects chronologically

        Returns a iterable, sorted sequence of the episodes
        """
        return sorted(episodes, key=cls.episode_sort_key, reverse=reverse)
