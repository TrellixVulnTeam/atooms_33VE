# This file is part of atooms
# Copyright 2010-2017, Daniele Coslovich

"""LAMMPS trajectory format."""

import numpy

from .base import TrajectoryBase
from .folder import TrajectoryFolder
from atooms.system.particle import Particle, distinct_species
from atooms.system.cell import Cell
from atooms.system import System


class TrajectoryLAMMPS(TrajectoryBase):

    """
    Trajectory layout for LAMMPS.

    In write mode, an additional .inp file is used as startup file.
    """

    def __init__(self, filename, mode='r'):
        TrajectoryBase.__init__(self, filename, mode)
        self._fh = open(self.filename, self.mode)
        if mode == 'r':
            self._setup_index()
            self._setup_steps()

    def _setup_index(self):
        """Sample indexing via tell / seek"""
        from collections import defaultdict
        self._fh.seek(0)
        self._index_db = defaultdict(list)
        while True:
            line = self._fh.tell()
            data = self._fh.readline()
            # We break if file is over or we found an empty line
            if not data:
                break
            if data.startswith('ITEM:'):                
                for block in ['TIMESTEP', 'NUMBER OF ATOMS', 'BOX BOUNDS', 'ATOMS']:
                    if data[6:].startswith(block):
                        # entry contains whatever is found after block
                        entry = data[7+len(block):]
                        self._index_db[block].append((line, entry))
                        break
        self._fh.seek(0)

    def _setup_steps(self):
        self.steps = []
        for idx, _ in self._index_db['TIMESTEP']:
            self._fh.seek(idx)
            self._fh.readline()
            step = int(self._fh.readline())
            self.steps.append(step)
        self._fh.seek(0)

    def read_sample(self, frame):
        # TODO: respect input frame
        idx, _ = self._index_db['TIMESTEP'][frame]
        self._fh.seek(idx)
        self._fh.readline()
        step = int(self._fh.readline())

        # Read number of particles
        idx, _ = self._index_db['NUMBER OF ATOMS'][frame]
        self._fh.seek(idx)
        self._fh.readline()
        data = self._fh.readline()
        npart = int(data)

        # Read box
        idx, data = self._index_db['BOX BOUNDS'][frame]
        self._fh.seek(idx)
        self._fh.readline()
        ndim = len(data.split())  # line is ITEM: BOX BONDS pp pp pp
        L, offset = [], []
        for i in range(ndim):
            data = [float(x) for x in self._fh.readline().split()]
            L.append(data[1] - data[0])
        cell = Cell(numpy.array(L))

        # Read atoms data
        idx, data = self._index_db['ATOMS'][frame]
        # Determine how many fields are there
        fields = data.split()
        nfields = len(data)

        def parse_type(data, particle):
            particle.species = data
        def parse_x(data, particle):
            particle.position[0] = float(data)
        def parse_y(data, particle):
            particle.position[1] = float(data)
        def parse_z(data, particle):
            particle.position[2] = float(data)
        def parse_xs(data, particle):
            particle.position[0] = (float(data)-0.5) * cell.side[0]
        def parse_ys(data, particle):
            particle.position[1] = (float(data)-0.5) * cell.side[1]
        def parse_zs(data, particle):
            particle.position[2] = (float(data)-0.5) * cell.side[2]
        def parse_vx(data, particle):
            particle.velocity[0] = float(data)
        def parse_vy(data, particle):
            particle.velocity[1] = float(data)
        def parse_vz(data, particle):
            particle.velocity[2] = float(data)

        _cbk = {'x': parse_x, 'y': parse_y, 'z': parse_z,
                'vx': parse_vx, 'vy': parse_vy, 'vz': parse_vz,
                'xu': parse_x, 'yu': parse_y, 'zu': parse_z,
                'xs': parse_xs, 'ys': parse_ys, 'zs': parse_zs,
                'xsu': parse_xs, 'ysu': parse_ys, 'zsu': parse_zs,
                'type': parse_type}

        _ = self._fh.readline()
        particles = [Particle() for i in range(npart)]
        for i in range(npart):
            data = self._fh.readline().split()
            # Accept unsorted particles by parsing their id
            if 'id' in fields:
                idx = int(data[0]) - 1
            else:
                idx = i

            for j, field in enumerate(fields):
                if field in _cbk:
                    _cbk[field](data[j], particles[idx])
                else:
                    # We should store these fields in particle anyway
                    pass

        return System(particle=particles, cell=cell)

    def write_init(self, system):
        f = open(self.filename + '.inp', 'w')
        np = len(system.particle)
        L = system.cell.side
        sp = distinct_species(system.particle)

        # LAMMPS header
        h = '\n'
        h += "%i atoms\n" % np
        h += "%i atom types\n" % len(sp)
        h += "%g %g  xlo xhi\n" % (-L[0]/2, L[0]/2)
        h += "%g %g  ylo yhi\n" % (-L[1]/2, L[1]/2)
        h += "%g %g  zlo zhi\n" % (-L[2]/2, L[2]/2)
        f.write(h + '\n')

        # LAMMPS body
        # Masses of species
        m = "\nMasses\n\n"
        for isp in range(len(sp)):
            # Iterate over particles. Find instances of species and get masses
            for p in system.particle:
                if p.species == sp[isp]:
                    m += '%s %g\n' % (isp+1, p.mass)
                    break

        # Atom coordinates
        r = "\nAtoms\n\n"
        v = "\nVelocities\n\n"
        for i, p in enumerate(system.particle):
            r += '%s %s %g %g %g\n' % tuple([i+1, sp.index(p.species)+1] + list(p.position))
            v += '%s    %g %g %g\n' % tuple([i+1] + list(p.velocity))

        f.write(m)
        f.write(r)
        f.write(v)
        f.close()

    def write_sample(self, system, step):
        pass


