# This file is part of atooms
# Copyright 2010-2017, Daniele Coslovich

"""Point particles in a cartesian reference frame."""

import numpy
import random
from copy import deepcopy
from atooms.core import ndim as _ndim


class Particle(object):

    def __init__(self, species='A', mass=1.0, position=None,
                 velocity=None, radius=0.5):
        self.species = species
        """The chemical species of the particle."""
        self.mass = mass
        self.radius = radius
        if position is None:
            self.position = numpy.zeros(_ndim)
        else:
            self.position = numpy.asarray(position)
        if velocity is None:
            self.velocity = numpy.zeros(_ndim)
        else:
            self.velocity = numpy.asarray(velocity)

    @property
    def diameter(self):
        """Particle diameter."""
        return self.radius * 2

    def nearest_image(self, particle, cell, copy=False):
        """
        Return the nearest image of `particle` in the given `cell`.

        If `copy` is `False`, the particle is transformed into to its
        nearest image, otherwise the fucction returns a copy of the
        nearest image particle and leave the original particle as is.
        """
        rij = self.position - particle.position
        _periodic_vector(rij, cell.side)
        if copy:
            image = deepcopy(self)
            image.position = particle.position + rij
            return image
        else:
            self.position = particle.position + rij
            return self

    def distance(self, particle, cell=None, folded=True):
        """
        Return the distance from another `particle`.

        If `cell` is given, return the distance from the nearest image
        of `particle`. In this case, if `folded` is True, the
        coordinates are assumed to be folded into the central cell (or
        in a cell just next to it), otherwise they will be assumed to
        lie in an arbitrary periodic cell.

        If `cell` is None, periodic boundary conditions are *not*
        applied and folded is irrelevant.
        """
        r = self.position - particle.position
        if cell is not None:
            # Apply periodic boundary conditions
            if folded:
                r = _periodic_vector(r, cell.side)
            else:
                r = _periodic_vector_unfolded(r, cell.sidebox)
        return r

    def __repr__(self):
        return 'Particle(species={0.species}, mass={0.mass}, ' \
            'position={0.position}, velocity={0.velocity}, ' \
            'radius={0.radius})'.format(self)

    def fold(self, cell):
        """Fold self into central cell."""
        self.position = _periodic_vector_unfolded(self.position, cell.side)
        return self

    def maxwellian(self, T):
        """
        Assign the velocity to particle according to a Maxwell-Boltzmann
        distribution at temperature `T`.
        """
        vx = random.gauss(0, numpy.sqrt(T / self.mass))
        vy = random.gauss(0, numpy.sqrt(T / self.mass))
        vz = random.gauss(0, numpy.sqrt(T / self.mass))
        self.velocity = numpy.array((vx, vy, vz))

    @property
    def kinetic_energy(self):
        """Kinetic energy."""
        return 0.5 * self.mass * numpy.dot(self.velocity, self.velocity)


# Utility functions

def _periodic_vector(vec, box):
    for i in range(vec.shape[0]):
        if vec[i] > box[i] / 2:
            vec[i] += - box[i]
        elif vec[i] < -box[i] / 2:
            vec[i] += box[i]
    # Compact version
    # return numpy.where(abs(a) > box/2, a-numpy.copysign(box, a), a)
    return vec

def _periodic_vector_unfolded(vec, box):
    return vec - numpy.rint(vec / box) * box
    # Optimized version
    # return vec - numpy.rint(vec * invbox) * box

def fix_total_momentum(particles):
    """
    Subtract out the center of mass velocity from a list of
    `particles`.
    """
    vcm = cm_velocity(particles)
    for p in particles:
        p.velocity -= vcm
    return particles

def cm_velocity(particle):
    """Velocity of the center of mass of a list of particles."""
    vcm = numpy.zeros_like(particle[0].velocity)
    mtot = 0.0
    for p in particle:
        vcm += p.velocity * p.mass
        mtot += p.mass
    return vcm / mtot

def cm_position(particle):
    """Center-of-mass of a list of particles."""
    rcm = numpy.zeros_like(particle[0].position)
    mtot = 0.0
    for p in particle:
        rcm += p.position * p.mass
        mtot += p.mass
    return rcm / mtot

def distinct_species(particles):
    """Return sorted list of distinct `species` of `particles`."""
    return list(sorted(set([p.species for p in particles])))

