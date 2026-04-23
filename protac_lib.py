import sys
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import rdFMCS
from rdkit.Chem import rdMolAlign
from rdkit.Chem import rdMolTransforms
from rdkit.Geometry.rdGeometry import Point3D
from rdkit.Chem.rdchem import Atom
import utils
import numpy as np
import math
import glob
import random
import copy

def _read_sdf(path, sanitize=True):
    """Read the first mol from an SDF, falling back to sanitize=False for
    ligands (e.g. JQ1-derivatives) that OpenBabel's addH leaves in a state
    the RDKit sanitizer rejects."""
    mol = Chem.SDMolSupplier(path, sanitize=sanitize)[0]
    if mol is None and sanitize:
        mol = Chem.SDMolSupplier(path, sanitize=False)[0]
        if mol is not None:
            try:
                Chem.SanitizeMol(mol, sanitizeOps=Chem.SANITIZE_ALL ^ Chem.SANITIZE_PROPERTIES)
            except Exception:
                pass
    return mol

def get_mcs_sdf(old_sdf, new_sdf, protac):
    utils.addH_sdf(old_sdf)
    OldSdf = Chem.SDMolSupplier(old_sdf)[0]
    if OldSdf is None:
        # Fall back to unsanitized read for ligands that trip the sanitizer,
        # e.g. cationic nitrogens in JQ1-like thienotriazolodiazepines that
        # OpenBabel's addH marks as radicals. Try a minimal sanitize after.
        OldSdf = Chem.SDMolSupplier(old_sdf, sanitize=False)[0]
        if OldSdf is None:
            return False, old_sdf + ' is not readable by RDKit.'
        try:
            Chem.SanitizeMol(OldSdf, sanitizeOps=Chem.SANITIZE_ALL ^ Chem.SANITIZE_PROPERTIES)
        except Exception:
            pass
    PROTAC = Chem.MolFromSmiles(protac)
    print(Chem.MolToSmiles(OldSdf))
    print(Chem.MolToSmiles(PROTAC))
    mcs = rdFMCS.FindMCS([OldSdf, PROTAC], ringMatchesRingOnly=False, completeRingsOnly=False, timeout=1)
    print(mcs.smartsString)
    mcs_patt = Chem.MolFromSmarts(mcs.smartsString)
    print(mcs_patt.GetNumHeavyAtoms())
    print(OldSdf.GetNumHeavyAtoms())
    if mcs_patt.GetNumHeavyAtoms() < OldSdf.GetNumHeavyAtoms() * 0.6:
        return False, 'The MCS (maximal common substructure) is below the size threshold (at least 60 percent) compared with ' + old_sdf + '.'
    # Build a proper substructure mol from OldSdf's atoms (with real bond
    # orders and valences) in MCS-traversal order. The previous approach of
    # writing the SMARTS-derived RWMol as SDF produced a file that
    # SDMolSupplier cannot parse, because SMARTS atoms lack well-defined
    # chemistry.
    Match = OldSdf.GetSubstructMatch(mcs_patt)
    submol = Chem.RWMol()
    orig_to_sub = {}
    for new_idx, orig_idx in enumerate(Match):
        atom = Chem.Atom(OldSdf.GetAtomWithIdx(orig_idx))
        added = submol.AddAtom(atom)
        orig_to_sub[orig_idx] = added
    for bond in OldSdf.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if a in orig_to_sub and b in orig_to_sub:
            submol.AddBond(orig_to_sub[a], orig_to_sub[b], bond.GetBondType())
    submol = submol.GetMol()
    conf = Chem.Conformer(submol.GetNumAtoms())
    for orig_idx, sub_idx in orig_to_sub.items():
        conf.SetAtomPosition(sub_idx, OldSdf.GetConformer().GetAtomPosition(orig_idx))
    submol.AddConformer(conf)
    try:
        Chem.SanitizeMol(submol)
    except Exception:
        pass
    writer = Chem.SDWriter(new_sdf)
    writer.write(submol)
    writer.close()
    print(new_sdf)

    # Identify the anchor: the MCS atom whose counterpart in the PROTAC has
    # at least one bond to an atom NOT in the MCS. That atom is where the
    # linker extends out of the warhead and should be the docking anchor.
    # If more than one qualifies (rare — typically only one attachment
    # point), pick the one with the most "extra" PROTAC neighbors.
    protac_match = PROTAC.GetSubstructMatch(mcs_patt)
    if len(protac_match) == mcs_patt.GetNumAtoms():
        protac_match_set = set(protac_match)
        best_i, best_extra = 0, -1
        for i, protac_idx in enumerate(protac_match):
            extra = sum(
                1 for n in PROTAC.GetAtomWithIdx(protac_idx).GetNeighbors()
                if n.GetIdx() not in protac_match_set
            )
            if extra > best_extra:
                best_extra, best_i = extra, i
        if best_extra > 0:
            # best_i is the MCS-atom index; submol atoms are in MCS order, so
            # anchor in SubA.sdf == best_i.
            return True, best_i

    # Fallback to the original automorphism-based heuristic if we couldn't
    # localize the attachment point (e.g. the PROTAC itself is the ligand).
    NewSdf = submol
    Matches = NewSdf.GetSubstructMatches(NewSdf, uniquify=False)
    if len(Matches) == 0:
        return False, ''
    elif len(Matches) == 1:
        return True, 0
    for i in range(len(Matches[0])):
        a = Matches[0][i]
        if all(a == j[i] for j in Matches[1:]):
            return True, a
    return False, 'The MCS between the PROTAC and the ligand does not have a uniquely defined anchor atom.'

