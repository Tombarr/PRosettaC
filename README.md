# PRosettaC — Docker edition

A containerized setup for [PRosettaC](https://github.com/LondonLab/PRosettaC)
that runs on any machine with Docker, without manually installing Rosetta,
PatchDock, or an HPC scheduler. The original HPC install still works — see
[Native install](#native-install-hpc--no-docker).

## What this fork changes

- **Dockerfile + docker-compose.yml** for a one-command build.
- **`cluster/Local`** — new scheduler backend that runs batches inline on a
  single box, so the container doesn't need PBS/SGE/SLURM.
- **`docker/fetch-patchdock.sh`** — runtime downloader that prompts for the
  PatchDock license info (name, affiliation, email) and installs PatchDock
  on first run. Cached via a bind-mounted volume.
- **Rosetta sourcing** — compiled binary + database pulled from the official
  `rosettacommons/rosetta` image; Python helper scripts
  (`molfile_to_params.py`, `clean_pdb.py`) sparse-checked-out from the public
  RosettaCommons repos at pinned commit SHAs.
- **`ROSETTA3_HOME`** env var (with `ROSETTA_FOL` fallback) so the image
  works under Apple Rosetta 2 on Apple Silicon, which rejects any process
  that sets an unknown `ROSETTA_*` env var.
- **Compatibility patches** to `protac_lib.py`, `utils.py`, and `auto.py`
  for newer RDKit (2024+) and OpenBabel 3 — see the
  [patch notes](#compatibility-patches) below.
- **Sample inputs** under [`examples/`](examples/) for two landmark PROTAC
  systems (MZ1 / VHL–BRD4 and dBET6 / CRBN–BRD4) with `fetch_inputs.sh`
  scripts that pull SMILES from PubChem.

## Quick start

```bash
docker build -t prosettac .

mkdir -p patchdock_cache work
cp YourProtac_params.txt YourInputs.* work/
```

Interactive — prompts for the PatchDock license on first run:

```bash
docker run --rm -it \
  -v "$PWD/patchdock_cache:/opt/patchdock" \
  -v "$PWD/work:/work" \
  prosettac auto.py YourProtac_params.txt
```

Non-interactive (CI/batch):

```bash
docker run --rm \
  -e PATCHDOCK_FULLNAME="Jane Doe" \
  -e PATCHDOCK_AFFILIATION="Example University" \
  -e PATCHDOCK_EMAIL="jane@example.edu" \
  -v "$PWD/patchdock_cache:/opt/patchdock" \
  -v "$PWD/work:/work" \
  prosettac auto.py YourProtac_params.txt
```

Results land in `work/Results/` on the host.

Or via Compose:

```bash
PATCHDOCK_CACHE=./patchdock_cache \
PROSETTAC_WORK=./work \
docker compose run --rm prosettac auto.py YourProtac_params.txt
```

## How the image is assembled

The Dockerfile is multi-stage:

```
rosettacommons/rosetta:serial  ─►  stage "rosetta"
    │
    │   compiled binary + libs from /usr/local/bin
    │   Rosetta database from .../pyrosetta/database
    ▼
continuumio/miniconda3 (Debian trixie, linux/amd64)  ─►  final stage
  + apt: build-essential, git, curl, file, unzip, tcsh, libgl1, ...
  + conda env "prosettac" — python 3.11, rdkit, numpy, scikit-learn,
                            openbabel, pymol-open-source
  + conda env "py27"      — python 2.7 (for molfile_to_params.py)
  + git sparse-checkout of RosettaCommons/rosetta and RosettaCommons/tools
    at pinned SHAs (SCRIPTS_REPO_SHA, TOOLS_REPO_SHA)
  + COPY of Rosetta binaries + database into /opt/rosetta/main/...
  + COPY of this repo into /opt/prosettac
```

### Runtime layout inside the container

| Path | Contents |
|---|---|
| `/opt/rosetta/main/source/bin/` | `rosetta_scripts.default.linuxgccrelease` + shared libs |
| `/opt/rosetta/main/source/scripts/python/public/` | `molfile_to_params.py` + `rosetta_py/` |
| `/opt/rosetta/main/database/` | Rosetta database (`ROSETTA3_DB` points here) |
| `/opt/rosetta/tools/protein_tools/scripts/` | `clean_pdb.py` + `amino_acids.py` |
| `/opt/patchdock/` | populated on first run |
| `/opt/prosettac/` | this repo |
| `/work` | bind mount — your inputs/outputs |

The image is about 3 GB; most of that is the Rosetta database.

## Configuration

### Params file

**`auto.py` / `short.py`:**

```
PDB: PDB_ID1 PDB_ID2
LIG: LIG_ID1 LIG_ID2
PROTAC: protac.smi
Full: True
ClusterName: Local
```

Either field can use explicit files with the `[ID ; file]` form, e.g.
`PDB: [6BOY ; my_struct.pdb] [5T35 ; other.pdb]`.

**`main.py` / `extended.py`:**

```
Structures: StructA.pdb StructB.pdb
Chains: A B
Heads: HeadA.sdf HeadB.sdf
Anchor atoms: 11 23
Protac: protac.smi
Full: True
ClusterName: Local
```

Notes:

- `Full: False` runs a shorter, lower-quality sampling.
- The params file **must not** be called `params.txt` (reserved).
- `Protac` is a `.smi` file with the full PROTAC SMILES on a single line.
- Anchor atoms are 1-indexed and must be uniquely defined in the PROTAC SMILES.

### Scheduler

| `ClusterName` | Behavior |
|---|---|
| `Local` | Runs each batch inline — recommended inside Docker. |
| `PBS` | Portable Batch System (default if omitted). |
| `SGE` | Sun Grid Engine / OGS. |
| `SLURM` | Slurm Workload Manager. |

For non-`Local` schedulers, see `cluster/Cluster.py` for the interface. Set
`SCHEDULER_PARAMS` to a file whose contents are prepended to each job file
(useful for CPU counts, conda activation, etc.).

### Memory knobs

| Param | Default (MB) | Step |
|---|---|---|
| `RosettaDockMemory` | 8000 | Rosetta local docking |
| `ProtacModelMemory` | 4000 | PROTAC linker conformer generation |

### Sampling knobs (env vars)

These override the hard-coded sampling counts in `auto.py`. Useful for
cutting down runtime during development or on emulated amd64 hosts.

| Env var | Default (`Full: True`) | Default (`Full: False`) | Controls |
|---|---|---|---|
| `PROSETTAC_GLOBAL` | 1000 | 500 | Top PatchDock solutions to carry forward |
| `PROSETTAC_LOCAL` | 50 | 10 | Rosetta local-docking `nstruct` per hit |

## Entry points

| Script | Purpose |
|---|---|
| `auto.py` | Full automatic pipeline: fetch PDB, prep ligands, dock, linker conformers, cluster. |
| `main.py` | Manual pipeline: you supply prepared structures, binder SDFs, chains, anchor atoms. |
| `short.py` | `auto.py` wrapper that submits the whole run as one job. |
| `extended.py` | `main.py` wrapper that submits the whole run as one job. |

## Inputs

Input files for `auto.py` go in your `/work` bind mount. The `PDB:` line can
reference a remote PDB ID (fetched via PyMOL) or a local `.pdb` file. The
`LIG:` line can reference a PDB ligand three-letter code or a local `.sdf`
file. Ligand SDFs must be positioned in their binding pose within the
corresponding receptor.

## Compatibility patches

Upstream PRosettaC was written against RDKit 2019–2020 and OpenBabel 2.x.
To run on modern stacks the following source-level adjustments were made:

- `utils.py` — reads either `ROSETTA_FOL` or `ROSETTA3_HOME` for the
  Rosetta install path.
- `utils.patchdock` — writes the anchor-distance restraint using inline
  `distanceConstraints <rec> <lig> <max>` in the PatchDock params file
  (current PatchDock parses the external constraints file by residue
  number, not atom index).
- `protac_lib.get_mcs_sdf` — writes the MCS fragment from the source
  ligand's atoms (preserves bond orders) rather than the SMARTS pattern,
  and identifies the anchor as the MCS atom whose PROTAC counterpart has
  a bond to an atom outside the MCS (where the linker attaches).
- `protac_lib._read_sdf` helper — falls back to `sanitize=False` for
  ligands whose nitrogens get flagged as radicals by OpenBabel's addH
  (e.g. JQ1-class thienotriazolodiazepines).
- `protac_lib.translate_anchors` — reads both SDFs with matching sanitize
  settings so bond-order perception doesn't desync the substructure match.
- `protac_lib.GenConstConf` — calls `UpdatePropertyCache(strict=False)`
  before `EmbedMolecule` on the SMARTS-built virtual-atom helper, and
  falls back to MCS matching if the strict `GetSubstructMatches` returns
  empty.
- `auto.py` — reads `PROSETTAC_GLOBAL`/`PROSETTAC_LOCAL` from the
  environment and wraps the anchor-selection exception with a traceback
  for diagnosability.
- `cluster/Local/Local.py` — does **not** use `set -e` in the generated
  job script, so a single Rosetta `nstruct` failure within a batch of
  commands doesn't kill the other commands in the batch.
- `docker/babel-shim.sh` — translates OpenBabel 2.x-style invocations
  (`babel in.ext out.ext`) to OpenBabel 3 (`obabel in.ext -O out.ext`),
  since PRosettaC's `utils.py` still uses the 2.x argument order.

These changes are all fork-local; upstream PRosettaC isn't modified.

## Native install (HPC / no Docker)

If you cannot use Docker, the original flow still works:

1. Load Python 3 (the original study used 3.6.4).
2. Install RDKit, NumPy, PyMOL, scikit-learn, OpenBabel.
3. Install [Rosetta](https://www.rosettacommons.org/) and
   [PatchDock](https://bio3d.cs.huji.ac.il/webserver/patchdock/).
4. Set env vars:
   ```bash
   export PATCHDOCK=/path/to/patchdock
   export OB=/path/to/openbabel
   export SCRIPTS_FOL=/path/to/this/repo/
   export ROSETTA_FOL=/path/to/rosetta   # or ROSETTA3_HOME
   ```
5. Set scheduler paths (`PBS_HOME`, `SGE_HOME`, or Slurm equivalent) and
   `PBS_O_WORKDIR` / equivalent for each job.

Then:

```bash
python auto.py YourProtac_params.txt
```

## Authors

Daniel Zaidman, Nir London (original PRosettaC).
