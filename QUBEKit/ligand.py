#!/usr/bin/env python

# TODO Add remaining xml methods for Protein class

from collections import OrderedDict
from datetime import datetime
from itertools import groupby
import pickle
import re

import networkx as nx
import numpy as np

from xml.etree.ElementTree import tostring, Element, SubElement, ElementTree
from xml.dom.minidom import parseString


class Molecule:
    """Base class for ligands and proteins."""

    def __init__(self, filename, smiles_string=None):
        """
        # Namings
        filename                str; Full filename e.g. methane.pdb
        name                    str; Molecule name e.g. methane
        smiles                  str; equal to the smiles_string if one is provided

        # Structure
        molecule                Dict of lists where the keys are the input type (mm, qm, etc) and the vals are
                                lists of lists where the inner lists are the atom name, followed by the coords
                                e.g. {'mm': [['C', 1.045, 2.456, 1.564], ...], ...}
        topology                Graph class object. Contains connection information for molecule
        angles                  List of tuples; Shows angles based on atom indices (+1) e.g. (1, 2, 4), (1, 2, 5)
        dihedrals               Dictionary of dihedral tuples stored under their common core bond
                                e.g. {(1,2): [(3, 1, 2, 6), (3, 1, 2, 7)]}
        improper_torsions
        rotatable               List of dihedral core tuples [(1,2)]
        atom_names              List of the atom names taken from the pdb file
        bond_lengths            Dictionary of bond lengths stored under the bond tuple
                                e.g. {(1, 3): 1.115341203992107} (angstroms)
        dih_phis                Dictionary of the dihedral angles measured in the molecule object stored under the
                                dihedral tuple e.g. {(3, 1, 2, 6): -70.3506776877}  (degrees)
        angle_values            Dictionary of the angle values measured in the molecule object stored under the
                                angle tuple e.g. {(2, 1, 3): 107.2268} (degrees)
        symm_hs
        qm_energy

        # XML Info
        xml_tree                An XML class object containing the force field values
        AtomTypes               dict of lists; basic non-symmetrised atoms types for each atom in the molecule
                                e.g. {0, ['C1', 'opls_800', 'C800'], 1: ['H1', 'opls_801', 'H801'], ... }
        Residues                List of residue names in the sequence they are found in the protein
        extra_sites

        Parameters
        -------------------
        This section has different units due to it interacting with OpenMM

        HarmonicBondForce       Dictionary of equilibrium distances and force constants stored under the bond tuple.
                                {(1, 2): [0.108, 405.65]} (nano meters, kj/mol)
        HarmonicAngleForce      Dictionary of equilibrium angles and force constants stored under the angle tuple
                                e.g. {(2, 1, 3): [2.094395, 150.00]} (radians, kj/mol)
        PeriodicTorsionForce    Dictionary of lists of the torsions values [periodicity, k, phase] stored under the
                                dihedral tuple with an improper tag only for improper torsions
                                e.g. {(3, 1, 2, 6): [[1, 0.6, 0 ] [2, 0, 3.141592653589793] .... Improper]}
        NonbondedForce          OrderedDict; L-J params. Keys are atom index, vals are [charge, sigma, epsilon]

        combination             str; Combination rules e.g. 'opls'
        sites                   OrderedDict of virtual site parameters {0: [(top nos parent, a .b), (p1, p2, p3), charge]}

        # QUBEKit Internals
        state                   str; Describes the stage the analysis is in for pickling and unpickling
        """

        # Namings
        self.filename = filename
        self.name = filename.split(".")[0]
        # Also check if we have a full path in the name
        self.name = self.name.split("/")[-1]
        self.smiles = smiles_string

        # Structure
        self.molecule = {'qm': [], 'mm': [], 'input': [], 'temp': [], 'traj': []}
        self.topology = None
        self.angles = None
        self.dihedrals = None
        self.improper_torsions = []
        self.rotatable = None
        self.atom_names = None
        self.mol2_types = None
        self.bond_lengths = None
        self.dih_phis = None
        self.angle_values = None
        self.symm_hs = None
        self.qm_energy = None

        # XML Info
        self.xml_tree = None
        self.AtomTypes = {}
        self.Residues = None
        self.extra_sites = None
        self.HarmonicBondForce = {}
        self.HarmonicAngleForce = {}
        self.PeriodicTorsionForce = OrderedDict()
        self.NonbondedForce = OrderedDict()

        self.combination = None
        self.sites = None

        # QUBEKit internals
        self.state = None

        # Atomic weight dict
        self.element_dict = {
            'H': 1.008000,   # Group 1
            'B': 10.811000,  # Group 3
            'C': 12.011000,  # Group 4
            'N': 14.007000, 'P': 30.973762,  # Group 5
            'O': 15.999000, 'S': 32.060000,  # Group 6
            'F': 18.998403, 'CL': 35.450000, 'BR': 79.904000, 'I': 126.904470   # Group 7
        }

    def __repr__(self):
        return f'{self.__class__.__name__}({self.__dict__!r})'

    def __str__(self, trunc=False):
        """
        Prints the Molecule class objects' names and values one after another with new lines between each.
        Mostly just used for logging, debugging and displaying the results at the end of a run.
        If trunc is set to True:
            Check the items being printed:
                If they are empty or None -> skip over them
                If they're short (<120 chars) -> print them as normal
                Otherwise -> print a truncated version of them.
        If trunc is set to False:
            Just print everything (all key: value pairs) as is with a little extra spacing.
        """

        return_str = ''

        if trunc:
            for key, val in self.__dict__.items():

                # Don't bother printing objects that are empty or None.
                # Just checking (if val) won't work as truth table is ambiguous for length > 1 arrays
                # I know this is gross, but it's the best of a bad situation.

                try:
                    bool(val)
                # Catch numpy array truth table
                except ValueError:
                    continue

                if val is not None and val:
                    return_str += f'\n{key} = '

                    # if it's smaller than 120 chars: print it as is. Otherwise print a version cut off with "...".
                    if len(str(key) + str(val)) < 120:
                        # Print the repr() not the str(). This means generator expressions etc appear too.
                        return_str += repr(val)
                    else:
                        return_str += repr(val)[:121 - len(str(key))] + '...'

        else:
            for key, val in self.__dict__.items():
                # Return all objects as {ligand object name} = {ligand object value(s)} without any special formatting.
                return_str += f'\n{key} = {val}\n'

        return return_str

    def read_file(self):
        """The base file reader used on instancing the class it will decided what file reader to use."""

        if self.filename.split(".")[1] == 'pdb':
            self.read_pdb(self.filename)
        elif self.filename.split(".")[1] == 'mol2':
            self.read_mol2(self.filename)

    def read_pdb(self, name, input_type='input'):
        """
        Reads the input PDB file to find the ATOM or HETATM tags, extracts the elements and xyz coordinates.
        Then reads through the connection tags and builds a connectivity network
        (only works if connections are present in PDB file).
        Bonds are easily found through the edges of the network.
        Can also generate a simple plot of the network.
        """

        with open(name, 'r') as pdb:
            lines = pdb.readlines()

        molecule = []
        self.topology = nx.Graph()
        self.atom_names = []

        # atom counter used for graph node generation
        atom_count = 1
        for line in lines:
            if 'ATOM' in line or 'HETATM' in line:
                element = str(line[76:78])
                element = re.sub('[0-9]+', '', element)
                element = element.strip()
                self.atom_names.append(str(line.split()[2]))

                # If the element column is missing from the pdb, extract the element from the name.
                # TODO Will this be ok if the element is 2 chars?
                if not element:
                    element = str(line.split()[2])[:-1]
                    element = re.sub('[0-9]+', '', element)

                # Also add the atom number as the node in the graph
                self.topology.add_node(atom_count)
                atom_count += 1
                molecule.append([element, float(line[30:38]), float(line[38:46]), float(line[46:54])])

            if 'CONECT' in line:
                # Now look through the connectivity section and add all edges to the graph corresponding to the bonds.
                for i in range(2, len(line.split())):
                    if int(line.split()[i]) != 0:
                        self.topology.add_edge(int(line.split()[1]), int(line.split()[i]))

        # put the object back into the correct place
        self.molecule[input_type] = molecule

    def read_mol2(self, name, input_type='input'):
        """
        Read an input mol2 file and extract the atom names, positions, atom types and bonds.
        :param input_type: Assign the structure to right holder, input, mm, qm, temp or traj.
        :return: The object back into the right place.
        """

        molecule = []
        self.topology = nx.Graph()
        self.atom_names = []
        self.mol2_types = []

        # atom counter used for graph node generation
        atom_count = 1

        with open(name, 'r') as mol2:
            lines = mol2.readlines()

        atoms = False
        bonds = False

        for line in lines:
            if '@<TRIPOS>ATOM' in line:
                atoms = True
                continue
            elif '@<TRIPOS>BOND' in line:
                atoms = False
                bonds = True
                continue
            elif '@<TRIPOS>SUBSTRUCTURE' in line:
                bonds = False
                continue
            if atoms:
                # Add the molecule information
                element = line.split()[1][:2]
                element = re.sub('[0-9]+', '', element)
                element = element.strip()
                if element.upper() not in self.element_dict:
                    element = element[0]
                molecule.append([element, float(line.split()[2]), float(line.split()[3]), float(line.split()[4])])

                # Collect the atom names
                self.atom_names.append(str(line.split()[1]))

                # Add the nodes to the topology object
                self.topology.add_node(atom_count)
                atom_count += 1

                # Get the atom types
                atom_type = line.split()[5]
                atom_type = atom_type.replace(".", "")
                self.mol2_types.append(atom_type)

            if bonds:
                # Add edges to the topology network
                self.topology.add_edge(int(line.split()[1]), int(line.split()[2]))

        # put the object back into the correct place
        self.molecule[input_type] = molecule

    def read_geometric_traj(self, trajectory):
        """
        Read in the molecule coordinates to the traj holder from a geometric optimisation using qcengine.
        :param trajectory: The qcengine trajectory
        :return: None
        """

        for frame in trajectory:
            opt_traj = []
            # Convert coordinates from bohr to angstroms
            geometry = np.array(frame['molecule']['geometry']) * 0.529177210
            for i, atom in enumerate(frame['molecule']['symbols']):
                opt_traj.append([atom, geometry[0 + i * 3], geometry[1 + i * 3], geometry[2 + i * 3]])
            self.molecule['traj'].append(opt_traj)

    def find_impropers(self):
        """
        Take the topology graph and find all of the improper torsions in the molecule;
        these are atoms with 3 bonds.
        """

        improper_torsions = []

        for node in self.topology.nodes:
            near = sorted(list(nx.neighbors(self.topology, node)))
            # if the atom has 3 bonds it could be an improper
            if len(near) == 3:
                improper_torsions.append((node, near[0], near[1], near[2]))

        if bool(improper_torsions):
            self.improper_torsions = improper_torsions

    def find_angles(self):
        """
        Take the topology graph network and return a list of all angle combinations.
        Checked against OPLS-AA on molecules containing 10-63 angles.
        """

        angles = []

        for node in self.topology.nodes:
            bonded = sorted(list(nx.neighbors(self.topology, node)))

            # Check that the atom has more than one bond
            if len(bonded) < 2:
                continue

            # Find all possible angle combinations from the list
            for i in range(len(bonded)):
                for j in range(i + 1, len(bonded)):
                    atom1, atom3 = bonded[i], bonded[j]

                    angles.append((atom1, node, atom3))

        if bool(angles):
            self.angles = angles

    def get_bond_lengths(self, input_type='input'):
        """For the given molecule and topology find the length of all of the bonds."""

        bond_lengths = {}

        molecule = self.molecule[input_type]

        for edge in self.topology.edges:
            atom1 = np.array(molecule[int(edge[0]) - 1][1:])
            atom2 = np.array(molecule[int(edge[1]) - 1][1:])
            self.bond_lengths[edge] = np.linalg.norm(atom2 - atom1)

        # Check if the dictionary is full then store else leave as None
        if bool(bond_lengths):
            self.bond_lengths = bond_lengths

    def find_dihedrals(self):
        """
        Take the topology graph network and again return a dictionary of all possible dihedral combinations stored under
        the central bond keys which describe the angle.
        """

        dihedrals = {}

        # Work through the network using each edge as a central dihedral bond
        for edge in self.topology.edges:

            for start in list(nx.neighbors(self.topology, edge[0])):

                # Check atom not in main bond
                if start != edge[0] and start != edge[1]:

                    for end in list(nx.neighbors(self.topology, edge[1])):

                        # Check atom not in main bond
                        if end != edge[0] and end != edge[1]:

                            if edge not in dihedrals:
                                # Add the central edge as a key the first time it is used
                                dihedrals[edge] = [(start, edge[0], edge[1], end)]

                            else:
                                # Add the tuple to the correct key.
                                dihedrals[edge].append((start, edge[0], edge[1], end))

        if bool(dihedrals):
            self.dihedrals = dihedrals

    def find_rotatable_dihedrals(self):
        """
        For each dihedral in the topology graph network and dihedrals dictionary, work out if the torsion is
        rotatable. Returns a list of dihedral dictionary keys representing the rotatable dihedrals.
        Also exclude standard rotations such as amides and methyl groups.
        """

        if bool(self.dihedrals):
            rotatable = []

            # For each dihedral key remove the edge from the network
            for key in self.dihedrals:
                self.topology.remove_edge(*key)

                # Check if there is still a path between the two atoms in the edges.
                if not nx.has_path(self.topology, key[0], key[1]):
                    rotatable.append(key)

                # Add edge back to the network and try next key
                self.topology.add_edge(*key)

            if bool(rotatable):
                self.rotatable = rotatable

    def get_dihedral_values(self, input_type='input'):
        """
        Taking the molecules' xyz coordinates and dihedrals dictionary, return a dictionary of dihedral
        angle keys and values. Also an option to only supply the keys of the dihedrals you want to calculate.
        """
        if bool(self.dihedrals):

            dih_phis = {}

            molecule = self.molecule[input_type]

            for key in self.dihedrals.keys():
                for torsion in self.dihedrals[key]:
                    # Calculate the dihedral angle in the molecule using the molecule data array.
                    x1, x2, x3, x4 = [np.array(molecule[int(torsion[i]) - 1][1:]) for i in range(4)]
                    b1, b2, b3 = x2 - x1, x3 - x2, x4 - x3
                    t1 = np.linalg.norm(b2) * np.dot(b1, np.cross(b2, b3))
                    t2 = np.dot(np.cross(b1, b2), np.cross(b2, b3))
                    dih_phis[torsion] = np.degrees(np.arctan2(t1, t2))

            if bool(dih_phis):
                self.dih_phis = dih_phis

    def get_angle_values(self, input_type='input'):
        """
        For the given molecule and list of angle terms measure the angle values,
        then return a dictionary of angles and values.
        """

        angle_values = {}

        molecule = self.molecule[input_type]

        for angle in self.angles:
            x1 = np.array(molecule[int(angle[0]) - 1][1:])
            x2 = np.array(molecule[int(angle[1]) - 1][1:])
            x3 = np.array(molecule[int(angle[2]) - 1][1:])
            b1, b2 = x1 - x2, x3 - x2
            cosine_angle = np.dot(b1, b2) / (np.linalg.norm(b1) * np.linalg.norm(b2))
            angle_values[angle] = np.degrees(np.arccos(cosine_angle))

        if bool(angle_values):
            self.angle_values = angle_values

    def write_parameters(self, name=None, protein=False):
        """Take the molecule's parameter set and write an xml file for the molecule."""

        # First build the xml tree
        self.build_tree(protein=protein)

        tree = self.xml_tree.getroot()
        messy = tostring(tree, 'utf-8')

        pretty_xml_as_string = parseString(messy).toprettyxml(indent="")

        with open(f'{name if name is not None else self.name}.xml', 'w+') as xml_doc:
            xml_doc.write(pretty_xml_as_string)

    def build_tree(self, protein):
        """Separates the parameters and builds an xml tree ready to be used."""

        # Create XML layout
        root = Element('ForceField')
        AtomTypes = SubElement(root, "AtomTypes")
        Residues = SubElement(root, "Residues")

        if protein:
            Residue = SubElement(Residues, "Residue", name="QUP")
        else:
            Residue = SubElement(Residues, "Residue", name="UNK")

        HarmonicBondForce = SubElement(root, "HarmonicBondForce")
        HarmonicAngleForce = SubElement(root, "HarmonicAngleForce")
        PeriodicTorsionForce = SubElement(root, "PeriodicTorsionForce")

        # Assign the combination rule
        c14 = '0.83333' if self.combination == 'amber' else '0.5'
        l14 = '0.5'

        # add the combination rule to the xml for geometric.
        NonbondedForce = SubElement(root, "NonbondedForce", attrib={'coulomb14scale': c14, 'lj14scale': l14,
                                                                    'combination': self.combination})

        for key, val in self.AtomTypes.items():
            SubElement(AtomTypes, "Type", attrib={
                'name': val[1], 'class': val[2],
                'element': self.molecule['input'][key][0],
                'mass': str(self.element_dict[self.molecule['input'][key][0].upper()])})

            SubElement(Residue, "Atom", attrib={'name': val[0], 'type': val[1]})

        # Add the bonds / connections
        for key, val in self.HarmonicBondForce.items():
            SubElement(Residue, "Bond", attrib={'from': str(key[0]), 'to': str(key[1])})

            SubElement(HarmonicBondForce, "Bond", attrib={
                'class1': self.AtomTypes[key[0]][2],
                'class2': self.AtomTypes[key[1]][2],
                'length': val[0], 'k': val[1]})

        # Add the angles
        for key, val in self.HarmonicAngleForce.items():
            SubElement(HarmonicAngleForce, "Angle", attrib={
                'class1': self.AtomTypes[key[0]][2],
                'class2': self.AtomTypes[key[1]][2],
                'class3': self.AtomTypes[key[2]][2],
                'angle': val[0], 'k': val[1]})

        # add the proper and improper torsion terms
        for key in self.PeriodicTorsionForce:
            if self.PeriodicTorsionForce[key][-1] == 'Improper':
                tor_type = 'Improper'
            else:
                tor_type = 'Proper'
            SubElement(PeriodicTorsionForce, tor_type, attrib={
                'class1': self.AtomTypes[key[0]][2],
                'class2': self.AtomTypes[key[1]][2],
                'class3': self.AtomTypes[key[2]][2],
                'class4': self.AtomTypes[key[3]][2],
                'k1': self.PeriodicTorsionForce[key][0][1],
                'k2': self.PeriodicTorsionForce[key][1][1],
                'k3': self.PeriodicTorsionForce[key][2][1],
                'k4': self.PeriodicTorsionForce[key][3][1],
                'periodicity1': '1', 'periodicity2': '2',
                'periodicity3': '3', 'periodicity4': '4',
                'phase1': self.PeriodicTorsionForce[key][0][2],
                'phase2': self.PeriodicTorsionForce[key][1][2],
                'phase3': self.PeriodicTorsionForce[key][2][2],
                'phase4': self.PeriodicTorsionForce[key][3][2]})

        # add the non-bonded parameters
        for key in self.NonbondedForce:
            SubElement(NonbondedForce, "Atom", attrib={
                'type': self.AtomTypes[key][1],
                'charge': self.NonbondedForce[key][0],
                'sigma': self.NonbondedForce[key][1],
                'epsilon': self.NonbondedForce[key][2]})

        # Add all of the virtual site info if present
        if self.sites:
            # Add the atom type to the top
            for key, val in self.sites.items():
                SubElement(AtomTypes, "Type", attrib={'name': f'v-site{key + 1}', 'class': f'X{key + 1}', 'mass': '0'})

                # Add the atom info
                SubElement(Residue, "Atom", attrib={'name': f'X{key + 1}', 'type': f'v-site{key + 1}'})

                # Add the local coords site info
                SubElement(Residue, "VirtualSite", attrib={
                    'type': 'localCoords', 'index': str(key + len(self.atom_names)),
                    'atom1': str(val[0][0]), 'atom2': str(val[0][1]), 'atom3': str(val[0][2]),
                    'wo1': '1.0', 'wo2': '0.0', 'wo3': '0.0', 'wx1': '-1.0', 'wx2': '1.0', 'wx3': '0.0',
                    'wy1': '-1.0', 'wy2': '0.0', 'wy3': '1.0',
                    'p1': f'{float(val[1][0]):.4f}',
                    'p2': f'{float(val[1][1]):.4f}',
                    'p3': f'{float(val[1][2]):.4f}'})

                # Add the nonbonded info
                SubElement(NonbondedForce, "Atom", attrib={
                    'type': f'v-site{key + 1}',
                    'charge': f'{val[2]}',
                    'sigma': '1.000000',
                    'epsilon': '0.000000'})

        # Store the tree back into the molecule
        self.xml_tree = ElementTree(root)

    def write_xyz(self, input_type='input', name=None):
        """
        Write a general xyz file of the molecule if there are multiple geometries in the molecule write a traj
        :param input_type: Where the molecule coordinates are to be wrote from
        :param name: The name of the xyz file to be produced
        :return: None
        """

        with open(f'{name if name is not None else self.name}.xyz', 'w+') as xyz_file:

            if len(self.molecule[input_type]) / len(self.atom_names) == 1:
                message = 'xyz file generated with QUBEKit'
                end = ''
                trajectory = [self.molecule[input_type]]

            else:
                message = f'QUBEKit xyz trajectory FRAME '
                end = 1
                trajectory = self.molecule[input_type]

            # Write out each frame
            for frame in trajectory:

                xyz_file.write(f'{len(self.atom_names)}\n')
                xyz_file.write(f'{message}{end}\n')

                for atom in frame:
                    xyz_file.write(f'{atom[0]}       {atom[1]: .10f}   {atom[2]: .10f}   {atom[3]: .10f} \n')

                try:
                    end += 1
                except TypeError:
                    # This is the result of only printing one frame so catch the error and ignore
                    pass

    def write_gromacs_file(self, input_type='input'):
        """To a gromacs file, write and format the necessary variables."""

        with open(f'{self.name}.gro', 'w+') as gro_file:
            gro_file.write(f'NEW {self.name.upper()} GRO FILE\n')
            gro_file.write(f'{len(self.molecule[input_type]):>5}\n')
            for pos, atom in enumerate(self.molecule[input_type], 1):
                # 'mol number''mol name'  'atom name'   'atom count'   'x coord'   'y coord'   'z coord'
                # 1WATER  OW1    1   0.126   1.624   1.679
                gro_file.write(f'    1{self.name.upper()}  {atom[0]}{pos}   {pos}   {atom[1]: .3f}   {atom[2]: .3f}   {atom[3]: .3f}\n')

    def pickle(self, state=None):
        """
        Pickles the Molecule object in its current state to the (hidden) pickle file.
        If other pickle objects already exist for the particular object:
            the latest object is put to the top.
        """

        mols = OrderedDict()
        # First check if the pickle file exists
        try:
            # Try to load a hidden pickle file; make sure to get all objects
            with open(f'.QUBEKit_states', 'rb') as pickle_jar:
                while True:
                    try:
                        mol = pickle.load(pickle_jar)
                        mols[mol.state] = mol
                    except:
                        break
        except FileNotFoundError:
            # TODO Should this only pass if we're on the first stage? i.e. if the file hasn't been made yet
            pass

        # Now we can save the items; first assign the location
        self.state = state
        mols[self.state] = self

        # Open the pickle jar which will always be the ligand object's name
        with open(f'.QUBEKit_states', 'wb') as pickle_jar:
            # If there were other molecules of the same state in the jar: overwrite them

            for val in mols.values():
                pickle.dump(val, pickle_jar)

    def symmetrise_from_topo(self):
        """
        Based on the molecule topology, symmetrise the methyl / amine hydrogens.
        If there's a carbon, does it have 3 hydrogens? -> symmetrise
        If there's a nitrogen, does it have 2 hydrogens? -> symmetrise
        Also keep a list of the methyl carbons and amine / nitrile nitrogens
        then exclude these bonds from the rotatable torsions list.
        """

        methyl_hs = []
        amine_hs = []
        methyl_amine_nitride_cores = []
        for pos, atom_coords in enumerate(self.molecule['input']):
            if atom_coords[0] == 'C' or atom_coords[0] == 'N':

                hs = []
                for atom in self.topology.neighbors(pos + 1):
                    if len(list(self.topology.neighbors(atom))) == 1:
                        # now make sure it is a hydrogen (as halogens could be caught here)
                        if self.molecule['input'][atom - 1][0] == 'H':
                            hs.append(atom)
                if atom_coords[0] == 'C' and len(hs) == 3:
                    methyl_hs.append(hs)
                    methyl_amine_nitride_cores.append(pos + 1)
                if atom_coords[0] == 'N' and len(hs) == 2:
                    amine_hs.append(hs)
                    methyl_amine_nitride_cores.append(pos + 1)
                if atom_coords[0] == 'N' and len(hs) == 1:
                    methyl_amine_nitride_cores.append(pos + 1)

        self.symm_hs = {'methyl': methyl_hs, 'amine': amine_hs}

        # now modify the rotatable list to remove methyl and amine/ nitrile torsions
        # these are already well represented in most FF's
        remove_list = []
        if self.rotatable:
            rotatable = self.rotatable
            for key in rotatable:
                if key[0] in methyl_amine_nitride_cores or key[1] in methyl_amine_nitride_cores:
                    remove_list.append(key)

            # now remove the keys
            for torsion in remove_list:
                rotatable.remove(torsion)

            self.rotatable = rotatable

    def update(self, input_type='input'):
        """
        After the protein has been passed to the parametrisation class we get back the bond info
        use this to update all missing terms.
        """

        # using the new harmonic bond force dict we can add the bond edges to the topology graph
        for key in self.HarmonicBondForce:
            self.topology.add_edge(key[0] + 1, key[1] + 1)

        self.find_angles()
        self.find_dihedrals()
        self.find_rotatable_dihedrals()
        self.get_dihedral_values(input_type)
        self.get_bond_lengths(input_type)
        self.get_angle_values(input_type)
        self.find_impropers()
        # this creates the dictionary of terms that should be symmetrise
        self.symmetrise_from_topo()