def translate_anchors(old_sdf, new_sdf, old_anchor):
    # Read both files with matching sanitize settings so bond-order perception
    # doesn't desynchronize them and break the substructure match.
    OldSdf = Chem.SDMolSupplier(old_sdf, sanitize=False)[0]
    NewSdf = Chem.SDMolSupplier(new_sdf, sanitize=False)[0]
    if NewSdf is None:
        NewSdf = Chem.SDMolSupplier(new_sdf, sanitize=True)[0]
    print("translate_anchors old:", Chem.MolToSmiles(OldSdf))
    print("translate_anchors new:", Chem.MolToSmiles(NewSdf))
    NewMatch = NewSdf.GetSubstructMatch(OldSdf)
    if len(NewMatch) == 0:
        # Retry with a SMARTS-only query (matches atomic numbers/connectivity,
        # ignores bond orders) for cases where sanitize perception still diverges.
        query = Chem.MolFromSmarts(Chem.MolToSmarts(OldSdf))
        if query is not None:
            NewMatch = NewSdf.GetSubstructMatch(query)
    if len(NewMatch) == 0:
        return -1
    print("translate_anchors match:", NewMatch)
    return NewMatch[old_anchor]

def rmsd(query, ref, q_match, r_match):
    rmsd = 0
    for i in range(len(q_match)):
        rmsd += (query.GetConformer().GetAtomPosition(q_match[i])-ref.GetConformer().GetAtomPosition(r_match[i])).LengthSq()
    rmsd = np.sqrt(rmsd/len(q_match))
    return rmsd

def heads_rmsd(query, headA, headB, headA_sub, headB_sub, match_A, match_B):
    rmsd = 0
    for i in range(len(match_A)):
        rmsd += (query.GetConformer().GetAtomPosition(match_A[i])-headA.GetConformer().GetAtomPosition(headA_sub[i])).LengthSq()
    for i in range(len(match_B)):
        rmsd += (query.GetConformer().GetAtomPosition(match_B[i])-headB.GetConformer().GetAtomPosition(headB_sub[i])).LengthSq()
    rmsd = np.sqrt(rmsd/(len(match_A) + len(match_B)))
    return rmsd

def MCS_AtomMap(query, ref):
    mcs = rdFMCS.FindMCS([query, ref], ringMatchesRingOnly=True, completeRingsOnly=True)
    mcs_patt = Chem.MolFromSmarts(mcs.smartsString)
    refMatch = ref.GetSubstructMatch(mcs_patt)
    queryMatch = query.GetSubstructMatch(mcs_patt)
    amap = []
    for i in range(len(refMatch)):
        amap.append((queryMatch[i], refMatch[i]))
    return amap