class TrajectoryFolderLAMMPS(TrajectoryFolder):

    """
    Trajectory layout for LAMMPS.

    In write mode, an additional .inp file is used as startup file.
    """

    suffix = '.tgz'

    def __init__(self, filename, mode='r', file_pattern='*', step_pattern=r'[a-zA-Z\.]*(\d*)'):
        TrajectoryFolder.__init__(self, filename, mode=mode,
                                  file_pattern=file_pattern,
                                  step_pattern=step_pattern)

    def read_sample(self, frame):
        with TrajectoryLAMMPS(self.files[frame], 'r') as th:
            return th[0]

    def write_init(self, system):
        f = open(self.filename + '.inp', 'w')
        np = len(system.particle)
        L = system.cell.side
        sp = distinct_species(system.particle)

        # LAMMPS header
        h = '\n'
        h += "%i atoms\n" % np
        h += "%i atom types\n" % len(sp)
        h += "%g %g  xlo xhi\n" % (-L[0]/2, L[0]/2)
        h += "%g %g  ylo yhi\n" % (-L[1]/2, L[1]/2)
        h += "%g %g  zlo zhi\n" % (-L[2]/2, L[2]/2)
        f.write(h + '\n')

        # LAMMPS body
        # Masses of species
        m = "\nMasses\n\n"
        for isp in range(len(sp)):
            # Iterate over particles. Find instances of species and get masses
            for p in system.particle:
                if p.species == sp[isp]:
                    m += '%s %g\n' % (isp+1, p.mass)
                    break

        # Atom coordinates
        r = "\nAtoms\n\n"
        v = "\nVelocities\n\n"
        for i, p in enumerate(system.particle):
            r += '%s %s %g %g %g\n' % tuple([i+1, sp.index(p.species)+1] + list(p.position))
            v += '%s    %g %g %g\n' % tuple([i+1] + list(p.velocity))

        f.write(m)
        f.write(r)
        f.write(v)
        f.close()

    def write_sample(self, system, step):
        # We cannot write
        return

# Note: to get the tabulated potential from a dump of potential.x do
# > { echo -e "\nPOTENTIAL\nN 10000\n"; grep -v '#' /tmp/kalj.ff.potential.1-1 | \
#    awk '{printf "%i %g %12e %12e\n", NR, $1, $2, -$3}' ; }
