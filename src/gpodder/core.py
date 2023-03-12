#
# gpodder.core - Common functionality used by all UIs (2011-02-06)
# Copyright (c) 2011-2013, Thomas Perl <m@thp.io>
# Copyright (c) 2011, Neal H. Walfield <neal@gnu.org>
# Copyright (c) 2012, Bernd Schlapsi <brot@gmx.info>
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
from gpodder import config
from gpodder import storage
from gpodder import coverart
from gpodder import model
from gpodder import log

import os
import logging
import socket


class Core(object):
    def __init__(self,
                 config_class=config.Config,
                 database_class=storage.Database,
                 model_class=model.Model,
                 verbose=True,
                 progname='gpodder',
                 stdout=False):
        self._set_socket_timeout()

        home = os.path.expanduser('~')

        xdg_data_home = os.environ.get('XDG_DATA_HOME', os.path.join(home, '.local', 'share'))
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.join(home, '.config'))
        xdg_cache_home = os.environ.get('XDG_CACHE_HOME', os.path.join(home, '.cache'))

        self.data_home = os.path.join(xdg_data_home, progname)
        self.config_home = os.path.join(xdg_config_home, progname)
        self.cache_home = os.path.join(xdg_cache_home, progname)

        # Use $GPODDER_HOME to set a fixed config and data folder
        if 'GPODDER_HOME' in os.environ:
            home = os.environ['GPODDER_HOME']
            self.data_home = self.config_home = self.cache_home = home

        # Setup logging
        log.setup(self.cache_home, verbose, stdout)
        self.logger = logging.getLogger(__name__)

        config_file = os.path.join(self.config_home, 'Settings.json')
        database_file = os.path.join(self.data_home, 'Database')
        # Downloads go to <data_home> or $GPODDER_DOWNLOAD_DIR
        self.downloads = os.environ.get('GPODDER_DOWNLOAD_DIR', os.path.join(self.data_home))

        # Initialize the gPodder home directories
        util.make_directory(self.data_home)
        util.make_directory(self.config_home)

        # Open the database and configuration file
        self.db = database_class(database_file, verbose)
        self.model = model_class(self)
        self.config = config_class(config_file)

        # Load installed/configured plugins
        self._load_plugins()

        self.cover_downloader = coverart.CoverDownloader(self)

    def _set_socket_timeout(self):
        # Set up socket timeouts to fix bug 174
        SOCKET_TIMEOUT = 60
        socket.setdefaulttimeout(SOCKET_TIMEOUT)

    def _load_plugins(self):
        # Plugins to load by default
        DEFAULT_PLUGINS = [
            # Custom handlers (tried in order, put most specific first)
            #'gpodder.plugins.soundcloud',
            'gpodder.plugins.itunes',
            'gpodder.plugins.youtube',
            'gpodder.plugins.vimeo',

            # Directory plugins
            'gpodder.plugins.gpoddernet',

            # Fallback handlers (catch-all)
            'gpodder.plugins.podcast',
        ]

        PLUGINS = os.environ.get('GPODDER_PLUGINS', None)
        if PLUGINS is None:
            PLUGINS = DEFAULT_PLUGINS
        else:
            PLUGINS = PLUGINS.split()
        ADD_PLUGINS = os.environ.get('GPODDER_ADD_PLUGINS', None)
        if ADD_PLUGINS is not None:
            PLUGINS += ADD_PLUGINS.split()

        for plugin in PLUGINS:
            try:
                __import__(plugin)
            except Exception as e:
                self.logger.warn('Cannot load plugin "%s": %s', plugin, e, exc_info=True)

    def save(self):
        # XXX: Although the function is called close(), this actually doesn't
        # close the DB, just saves the current state to disk
        self.db.commit()

    def shutdown(self):
        self.logger.info('Shutting down core')

        # Close the configuration and store outstanding changes
        self.config.close()

        # Close the database and store outstanding changes
        self.db.close()