def SetCoordsForMatch(query, ref, ref_match):
    for i, pos in enumerate(ref_match):
        ref_pos = ref.GetConformer().GetAtomPosition(i)
        query.GetConformer().SetAtomPosition(pos, ref_pos)

def translateMol(mol, pointA, pointB):
    for i in range(mol.GetConformer().GetNumAtoms()):
        mol.GetConformer().SetAtomPosition(i, mol.GetConformer().GetAtomPosition(i) + pointA - pointB)

def x_rotation(vector,theta):
    """Rotates 3-D vector around x-axis"""
    R = np.array([[1,0,0],[0,np.cos(theta),-np.sin(theta)],[0, np.sin(theta), np.cos(theta)]])
    output = np.dot(R, [vector.x, vector.y, vector.z])
    return Point3D(output[0], output[1], output[2])

def y_rotation(vector,theta):
    """Rotates 3-D vector around y-axis"""
    R = np.array([[np.cos(theta),0,np.sin(theta)],[0,1,0],[-np.sin(theta), 0, np.cos(theta)]])
    output = np.dot(R, [vector.x, vector.y, vector.z])
    return Point3D(output[0], output[1], output[2])

def z_rotation(vector,theta):
    """Rotates 3-D vector around z-axis"""
    R = np.array([[np.cos(theta), -np.sin(theta),0],[np.sin(theta), np.cos(theta),0],[0,0,1]])
    output = np.dot(R, [vector.x, vector.y, vector.z])
    return Point3D(output[0], output[1], output[2])

#rotate a molecule around the origin
def rotateMol(mol, x, y, z):
    for i in range(mol.GetConformer().GetNumAtoms()):
        atom = mol.GetConformer().GetAtomPosition(i)
        atom = x_rotation(atom, x)
        atom = y_rotation(atom, y)
        atom = z_rotation(atom, z)
        mol.GetConformer().SetAtomPosition(i, atom)

def randomRotateMol(mol):
    x = random.random()*np.pi*2
    y = random.random()*np.pi*2
    z = random.random()*np.pi*2
    rotateMol(mol, x, y, z)

