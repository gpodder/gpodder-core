#
# gpodder.plugins.gpoddernet: gpodder.net directory integration (2014-10-26)
# Copyright (c) 2014, Thomas Perl <m@thp.io>
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
from gpodder import directory

import logging
import urllib.parse

logger = logging.getLogger(__name__)


@registry.directory.register_instance
class GPodderNetSearchProvider(directory.Provider):
    def __init__(self):
        self.name = 'gpodder.net search'
        self.kind = directory.Provider.PROVIDER_SEARCH

    def on_search(self, query):
        return directory.directory_entry_from_mygpo_json('http://gpodder.net/search.json?q=' + urllib.parse.quote(query))

@registry.directory.register_instance
class GPodderRecommendationsProvider(directory.Provider):
    def __init__(self):
        self.name = 'Getting started'
        self.kind = directory.Provider.PROVIDER_STATIC

    def on_static(self):
        return directory.directory_entry_from_opml('http://gpodder.org/directory.opml')

@registry.directory.register_instance
class GPodderNetToplistProvider(directory.Provider):
    def __init__(self):
        self.name = 'gpodder.net Top 50'
        self.kind = directory.Provider.PROVIDER_STATIC

    def on_static(self):
        return directory.directory_entry_from_mygpo_json('http://gpodder.net/toplist/50.json')

@registry.directory.register_instance
class GPodderNetTagsProvider(directory.Provider):
    def __init__(self):
        self.name = 'gpodder.net Tags'
        self.kind = directory.Provider.PROVIDER_TAGCLOUD

    def on_tag(self, tag):
        return directory.directory_entry_from_mygpo_json('http://gpodder.net/api/2/tag/%s/50.json' % urllib.parse.quote(tag))

    def get_tags(self):
        return [DirectoryTag(d['tag'], d['usage']) for d in json.load(util.urlopen('http://gpodder.net/api/2/tags/40.json'))]

