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


class Database:
    def __init__(self, filename, debug=False):
        self.filename = filename + '.minidb'

        self.db = minidb.Store(self.filename, debug=debug, smartupdate=True)
        self.db.register(model.PodcastEpisode)
        self.db.register(model.PodcastChannel)

    def load_podcasts(self, *args):
        return model.PodcastChannel.load(self.db)(*args)

    def load_episodes(self, podcast, *args):
        return model.PodcastEpisode.load(self.db, podcast_id=podcast.id)(*args)

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.commit()
        self.db.close()