#sample an array of distances between the anchor points
def SampleDist(Heads, Anchors, Linkers, n = 200, output_hist="initial_distances.hist", hist_threshold = 0.75, min_margin = 2, homo_protac = False):
    writer = Chem.SDWriter("random_sampling.sdf")
    random.seed(0)
    [HeadA_sdf, HeadB_sdf] = Heads
    #linkers
    with open(Linkers, 'r') as f:
        linkers = [Chem.MolFromSmiles(f.readline().split()[0])]
    #loading the heads sdf files
    HeadA = _read_sdf(HeadA_sdf)
    HeadB = _read_sdf(HeadB_sdf)
    origin = Point3D(0,0,0)
    anchor_a = HeadA.GetConformer().GetAtomPosition(Anchors[0])
    translateMol(HeadA, origin, anchor_a)
    anchor_b = HeadB.GetConformer().GetAtomPosition(Anchors[1])
    translateMol(HeadB, origin, anchor_b)
    for linker in linkers:
        #homo protacs are protacs with the same binder twice, causing self degradation of an E3 ligase
        if homo_protac:
            head_A = linker.GetSubstructMatches(HeadA)[0]
            head_B = linker.GetSubstructMatches(HeadB)[1]
        else:
            mcs_A = rdFMCS.FindMCS([linker, HeadA])
            mcs_patt_A = Chem.MolFromSmarts(mcs_A.smartsString)
            mcs_B = rdFMCS.FindMCS([linker, HeadB])
            mcs_patt_B = Chem.MolFromSmarts(mcs_B.smartsString)
            #head_A_list = linker.GetSubstructMatches(HeadA, uniquify=False)
            head_A_list = linker.GetSubstructMatches(mcs_patt_A, uniquify=False)
            head_A_inner = HeadA.GetSubstructMatch(mcs_patt_A)
            #head_B_list = linker.GetSubstructMatches(HeadB, uniquify=False)
            head_B_list = linker.GetSubstructMatches(mcs_patt_B, uniquify=False)
            head_B_inner = HeadB.GetSubstructMatch(mcs_patt_B)
            print(Chem.MolToSmiles(linker))
            print(Chem.MolToSmiles(HeadB))
            print(head_B_list)
            if len(head_A_list) == 0 or len(head_B_list) == 0:
                return (None, None)
        histogram = {}
        seed  = 0
        b = 1
        while True:
            b_counter = 0
            for i in range(n):
                head_A = random.choice(head_A_list)
                head_B = random.choice(head_B_list)
                seed += 1
                NewA = copy.deepcopy(HeadA)
                NewB = copy.deepcopy(HeadB)
                randomRotateMol(NewA) 
                randomRotateMol(NewB)
                translateMol(NewB, Point3D(b, 0, 0), origin)
                #the constraints for the conformation generation using the two randomized heads
                cmap = {head_A[i]:NewA.GetConformer().GetAtomPosition(head_A_inner[i]) for i in range(len(head_A))}
                cmap.update({head_B[i]:NewB.GetConformer().GetAtomPosition(head_B_inner[i]) for i in range(len(head_B))})
                #only half of the atoms are required to make the constrained embedding
                #this is done because using all the atoms sometimes makes it impossible
                #to find solutions, the half is chosen randomly for each generation
                cmap_tag = random.sample(list(cmap), int(len(cmap)/2))
                cmap_tag = {ctag:cmap[ctag] for ctag in cmap_tag}
                if AllChem.EmbedMolecule(linker, coordMap=cmap_tag, randomSeed=seed, useBasicKnowledge=True, maxAttempts=1) == -1:
                    continue
                if int(round(rdMolTransforms.GetBondLength(linker.GetConformer(), head_A[Anchors[0]], head_B[Anchors[1]]))) == b:
                    writer.write(linker)
                    b_counter += 1
            histogram[b] = b_counter
            if b >= 10 and b_counter == 0:
                break
            b += 1
        with open(output_hist, 'w') as f:
            for h in histogram:
                f.write(str(h) + "\t" + str(histogram[h]) + '\n')
        max_value = max([histogram[i] for i in histogram])
        sum_mul = 0
        sum_his = 0
        for i in histogram:
            sum_mul += i * histogram[i]
            sum_his += histogram[i]
        if sum_his == 0:
            return (0,0)
        else:
            avg_index = 1.0 * sum_mul / sum_his
            threshold = max_value * hist_threshold
            high_values = [i for i in histogram if histogram[i] >= threshold]
            return(min(min(high_values), avg_index - min_margin), max(max(high_values), avg_index + min_margin))

#generate n random conformations for each smile in linkers_file
#this is an old function and is not used in the final pipeline
def GenRandConf(Heads, Anchors, Linkers, n=1000, output_hist="initial_distances.hist", output_sdf="random_sampling.sdf"):
    writer = Chem.SDWriter(output_sdf)
    [HeadA_sdf, HeadB_sdf] = Heads
    #linkers
    with open(Linkers, 'r') as f:
        linkers = [Chem.MolFromSmiles(f.readline().split()[0])]
    #loading the heads sdf files
    HeadA = _read_sdf(HeadA_sdf)
    HeadB = _read_sdf(HeadB_sdf)
    #anchor distances
    X1Y1_dist = []
    for linker in linkers:
        Chem.AddHs(linker)
        amapA = MCS_AtomMap(HeadA, linker)
        amapB = MCS_AtomMap(HeadB, linker)
        anchors = [[item[1] for item in amapA if item[0] == Anchors[0]][0], [item[1] for item in amapB if item[0] == Anchors[1]][0]]
        i = 0
        seed = 0
        while i < n:
            seed += 1
            if Chem.rdDistGeom.EmbedMolecule(linker, randomSeed=seed, useBasicKnowledge=True, maxAttempts=10) == -1:
                continue
            X1Y1_dist.append(rdMolTransforms.GetBondLength(linker.GetConformer(), anchors[0], anchors[1]))
            writer.write(linker)
            i += 1
    
    hist = np.histogram(np.array(X1Y1_dist), range=(math.floor(min(X1Y1_dist)), math.ceil(max(X1Y1_dist))), bins=2*int(math.ceil(max(X1Y1_dist)-math.floor(min(X1Y1_dist)))))
    with open(output_hist, 'w') as f:
        f.write("range is: " + str([min(X1Y1_dist), max(X1Y1_dist)]) + '\n')
        for i in range(len(hist[0])):
            f.write(str(hist[0][i]) + '\t' + str(hist[1][i]) + '\n')
    return (min(X1Y1_dist), max(X1Y1_dist))

