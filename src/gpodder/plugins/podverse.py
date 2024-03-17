#
# gpodder.plugins.podverse: podverse.fm directory integration (2024-03-12)
# Copyright (c) 2024, kirbylife <hola@kirbylife.dev>
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
PAGE_SIZE = 20

@registry.directory.register_instance
class PodverseSearchProvider(directory.Provider):
    def __init__(self):
        self.name = 'Podverse search'
        self.kind = directory.Provider.PROVIDER_SEARCH
        self.priority = directory.Provider.PRIORITY_SECONDARY_SEARCH

    def on_search(self, query):
        page = 1
        result_data = []

        while True:
            json_url = "https://api.podverse.fm/api/v1/podcast?page={}&searchTitle={}&sort=top-past-week".format(page, urllib.parse.quote(query))

            json_data, entry_count = util.read_json(json_url)

            if entry_count > 0:
                for entry in json_data:
                    if entry["credentialsRequired"]:
                       continue

                    title = entry["title"]
                    url = entry["feedUrls"][0]["url"]
                    image = entry["imageUrl"]
                    description = entry["description"]

                    result_data.append(directory.DirectoryEntry(title, url, image, -1, description))

            if entry_count < PAGE_SIZE:
                break

            page += 1

        return result_data
