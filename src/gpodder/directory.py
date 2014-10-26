#
# gpodder.directory - Podcast directory and search providers (2014-10-26)
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

import logging

logger = logging.getLogger(__name__)

from gpodder import opml
from gpodder import util


class DirectoryEntry(object):
    def __init__(self, title, url, image=None, subscribers=-1, description=None):
        self.title = title
        self.url = url
        self.image = image
        self.subscribers = subscribers
        self.description = description

class DirectoryTag(object):
    def __init__(self, tag, weight):
        self.tag = tag
        self.weight = weight


class Provider(object):
    PROVIDER_SEARCH, PROVIDER_URL, PROVIDER_FILE, PROVIDER_TAGCLOUD, PROVIDER_STATIC = range(5)

    def __init__(self):
        self.name = ''
        self.kind = self.PROVIDER_SEARCH

    def on_search(self, query):
        # Should return a list of DirectoryEntry objects
        raise NotImplemented()

    def on_url(self, url):
        # Should return a list of DirectoryEntry objects
        raise NotImplemented()

    def on_file(self, filename):
        # Should return a list of DirectoryEntry objects
        raise NotImplemented()

    def on_tag(self, tag):
        # Should return a list of DirectoryEntry objects
        raise NotImplemented()

    def on_static(self):
        # Should return a list of DirectoryEntry objects
        raise NotImplemented()

    def get_tags(self):
        # Should return a list of DirectoryTag objects
        raise NotImplemented()


def directory_entry_from_opml(url):
    return [DirectoryEntry(d['title'], d['url'], description=d['description']) for d in opml.Importer(url).items]

def directory_entry_from_mygpo_json(url):
    return [DirectoryEntry(d['title'], d['url'], d['logo_url'], d['subscribers'], d['description']) for d in util.read_json(url)]

