# Example post-download extension script for gPodder 4
# To test this, you need to set the GPODDER_ADD_PLUGINS environment
# variable and make sure this folder is in your PYTHONPATH:
# env PYTHONPATH=examples GPODDER_ADD_PLUGINS=after_download bin/gpo

from gpodder import registry

@registry.after_download.register
def on_episode_downloaded(episode):
    print('Downloaded episode: {}'.format(episode.title))
