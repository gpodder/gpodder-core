#
# gpodder.coverart - Unified cover art downloading module (2012-03-04)
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

import logging
logger = logging.getLogger(__name__)

from gpodder import util
from gpodder import registry

import os


class CoverDownloader(object):
    # File name extension dict, lists supported cover art extensions
    # Values: functions that check if some data is of that file type
    SUPPORTED_EXTENSIONS = {
        '.png': lambda d: d.startswith(b'\x89PNG\r\n\x1a\n\x00'),
        '.jpg': lambda d: d.startswith(b'\xff\xd8'),
        '.gif': lambda d: d.startswith(b'GIF89a') or d.startswith(b'GIF87a'),
    }

    EXTENSIONS = list(SUPPORTED_EXTENSIONS.keys())

    # Low timeout to avoid unnecessary hangs of GUIs
    TIMEOUT = 5

    def __init__(self, core):
        self.core = core

    def get_cover(self, podcast, download=False, episode = None):
        if episode != None:
            # Get episode art.
            filename = episode.art_file
            cover_url = episode.episode_art_url
            if cover_url is None:
                return None
        else:
            # Get podcast cover.
            filename = podcast.cover_file
            cover_url = podcast.cover_url

        username = podcast.auth_username
        password = podcast.auth_password

        # Return already existing files
        if os.path.exists(filename):
            return filename

        for extension in self.EXTENSIONS:
            if os.path.exists(filename + extension):
                return filename + extension

        # If allowed to download files, do so here
        if download:
            cover_url = registry.cover_art.resolve(podcast, cover_url)

            if not cover_url:
                return None

            # We have to add username/password, because password-protected
            # feeds might keep their cover art also protected (bug 1521)
            cover_url = util.url_add_authentication(cover_url, username, password)

            try:
                logger.info('Downloading cover art: %s', cover_url)
                data = util.urlopen(cover_url, timeout=self.TIMEOUT).read()
            except Exception as e:
                logger.warn('Cover art download failed: %s', e)
                return None

            try:
                extension = None

                fname, ext = os.path.splitext(filename)

                # Check if an extension is part of the filename and that it matches the filetype
                if ext != None and ext != '' :
                    ext_unchanged = ext
                    # Assume last part of filename parts is extension
                    ext = ext.lower()
                    # Deal with alternative extensions for supported format,
                    # should more cases need to be added a mapping dictionary can be created.
                    if ext == '.jpeg':
                        ext = '.jpg'
                    if ext in self.SUPPORTED_EXTENSIONS:
                        if self.SUPPORTED_EXTENSIONS[ext](data):
                            filename = fname
                            extension = ext_unchanged
                # Filename did not include an extension or the extension did not match the filetype
                if extension is None:
                    for filetype, check in list(self.SUPPORTED_EXTENSIONS.items()):
                        if check(data):
                            extension = filetype
                            break

                if extension is None:
                    msg = 'Unknown file type: %s (%r)' % (cover_url, data[:6])
                    raise ValueError(msg)

                # Successfully downloaded the cover art - save it!
                with util.update_file_safely(filename + extension) as temp_filename:
                    with open(temp_filename, 'wb') as fp:
                        fp.write(data)

                return filename + extension
            except Exception as e:
                logger.warn('Cannot save cover art', exc_info=True)

        return None
