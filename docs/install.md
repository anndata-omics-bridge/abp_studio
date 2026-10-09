# Install

APB Studio runs from a checkout with its sibling packages in neighbouring folders; `uv sync` installs them editable from there.

```bash
git clone https://github.com/anndata-omics-bridge/apb2.git
git clone https://github.com/anndata-omics-bridge/apb-catalog.git
git clone https://github.com/anndata-omics-bridge/apb-fasta.git
git clone https://github.com/anndata-omics-bridge/apb-proteobench.git
git clone https://github.com/anndata-omics-bridge/protein-fasta.git protein_fasta
git clone https://github.com/anndata-omics-bridge/prozor.git
git clone https://github.com/anndata-omics-bridge/abp_studio.git apb_studio
cd apb_studio
uv sync --frozen --extra dev --group docs
```

Export workflows also need [apb-export](https://github.com/anndata-omics-bridge/apb-export) on `PATH`: clone it beside the others and run `uv tool install --editable ../apb-export`. Node is needed only to change the viewers.

The `aggregate` and `aggregate_medpolish` workflows run the private `apb-aggregate` command, which APB Studio does not install. Install it once with `uv tool install --editable ../apb-aggregate` so it is on `PATH`.

The executables declared by the selected workflow must be on `PATH`. The development extra installs the workspace checkouts for local integration testing; Studio invokes them only through subprocesses.

Then acquire fixtures, run a corpus and open the viewer as the [README](https://github.com/anndata-omics-bridge/abp_studio#start) shows.
