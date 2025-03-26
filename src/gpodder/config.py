#
# gPodder: Media and podcast aggregator
# Copyright (c) 2005-2020 Thomas Perl and the gPodder Team
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
#  config.py -- gPodder Configuration Manager
#  Thomas Perl <thp@perli.net>   2007-11-02
#


import gpodder
from gpodder import util

from gpodder import jsonconfig

import os
import shutil
import time
import logging

defaults = {
    # Various limits (downloading, updating, etc..)
    'limit': {
        'bandwidth': {
            'enabled': False,
            'kbps': 500.0,  # maximum kB/s per download
        },
        'downloads': {
            'enabled': True,
            'concurrent': 1,
            'podcast_max_new': 200,       # per podcast download limit same as episode limit
        },
        'episodes': 200,  # max episodes per feed
    },

    # Automatic feed updates, download removal and retry on download timeout
    'auto': {
        'update': {
            'enabled': False,
            'frequency': 20,  # minutes
        },

        'cleanup': {
            'days': 7,
            'played': False,
            'unplayed': False,
            'unfinished': True,
        },

        'retries': 3,  # number of retries when downloads time out
    },

    'fs': {
        'downloads': ''
    },

    'ui': {
        # Settings for the Command-Line Interface
        'cli': {
            'colors': True,
        },

        # Settings for the QML UI
        'qml': {
            'episode_list': {
                'filter_eql': '',
            },
            'playback_speed': {
                'stepSize': 0.1,
                'minimumValue': 0.5,
                'maximumValue': 3.0,
            },
        },
    },

    'plugins': {
        'youtube': {
            'preferred_fmt_id': 18,  # default fmt_id (see fallbacks in youtube.py)
            'preferred_fmt_ids': [],  # for advanced uses (custom fallback sequence)
            'api_key_v3': '',  # API key, register for one at https://developers.google.com/youtube/v3/
        },
        'vimeo': {
            'fileformat': 'hd',  # preferred format (hd, sd, mobile)
        },
    },
}

logger = logging.getLogger(__name__)


def config_value_to_string(config_value):
    config_type = type(config_value)

    if config_type == list:
        return ','.join(map(config_value_to_string, config_value))
    elif config_type in (str, str):
        return config_value
    else:
        return str(config_value)


def string_to_config_value(new_value, old_value):
    config_type = type(old_value)

    if config_type == list:
        return [_f for _f in [x.strip() for x in new_value.split(',')] if _f]
    elif config_type == bool:
        return (new_value.strip().lower() in ('1', 'true'))
    else:
        return config_type(new_value)


class Config(object):
    # Number of seconds after which settings are auto-saved
    WRITE_TO_DISK_TIMEOUT = 60

    def __init__(self, filename='gpodder.json'):
        self.__json_config = jsonconfig.JsonConfig(default=defaults,
                                                   on_key_changed=self._on_key_changed)
        self.__save_thread = None
        self.__filename = filename
        self.__observers = []

        self.load()

        # If there is no configuration file, we create one here (bug 1511)
        if not os.path.exists(self.__filename):
            self.save()

    def add_observer(self, callback):
        """
        Add a callback function as observer. This callback
        will be called when a setting changes. It should
        have this signature:

            observer(name, old_value, new_value)

        The "name" is the setting name, the "old_value" is
        the value that has been overwritten with "new_value".
        """
        if callback not in self.__observers:
            self.__observers.append(callback)
        else:
            logger.warn('Observer already added: %s', repr(callback))

    def remove_observer(self, callback):
        """
        Remove an observer previously added to this object.
        """
        if callback in self.__observers:
            self.__observers.remove(callback)
        else:
            logger.warn('Observer not added: %s', repr(callback))

    def all_keys(self):
        return self.__json_config._keys_iter()

    def schedule_save(self):
        if self.__save_thread is None:
            self.__save_thread = util.run_in_background(self.save_thread_proc, True)

    def save_thread_proc(self):
        time.sleep(self.WRITE_TO_DISK_TIMEOUT)
        if self.__save_thread is not None:
            self.save()

    def close(self):
        # If we have outstanding changes to the config, save them
        if self.__save_thread is not None:
            self.save()

    def save(self, filename=None):
        if filename is None:
            filename = self.__filename

        logger.info('Flushing settings to disk')

        try:
            with util.update_file_safely(filename) as temp_filename:
                with open(temp_filename, 'wt') as fp:
                    fp.write(repr(self.__json_config))
        except Exception as e:
            logger.error('Cannot write settings to %s: %s', filename, e)
            raise

        self.__save_thread = None

    def load(self, filename=None):
        if filename is not None:
            self.__filename = filename

        if os.path.exists(self.__filename):
            try:
                data = open(self.__filename, 'rt').read()
                new_keys_added = self.__json_config._restore(data)
            except:
                logger.warn('Cannot parse config file: %s', self.__filename, exc_info=True)
                new_keys_added = False

            if new_keys_added:
                logger.info('New default keys added - saving config.')
                self.save()

    def toggle_flag(self, name):
        setattr(self, name, not getattr(self, name))

    def get_field(self, name):
        """Get the current value of a field"""
        return self._lookup(name)

    def update_field(self, name, new_value):
        """Update a config field, converting strings to the right types"""
        old_value = self._lookup(name)
        new_value = string_to_config_value(new_value, old_value)
        setattr(self, name, new_value)
        return True

    def _on_key_changed(self, name, old_value, value):
        logger.debug('%s: %s -> %s', name, old_value, value)
        for observer in self.__observers:
            try:
                observer(name, old_value, value)
            except Exception as exception:
                logger.error('Error while calling observer %r: %s', observer, exception,
                             exc_info=True)

        self.schedule_save()

    def __getattr__(self, name):
        return getattr(self.__json_config, name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
            return

        setattr(self.__json_config, name, value)
