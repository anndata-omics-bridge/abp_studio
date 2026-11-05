#!/usr/bin/env fish
# STAGING ON fgcz-r-035: this file alone builds what https://fgcz-ms.uzh.ch/public/apb-studio/
# serves. Its runs, the site copy and the upload are the lines below; nothing else goes there.
# Every other corpus run is in collected_other_options.fish.
#
# Run from the apb_studio folder, with the laptop kept awake:
#   caffeinate -dimsu fish scripts/staging_35.fish
# apb_publish_output and apb_publish_site must be absent: `corpus publish` copies every run of
# the output root and writes only into an empty folder.
# A failed dataset is a report and the script goes on; a failed command stops it before upload.
# Defaults: --format hdf5, --cores 3, --force. --strict refuses a corpus with missing datasets.

test -e apb_publish_output; and echo "apb_publish_output exists: move it away first"; and exit 1
test -e apb_publish_site; and echo "apb_publish_site exists: move it away first"; and exit 1

# conversion: routine in three formats, problems
uv run corpus run routine convert --strict --output-root apb_publish_output; or exit 1
uv run corpus run routine convert --format duckdb --strict --output-root apb_publish_output; or exit 1
uv run corpus run routine convert --format parquet --strict --output-root apb_publish_output; or exit 1
uv run corpus run problems convert --strict --output-root apb_publish_output; or exit 1

# manuscript Figure 5: one dataset at a time
uv run corpus run proteobench_f3 convert_peptidoform_ion --cores 1 --strict --output-root apb_publish_output; or exit 1
uv run corpus run proteobench_f3 convert --cores 1 --strict --output-root apb_publish_output; or exit 1
uv run corpus run large_inputs convert_no_param --cores 1 --strict --output-root apb_publish_output; or exit 1
uv run corpus run large_inputs convert_no_param --format duckdb --cores 1 --strict --output-root apb_publish_output; or exit 1
uv run corpus run large_inputs convert_no_param --format parquet --cores 1 --strict --output-root apb_publish_output; or exit 1

# ProteoBench scoring and pMultiQC: the 197 ProteoBench submissions of proteobench_f3
uv run corpus run proteobench proteobench_pmultiqc --strict --output-root apb_publish_output; or exit 1

# site copy: viewer plus every run above
uv run corpus publish apb_publish_site --output-root apb_publish_output; or exit 1

# upload to fgcz-r-035: the site, then the fixture store beside it as fixtures/
rsync -a --delete --exclude /fixtures/ -e "ssh -l wolski" apb_publish_site/ fgcz-r-035.uzh.ch:/srv/www/htdocs/public/apb-studio/; or exit 1
rsync -a --delete --exclude .DS_Store -e "ssh -l wolski" test_data_download/ fgcz-r-035.uzh.ch:/srv/www/htdocs/public/apb-studio/fixtures/; or exit 1
# macOS rsync (openrsync) ignores --chmod, so make every file readable on the server
ssh -l wolski fgcz-r-035.uzh.ch 'chmod -R u=rwX,go=rX /srv/www/htdocs/public/apb-studio'