#generate constrained conformations for each of the local docking solutions
def GenConstConf(Heads, Docked_Heads, Head_Linkers, output_sdf, Anchor_A, v_atoms_sdf, n = 100, homo_protac = False):
    writer = Chem.SDWriter(output_sdf)
    with open(Head_Linkers, 'r') as f:
        head_linkers = [Chem.MolFromSmiles(f.readline().split()[0])]
    #loading the heads sdf files
    HeadA = _read_sdf(Heads[0])
    HeadB = _read_sdf(Heads[1])
    docked_heads = _read_sdf(Docked_Heads)
    #virtual atoms around the center of mass for the neighbor atom alignment
    num_atoms = docked_heads.GetConformer().GetNumAtoms()
    x = []
    y = []
    z = []
    for i in range(num_atoms):
        x.append(docked_heads.GetConformer().GetAtomPosition(i).x)
        y.append(docked_heads.GetConformer().GetAtomPosition(i).y)
        z.append(docked_heads.GetConformer().GetAtomPosition(i).z)
    v1 = Point3D(sum(x)/num_atoms, sum(y)/num_atoms, sum(z)/num_atoms)
    v2 = Point3D(sum(x)/num_atoms + 1, sum(y)/num_atoms, sum(z)/num_atoms)
    v3 = Point3D(sum(x)/num_atoms, sum(y)/num_atoms + 1, sum(z)/num_atoms)
    virtual_atoms = Chem.MolFromSmarts('[#23][#23][#23]')
    # MolFromSmarts skips valence perception; EmbedMolecule in RDKit 2024+
    # requires implicit-H counts to be populated.
    virtual_atoms = Chem.RWMol(virtual_atoms)
    virtual_atoms.UpdatePropertyCache(strict=False)
    Chem.rdDistGeom.EmbedMolecule(virtual_atoms)
    virtual_atoms.GetConformer().SetAtomPosition(1, v1)
    virtual_atoms.GetConformer().SetAtomPosition(0, v2)
    virtual_atoms.GetConformer().SetAtomPosition(2, v3)
    v_writer = Chem.SDWriter(v_atoms_sdf)
    v_writer.write(virtual_atoms)

    #homo protacs are protacs with the same binder twice, causing self degradation of an E3 ligase
    if homo_protac:
        docked_A = docked_heads.GetSubstructMatches(HeadA)[0]
        docked_B = docked_heads.GetSubstructMatches(HeadB)[1]
    else:
        docked_A = docked_heads.GetSubstructMatch(HeadA)
        docked_B = docked_heads.GetSubstructMatch(HeadB)
    for head_linker in head_linkers:
        Chem.AddHs(head_linker)
        if homo_protac:
            head_A = head_linker.GetSubstructMatches(HeadA)[0]
            head_B = head_linker.GetSubstructMatches(HeadB)[1]
        else:
            head_A_list = head_linker.GetSubstructMatches(HeadA, uniquify=False)
            head_B_list = head_linker.GetSubstructMatches(HeadB, uniquify=False)
            # Fall back to MCS-based matching if direct sanitized match fails
            # (sanitized vs non-sanitized bond-order perception can make the
            # exact substructure search return empty). When the linker is
            # remapped through MCS, docked_A/B must be remapped to the same
            # MCS pattern so the tuple lengths match downstream.
            if len(head_A_list) == 0:
                mcs = rdFMCS.FindMCS([head_linker, HeadA])
                patt = Chem.MolFromSmarts(mcs.smartsString)
                head_A_list = head_linker.GetSubstructMatches(patt, uniquify=False)
                docked_A = docked_heads.GetSubstructMatch(patt)
            if len(head_B_list) == 0:
                mcs = rdFMCS.FindMCS([head_linker, HeadB])
                patt = Chem.MolFromSmarts(mcs.smartsString)
                head_B_list = head_linker.GetSubstructMatches(patt, uniquify=False)
                docked_B = docked_heads.GetSubstructMatch(patt)
            if len(head_A_list) == 0 or len(head_B_list) == 0:
                return -1, v_atoms_sdf

        i = 0
        seed = 0
        while i < n:
            if seed > 10 * n:
                break
            if seed > n and i == 0:
                break
            seed += 1

            random.seed(seed)

            head_A = random.choice(head_A_list)
            head_B = random.choice(head_B_list)

            #amap for final alignment                                                                                                         
            amap = []
            for j in range(len(docked_A)):
                amap.append((head_A[j], docked_A[j]))
            for j in range(len(docked_B)):
                amap.append((head_B[j], docked_B[j]))

            #the constraints for the conformation generation using the two docked heads
            cmap = {head_A[j]:docked_heads.GetConformer().GetAtomPosition(docked_A[j]) for j in range(len(docked_A))}
            cmap.update({head_B[j]:docked_heads.GetConformer().GetAtomPosition(docked_B[j]) for j in range(len(docked_B))})
            #only half of the atoms are required to make the constrained embedding
            #this is done because using all the atoms sometimes makes it impossible
            #to find solutions, the half is chosen randomly for each generation
            cmap_tag = random.sample(list(cmap), int(len(cmap)/2))
            cmap_tag = {ctag:cmap[ctag] for ctag in cmap_tag}
            if AllChem.EmbedMolecule(head_linker, coordMap=cmap_tag, randomSeed=seed, useBasicKnowledge=True, maxAttempts=10) == -1:
                continue
            #final alignment to bring the new conformation to the position of the pose's heads
            #this is needed because the constrained embedding only applies
            #to distances and not to atoms position
            rdMolAlign.AlignMol(head_linker, docked_heads, atomMap=amap)
            #make sure the alignment is good enough for both heads (also to ensure the save isomer
            #for ambiguous rings
            if rmsd(head_linker, docked_heads, head_A, docked_A) < 0.5 and rmsd(head_linker, docked_heads, head_B, docked_B) < 0.5:
                writer.write(head_linker)
                i += 1
    return head_A[int(Anchor_A)], v_atoms_sdf

#printing head RMSD, calculated between a modeled PROTAC, and the .sdf files of the two binders (headA, headB)
def print_rmsd(headA, headB, Head_Linkers):
    #loading the heads sdf files                                                                                      
    HeadA = _read_sdf(headA)
    HeadB = _read_sdf(headB)
    head_linkers = Chem.SDMolSupplier(Head_Linkers)
    for head_linker in head_linkers:
        mcsA = rdFMCS.FindMCS([HeadA, head_linker])
        mcsB = rdFMCS.FindMCS([HeadB, head_linker])
        pattA = Chem.MolFromSmarts(mcsA.smartsString)
        pattB = Chem.MolFromSmarts(mcsB.smartsString)
        HeadA_sub = HeadA.GetSubstructMatches(pattA, uniquify=False)
        HeadB_sub = HeadB.GetSubstructMatch(pattB)
        head_A = head_linker.GetSubstructMatches(pattA, uniquify=False)
        head_B = head_linker.GetSubstructMatch(pattB)
        for H in HeadA_sub:
            for h in head_A:
                print(heads_rmsd(head_linker, HeadA, HeadB, H, HeadB_sub, h, head_B))
