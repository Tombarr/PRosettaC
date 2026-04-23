# Sample data

Two well-characterized PROTAC systems with published ternary crystal
structures. Use them to verify the Docker image works end-to-end and to
check your setup against known ground truth.

| Example | E3 | Target | PROTAC | Ternary PDB | Paper |
|---|---|---|---|---|---|
| [`MZ1_VHL_BRD4/`](MZ1_VHL_BRD4) | VHL | BRD4-BD2 | MZ1 | [5T35](https://www.rcsb.org/structure/5T35) | [Gadd et al., *Nat Chem Biol* 2017](https://doi.org/10.1038/nchembio.2329) |
| [`dBET6_CRBN_BRD4/`](dBET6_CRBN_BRD4) | CRBN | BRD4-BD1 | dBET6 | [6BOY](https://www.rcsb.org/structure/6BOY) | [Nowak et al., *Nat Chem Biol* 2018](https://doi.org/10.1038/s41589-018-0055-y) |

## How to use

Each example directory contains a `params.txt`, a `fetch_inputs.sh`, and a
per-example README. From your host shell:

```bash
cd examples/MZ1_VHL_BRD4
./fetch_inputs.sh                  # downloads PROTAC SMILES from PubChem
mkdir -p ../../work
cp params.txt protac.smi ../../work/
cd ../..

docker run --rm -it \
  -v "$PWD/patchdock_cache:/opt/patchdock" \
  -v "$PWD/work:/work" \
  prosettac auto.py params.txt
```

`auto.py` fetches the binary-complex PDBs directly from RCSB via PyMOL, so
you don't need to download those separately.

## Validating results

After the run completes, compare `work/Results/*.pdb` (top clusters of
predicted ternary conformations) against the published crystal structure
for the same system. A successful prediction places the E3 and target
proteins in an orientation close to the published ternary (RMSD under
~4 Å on the interface for a reasonable top-cluster hit).

## Runtime expectations

Set `Full: False` in `params.txt` for a ~30-60 min test run under Apple
Rosetta 2 emulation on Apple Silicon, or ~10-20 min on native amd64
hardware. `Full: True` (paper-grade sampling) takes several hours even on
a native amd64 box. These examples default to `Full: False`.
