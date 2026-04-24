# PRosettaC on Boston University SCC (Singularity + SGE)

Runbook for building and running the PRosettaC container on the BU Shared
Computing Cluster. The SCC uses [Singularity](https://www.bu.edu/tech/support/research/software-and-programming/containers/)
as its container runtime and [SGE](https://www.bu.edu/tech/support/research/system-usage/running-jobs/submitting-jobs/)
as its batch scheduler. Root / fakeroot is only available on the two dedicated
build nodes `scc-i01` and `scc-i02`.

Replace every `PROJECT_NAME` below with your real BU SCC project (the value
of the `-P` flag).

## 1. One-time build on `scc-i01`

```bash
ssh <user>@scc-i01.bu.edu

# Clone this repo into your project space.
cd /projectnb/PROJECT_NAME
git clone https://github.com/Tombarr/PRosettaC.git
cd PRosettaC

mkdir -p /projectnb/PROJECT_NAME/containers

# Redirect Singularity's scratch to node-local /scratch. The default /tmp
# is ~2GB on SCC, which will fail partway through the 2.3 GB Rosetta pull.
mkdir -p "$TMPDIR/$USER"
export SINGULARITY_TMPDIR="$TMPDIR/$USER"
export SINGULARITY_CACHEDIR="$TMPDIR/$USER"

singularity build --fakeroot \
    /projectnb/PROJECT_NAME/containers/prosettac.sif \
    hpc/scc/prosettac.def
```

Expect 10–30 minutes on a cold cache — the build pulls
`rosettacommons/rosetta:serial`, `continuumio/miniconda3:latest`, installs
apt packages, creates two conda envs, and sparse-clones the RosettaCommons
helper scripts.

Sanity-check the image:

```bash
singularity inspect --runscript /projectnb/PROJECT_NAME/containers/prosettac.sif
scc-singularity run --cleanenv /projectnb/PROJECT_NAME/containers/prosettac.sif --help
```

The second command should print the help block from `docker/entrypoint.sh`.

## 2. One-time PatchDock prefetch (on a login node)

PatchDock is a registration-gated dependency downloaded at runtime from
`bio3d.cs.huji.ac.il`. SCC compute nodes have restricted outbound network,
so we populate the cache once on a login node (which does have internet)
and bind-mount it into every compute job.

```bash
mkdir -p /projectnb/PROJECT_NAME/patchdock_cache

scc-singularity exec \
    --bind /projectnb/PROJECT_NAME/patchdock_cache:/opt/patchdock \
    --env PATCHDOCK_FULLNAME="Your Name" \
    --env PATCHDOCK_AFFILIATION="Boston University" \
    --env PATCHDOCK_EMAIL="you@bu.edu" \
    /projectnb/PROJECT_NAME/containers/prosettac.sif \
    /opt/prosettac/docker/fetch-patchdock.sh
```

The script is idempotent — it no-ops if `patch_dock.Linux` already exists
in the cache. Your credentials are submitted exactly as on the PatchDock
web form (name / affiliation / email are required by the license).

## 3. Test interactively before a long batch run

Grab a short interactive slot and run a tiny end-to-end smoke test:

```bash
qrsh -P PROJECT_NAME -pe omp 4 -l h_rt=1:00:00

cd /projectnb/PROJECT_NAME
export PATCHDOCK_FULLNAME="..." PATCHDOCK_AFFILIATION="..." PATCHDOCK_EMAIL="..."

WORK=$(mktemp -d /projectnb/PROJECT_NAME/runs/smoketest.XXXXXX)
cp PRosettaC/examples/MZ1_VHL_BRD4/Protac_params.txt "$WORK/"
bash PRosettaC/examples/MZ1_VHL_BRD4/fetch_inputs.sh
cp PRosettaC/examples/MZ1_VHL_BRD4/protac.smi "$WORK/"
# Ensure ClusterName: Local in the params file.
sed -i 's/^ClusterName:.*/ClusterName: Local/' "$WORK/Protac_params.txt"

mkdir -p "$TMPDIR/prosettac_home"
scc-singularity run \
    --cleanenv \
    --home "$TMPDIR/prosettac_home" \
    --bind "$TMPDIR:/tmp" \
    --bind /projectnb/PROJECT_NAME/patchdock_cache:/opt/patchdock \
    --bind "$WORK:/work" \
    --pwd /work \
    --env PATCHDOCK_FULLNAME \
    --env PATCHDOCK_AFFILIATION \
    --env PATCHDOCK_EMAIL \
    --env PROSETTAC_GLOBAL=10 \
    --env PROSETTAC_LOCAL=2 \
    --env TMPDIR=/tmp \
    /projectnb/PROJECT_NAME/containers/prosettac.sif \
    auto.py Protac_params.txt
```

`PROSETTAC_GLOBAL=10` and `PROSETTAC_LOCAL=2` cut sampling to produce
`Results/cluster*/` in a few minutes instead of hours. If this finishes
without errors and writes cluster directories, the image is healthy.

## 4. Submitting a production run

`hpc/scc/submit.sh` is a templated SGE job script. Edit the two
`PROJECT_NAME` placeholders, stage inputs into your desired `WORK`
directory, export PatchDock credentials, and `qsub`:

```bash
export PATCHDOCK_FULLNAME="..." PATCHDOCK_AFFILIATION="..." PATCHDOCK_EMAIL="..."

WORK=/projectnb/PROJECT_NAME/runs/mz1_$(date +%Y%m%dT%H%M%SZ)
mkdir -p "$WORK"
cp examples/MZ1_VHL_BRD4/Protac_params.txt "$WORK/"
bash examples/MZ1_VHL_BRD4/fetch_inputs.sh && cp examples/MZ1_VHL_BRD4/protac.smi "$WORK/"
# Local scheduler inside the container (not SGE-from-container).
sed -i 's/^ClusterName:.*/ClusterName: Local/' "$WORK/Protac_params.txt"

WORK="$WORK" qsub hpc/scc/submit.sh
```

Monitor with `qstat`. Output lands in `$WORK/Results/cluster*/` and the
SGE stdout/stderr in `prosettac.o<jobid>` next to the submission CWD.

### Resource tuning

Defaults in `submit.sh` are `-pe omp 8`, `-l mem_per_core=4G`, and
`-l h_rt=24:00:00`. For large runs (`Full: True`, default sampling
counts) increase walltime to 48–72 h. Rosetta's `serial` build is
single-threaded, so asking for more than ~4–8 cores rarely helps
with the current `ClusterName: Local` backend.

## Why `ClusterName: Local` (and not `SGE`)?

PRosettaC's `cluster/SGE/SGE.py` backend shells out to `qsub` / `qstat`
on the **host**. Those binaries aren't in the Debian-based container,
and even if SCC's `scc-singularity` wrapper binds `/usr/local` into the
image, the SGE client shared libraries may not be ABI-compatible with
the container's glibc. Running everything as a single long SGE job with
the `Local` backend is the simplest robust choice. If you later need
multi-node parallelism, the right follow-up is a new
`cluster/LocalParallel/` backend that uses `$NSLOTS` cores within a
single job — not mixing `qsub` between host and container.

## Files

- `hpc/scc/prosettac.def` — Singularity definition file (multi-stage; mirrors
  `Dockerfile`).
- `hpc/scc/submit.sh` — templated SGE submission script.
- `hpc/scc/README.md` — this file.

## Related

- Root project README: container architecture, example inputs, scheduler
  params file format.
- `docker/` — Docker / Docker Compose path for laptop use. Reused verbatim
  by the Singularity build (via `%files` and `%runscript`).