class Ligand(Molecule):

    def __init__(self, filename, smiles_string=None):
        """
        scan_order              A list of the dihedral cores to be scanned in the scan order
        parameter_engine        A string keeping track of the parameter engine used to assign the initial parameters
        hessian                 2d numpy array; matrix of size 3N x 3N where N is number of atoms in the molecule
        modes                   A list of the qm predicted frequency modes
        qm_scan_energy
        descriptors
        constraints_file        Either an empty string (does nothing in geometric run command); or
                                the abspath of the constraint.txt file (constrains the execution of geometric)
        """

        super().__init__(filename, smiles_string)

        self.scan_order = None
        self.parameter_engine = None
        self.hessian = None
        self.modes = None

        self.qm_scan_energy = {}
        self.descriptors = {}

        self.constraints_file = ''

        self.read_file()
        # Make sure we have the topology before we calculate the properties
        if bool(self.topology.edges):
            self.find_angles()
            self.find_dihedrals()
            self.find_rotatable_dihedrals()
            self.find_impropers()
            self.get_dihedral_values()
            self.get_bond_lengths()
            self.get_angle_values()
            self.symmetrise_from_topo()

    def read_xyz(self, name, input_type='traj'):
        """
        Read an xyz file and get all frames from the file and put in the traj molecule holder by default
        or if there is only one frame change the input location.
        """

        traj_molecules = []
        molecule = []
        try:
            with open(name, 'r') as xyz_file:
                # get the number of atoms
                n_atoms = len(self.molecule['input'])
                for line in xyz_file:
                    line = line.split()
                    # skip frame heading lines
                    if len(line) <= 1:
                        next(xyz_file)
                        continue
                    else:
                        molecule.append([line[0], float(line[1]), float(line[2]), float(line[3])])
                    if len(molecule) == n_atoms:
                        # we have collected the molecule now store the frame
                        traj_molecules.append(molecule)
                        molecule = []
            self.molecule[input_type] = traj_molecules

        except FileNotFoundError:
            raise FileNotFoundError(
                'Cannot find xyz file to read.\nThis is likely due to PSI4 not generating one.\n'
                'Please ensure PSI4 is installed properly and can be called with the command: psi4\n'
                'Alternatively, geometric may not be installed properly.\n'
                'Please ensure it is and can be called with the command: geometric-optimize\n'
                'Installation instructions can be found on the respective github pages and '
                'elsewhere online, see README for more details.\n')

    def write_pdb(self, input_type='input', name=None):
        """
        Take the current molecule and topology and write a pdb file for the molecule.
        Only for small molecules, not standard residues. No size limit.
        """

        molecule = self.molecule[input_type]

        with open(f'{name if name is not None else self.name}.pdb', 'w+') as pdb_file:

            # Write out the atomic xyz coordinates
            pdb_file.write(f'REMARK   1 CREATED WITH QUBEKit {datetime.now()}\n')
            pdb_file.write(f'COMPND    {self.name:<20}\n')
            for i, atom in enumerate(molecule):
                pdb_file.write(
                    f'HETATM{i+1:>5} {self.atom_names[i]:>4} UNL     1{atom[1]:12.3f}{atom[2]:8.3f}{atom[3]:8.3f}  1.00  0.00          {atom[0]:2}\n')

            # Now add the connection terms
            for node in self.topology.nodes:
                bonded = sorted(list(nx.neighbors(self.topology, node)))
                if len(bonded) > 1:
                    pdb_file.write(f'CONECT{node:5}{"".join(f"{x:5}" for x in bonded)}\n')

            pdb_file.write('END\n')


