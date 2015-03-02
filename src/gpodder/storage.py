#
# gpodder.storage - JSON-based Database Backend (2013-05-20)
# Copyright (c) 2013, Thomas Perl <m@thp.io>
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


import minidb

from gpodder import model
from gpodder import util

import json
import os
import gzip
import re
import sys

import logging
logger = logging.getLogger(__name__)


class MigrateJSONDBToMiniDB:
    def __init__(self, db):
        self.db = db
        self.jsondb_filename = re.sub(r'\.minidb$', '.jsondb', self.db.filename)

    def _append_podcast(self, podcast):
        # Dummy function to work as drop-in model.Model replacement
        ...

    def migrate(self):
        podcasts = {}
        classes = {
            'podcast': model.PodcastChannel,
            'episode': model.PodcastEpisode,
        }

        if os.path.exists(self.jsondb_filename):
            logger.info('Migrating from jsondb to minidb')
            data = json.loads(str(gzip.open(self.jsondb_filename, 'rb').read(), 'utf-8'))
            for table in ('podcast', 'episode'):
                cls = classes[table]
                for key, item in data[table].items():
                    if table == 'podcast':
                        o = cls(self)
                        podcasts[int(key)] = o
                    elif table == 'episode':
                        if item['podcast_id'] not in podcasts:
                            logger.warn('Skipping orphaned episode: %s (podcast_id=%r)',
                                        item['title'], item['podcast_id'])
                            continue
                        o = cls(podcasts[item['podcast_id']])

                    for k, v in item.items():
                        if k == 'podcast_id':
                            # Don't set the podcast id (will be set automatically)
                            continue

                        if hasattr(o, k):
                            setattr(o, k, v)
                        else:
                            logger.warn('Skipping %s attribute: %s', table, k)

                    o.save()

            os.rename(self.jsondb_filename, self.jsondb_filename + '.migrated')


class Database:
    def __init__(self, filename, debug=False):
        self.filename = filename + '.minidb'

        need_migration = not os.path.exists(self.filename)

        self.db = minidb.Store(self.filename, debug=debug, smartupdate=True)
        self.db.register(model.PodcastEpisode)
        self.db.register(model.PodcastChannel)

        if need_migration:
            try:
                MigrateJSONDBToMiniDB(self).migrate()
            except Exception as e:
                logger.fatal('Could not migrate database: %s', e, exc_info=True)
                self.db.close()
                self.db = None
                util.delete_file(self.filename)
                sys.exit(1)

    def load_podcasts(self, *args):
        return model.PodcastChannel.load(self.db)(*args)

    def load_episodes(self, podcast, *args):
        return model.PodcastEpisode.load(self.db, podcast_id=podcast.id)(*args)

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.commit()
        self.db.close()
