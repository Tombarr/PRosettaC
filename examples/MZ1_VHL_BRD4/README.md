# MZ1 — VHL:BRD4 PROTAC

The first structurally characterized PROTAC ternary complex. MZ1 links the
VHL inhibitor VH032 to the BET bromodomain inhibitor JQ1 via a PEG3
linker, recruiting BRD4-BD2 to the CRL2-VHL E3 ligase.

## Reference structures

| Role | PDB | Description | Ligand |
|---|---|---|---|
| Ternary (ground truth) | [5T35](https://www.rcsb.org/structure/5T35) | VHL + MZ1 + BRD4-BD2 | `759` (full MZ1) |
| E3 binary (input) | [4W9H](https://www.rcsb.org/structure/4W9H) | VHL + acetyl-VH032 analog | `3JF` |
| Target binary (input) | [3MXF](https://www.rcsb.org/structure/3MXF) | BRD4-BD1 + JQ1 | `JQ1` |

The 5T35 ternary is BRD4-BD**2**, but MZ1 binds both BD1 and BD2 and no clean
BD2+JQ1 binary complex is deposited separately. Using the BD1+JQ1 binary
(3MXF) as input still produces a meaningful prediction of the VHL-BRD4
interface.

## PROTAC

MZ1, [PubChem CID 122201421](https://pubchem.ncbi.nlm.nih.gov/compound/122201421),
CAS 1797406-69-9.
Run `./fetch_inputs.sh` to pull the canonical SMILES from PubChem.

## Files

- `params.txt` — `auto.py` config with `Full: False` for a faster test.
- `fetch_inputs.sh` — downloads MZ1's canonical SMILES to `protac.smi`.

## Run

```bash
./fetch_inputs.sh                  # generates protac.smi

mkdir -p ../../work
cp params.txt protac.smi ../../work/
cd ../..

docker run --rm -it \
  -v "$PWD/patchdock_cache:/opt/patchdock" \
  -v "$PWD/work:/work" \
  prosettac auto.py params.txt
```

## Validation

Successful runs produce a top cluster whose BRD4 placement relative to VHL
is within ~3-4 Å interface RMSD of the 5T35 crystal structure. Align your
top cluster result to 5T35 on the VHL chain, then measure RMSD on the BRD4
Cα atoms.