class Protein(Molecule):
    """This class handles the protein input to make the qubekit xml files and rewrite the pdb so we can use it."""

    def __init__(self, filename):
        super().__init__(filename)

        self.pdb_names = None
        self.read_pdb()
        self.residues = None

    def read_pdb(self, input_type='input'):
        """
        Read the pdb file which probably does not have the right connections,
        so we need to find them using QUBE.xml
        """

        with open(self.filename, 'r') as pdb:
            lines = pdb.readlines()

        protein = []
        self.topology = nx.Graph()
        self.atom_names = []
        self.residues = []
        self.Residues = []
        self.pdb_names = []

        # atom counter used for graph node generation
        atom_count = 1
        for line in lines:
            if 'ATOM' in line or 'HETATM' in line:
                element = str(line[76:78])
                element = re.sub('[0-9]+', '', element)
                element = element.strip()

                # If the element column is missing from the pdb, extract the element from the name.
                if not element:
                    element = str(line.split()[2])
                    element = re.sub('[0-9]+', '', element)

                # now make sure we have a valid element
                if element.lower() == 'cl' or element.lower() == 'br':
                    pass
                else:
                    element = element[0]

                self.atom_names.append(f'{element}{atom_count}')
                self.pdb_names.append(str(line.split()[2]))

                # also get the residue order from the pdb file so we can rewrite the file
                self.Residues.append(str(line.split()[3]))

                # Also add the atom number as the node in the graph
                self.topology.add_node(atom_count)
                atom_count += 1
                protein.append([element, float(line[30:38]), float(line[38:46]), float(line[46:54])])

            if 'CONECT' in line:
                # Now look through the connectivity section and add all edges to the graph corresponding to the bonds.
                for i in range(2, len(line.split())):
                    if int(line.split()[i]) != 0:
                        self.topology.add_edge(int(line.split()[1]), int(line.split()[i]))

        # check if there are any conect terms in the file first
        if len(self.topology.edges) == 0:
            print('No connections found!')

        # Remove duplicates
        self.residues = [res for res, group in groupby(self.Residues)]

        self.molecule[input_type] = protein

    def write_pdb(self, name=None):
        """This method replaces the ligand method as all of the atom names and residue names have to be replaced."""

        molecule = self.molecule['input']

        with open(f'{name if name else self.name}.pdb', 'w+') as pdb_file:

            # Write out the atomic xyz coordinates
            pdb_file.write(f'REMARK   1 CREATED WITH QUBEKit {datetime.now()}\n')
            # pdb_file.write(f'COMPND    {self.name:<20}\n')
            # we have to transform the atom name while writing out the pdb file
            for i, atom in enumerate(molecule):
                # TODO conditional printing
                pdb_file.write(
                    f'HETATM{i+1:>5}{atom[0] + str(i+1):>5} QUP     1{atom[1]:12.3f}{atom[2]:8.3f}{atom[3]:8.3f}  1.00  0.00          {atom[0]:2}\n')

            # Now add the connection terms
            for node in self.topology.nodes:
                bonded = sorted(list(nx.neighbors(self.topology, node)))
                if len(bonded) > 1:
                    pdb_file.write(f'CONECT{node:5}{"".join(f"{x:5}" for x in bonded)}\n')

            pdb_file.write('END\n')