def composition(particles):
    """
    Return a dictionary containing the number of particles of each
    species appearing the input `particles` list.
    """
    from collections import defaultdict
    comp = defaultdict(int)
    for p in particles:
        comp[p.species] += 1
    return comp

def rotate(particle, cell):
    """
    Return a list of particles rotated around the main symmetry axis
    of the set.
    """
    import math

    def norm2(vec):
        return numpy.dot(vec, vec)

    def rotation(axis, theta):
        """
        Return the rotation matrix associated with counterclockwise rotation about
        the given axis by theta radians.
        """
        axis = numpy.asarray(axis)
        theta = numpy.asarray(theta)
        axis = axis / math.sqrt(numpy.dot(axis, axis))
        a = math.cos(theta / 2.0)
        b, c, d = -axis * math.sin(theta / 2.0)
        aa, bb, cc, dd = a * a, b * b, c * c, d * d
        bc, ad, ac, ab, bd, cd = b * c, a * d, a * c, a * b, b * d, c * d
        return numpy.array([[aa + bb - cc - dd, 2 * (bc + ad), 2 * (bd - ac)],
                            [2 * (bc - ad), aa + cc - bb - dd, 2 * (cd + ab)],
                            [2 * (bd + ac), 2 * (cd - ab), aa + dd - bb - cc]])

    p = deepcopy(particle)
    dist = [sum(p[0].distance(pi, cell)**2) for pi in p]
    dmax = max(dist)
    imax = dist.index(dmax)
    z_axis = numpy.array([0, -1, 0])
    pr_axis = p[0].position - p[imax].position
    ro_axis = numpy.cross(pr_axis, z_axis)
    theta = math.acos(numpy.dot(pr_axis, z_axis) / (norm2(pr_axis) * norm2(z_axis))**0.5)
    for pi in p:
        pi.position = numpy.dot(rotation(ro_axis, theta), pi.position)


def overlaps(particle, cell):
    """Check presence of overlaps between particles."""
    x = []
    for i, pi in enumerate(particle):
        for j, pj in enumerate(particle):
            if j <= i:
                continue
            d = sum(pi.distance(pj, cell)**2)**0.5
            if d < (pi.radius + pj.radius):
                x.append((i, j))
    return len(x) > 0, x



def gyration_radius(particles, cell=None, weight=None, center=None,
                    method="N1"):
    """
    Gyration radius of a list of `particles` in a `cell` with an
    optional `weight`.

    The optional `center` variable is the index of the central
    particle for pbc unfolding. If `weight` is given but `center` is
    not, the latter will be the index of the first largest element of
    `weight`.

    Possible values of `methods` are `N1` (default), `N2` and `min`.
    """
    if method not in ['N1', 'N2', 'min']:
        raise ValueError('unknown method %s' % method)

    # Order N^2 calculation
    if method == 'N2':
        rg = 0.0
        for pi in particles:
            for pj in particles:
                if pi is pj:
                    continue
                dr = pi.distance(pj, cell)
                rg += numpy.dot(dr, dr)
        return (rg / (2*len(particles)**2))**0.5

    # Order N^1 calculation
    elif method == 'N1':
        # Assign weights
        if weight is None:
            weight = numpy.ones(len(particles))
            if center is None:
                center = 0
        else:
            if len(weight) != len(particles):
                raise ValueError('n. weights differs from n. particles')
            weight = numpy.asarray(weight)
            if center is None:
                center = weight.argmax()

        # Unfold cluster across pbc
        p_central = particles[center]
        if cell is None:
            cluster = particles
        else:
            cluster = []
            for p in particles:
                cluster.append(p.nearest_image(p_central, cell, copy=True))

        # Compute gyration radius
        rcm = cm_position(cluster)
        rg = 0.0
        for p in cluster:
            dr = p.position - rcm
            rg += numpy.dot(dr, dr)
        rg /= len(cluster)
        return rg**0.5

    # Minimize over possible centers
    elif method == 'min':
        rg = None
        for center in range(len(particles)):
            rg_new = gyration_radius(particles, cell=cell,
                                     weight=weight, center=center,
                                     method="N1")
            if rg is None:
                rg = rg_new
            else:
                rg = min(rg_new, rg)
        return rg
