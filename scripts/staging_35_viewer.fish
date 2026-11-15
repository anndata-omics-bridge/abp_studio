#!/usr/bin/env fish
# VIEWER-ONLY UPDATE OF STAGING ON fgcz-r-035: replaces the corpus viewer, index.html and assets/,
# of https://fgcz-ms.uzh.ch/public/apb-studio/ and leaves the published runs in data/ and the
# fixture store in fixtures/ as staging_35.fish uploaded them. No corpus runs.
#
# Run from the apb_studio folder:
#   fish scripts/staging_35_viewer.fish
# Only for a viewer change that reads the same run files; a change to what a run writes needs
# staging_35.fish.

make build-web; or exit 1

# upload the packaged viewer; --delete removes old hashed bundles, the excludes protect runs and fixtures
rsync -a --delete --exclude /data/ --exclude /fixtures/ --exclude .DS_Store -e "ssh -l wolski" src/apb_studio/corpus_viewer/web/ fgcz-r-035.uzh.ch:/srv/www/htdocs/public/apb-studio/; or exit 1
# macOS rsync (openrsync) ignores --chmod, so make the viewer files readable on the server
ssh -l wolski fgcz-r-035.uzh.ch 'chmod -R u=rwX,go=rX /srv/www/htdocs/public/apb-studio/index.html /srv/www/htdocs/public/apb-studio/assets'
