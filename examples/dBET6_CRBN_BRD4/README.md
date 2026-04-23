# dBET6 — CRBN:BRD4 PROTAC

The canonical CRBN-based BRD4 degrader. dBET6 links the CRBN ligand
thalidomide to JQ1, forming a ternary complex with CRBN and BRD4-BD1.

## Reference structures

| Role | PDB | Description | Ligand |
|---|---|---|---|
| Ternary (ground truth) | [6BOY](https://www.rcsb.org/structure/6BOY) | CRBN + dBET6 + BRD4-BD1 | `RN6` (full dBET6) |
| E3 binary (input) | [4CI1](https://www.rcsb.org/structure/4CI1) | CRBN + S-thalidomide | `EF2` |
| Target binary (input) | [3MXF](https://www.rcsb.org/structure/3MXF) | BRD4-BD1 + JQ1 | `JQ1` |

dBET6's CRBN-binding warhead is a thalidomide analog, so 4CI1 (thalidomide
in DDB1-CRBN) is the nearest binary match. Alternatives with lenalidomide
(`4CI2`, lig `LVY`) or pomalidomide (`4CI3`, lig `Y70`) may also work.

## PROTAC

dBET6, [PubChem CID 121427831](https://pubchem.ncbi.nlm.nih.gov/compound/121427831),
CAS 1950634-92-0.
Run `./fetch_inputs.sh` to pull the canonical SMILES from PubChem.

## Files

- `params.txt` — `auto.py` config with `Full: False`.
- `fetch_inputs.sh` — downloads dBET6's canonical SMILES to `protac.smi`.

## Run

```bash
./fetch_inputs.sh

mkdir -p ../../work
cp params.txt protac.smi ../../work/
cd ../..

docker run --rm -it \
  -v "$PWD/patchdock_cache:/opt/patchdock" \
  -v "$PWD/work:/work" \
  prosettac auto.py params.txt
```

## Validation

Align your top-cluster result to 6BOY on the CRBN chain and measure RMSD
on the BRD4 Cα atoms.
