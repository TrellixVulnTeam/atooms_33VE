#!/usr/bin/env python

"""Convert trajectory file to a different format."""

import os
import sys
import logging
import argparse
import random
from atooms import trajectory
from atooms.core.utils import fractional_slice, add_first_last_skip
from atooms.trajectory.utils import check_block_size, info, formats


def main(args):
    """Convert trajectory `file_inp` to `file_out`."""
    if args.file_out == '-':
        args.file_out = '/dev/stdout'

    if args.folder:
        t = trajectory.folder.Foldered(args.file_inp, cls=args.inp)
    else:
        t = trajectory.Trajectory(args.file_inp, fmt=args.inp)

    if args.info:
        print info(t)
        return

    # If no output format is provided we use the input one
    if args.out is None:
        out_class = t.__class__
    else:
        out_class = args.out

    if args.precision is not None:
        t.precision = args.precision

    if args.flatten_steps:
        t.steps = range(1,len(t)+1)

    # Reset random number generator
    if args.seed:
        random.seed(args.seed)

    # Trick to allow some trajectory formats to set the box side.
    # This way the cell is defined as we read the sample (callbacks
    # will not do that).
    if args.side is not None:
        t._side = args.side

    # Define slice.
    # We interpret --first N --last N as a request of step N
    if args.last == args.first and args.last is not None:
        args.last += 1
    sl = fractional_slice(args.first, args.last, args.skip, len(t))

    # Unfold if requested
    if args.unfold:
        tu = trajectory.Unfolded(t) #, fix_cm=True)
    else:
        tu = t

    # Fix CM and fold back
    if args.fix_cm:
        tu.add_callback(trajectory.fix_cm)
        tu.add_callback(trajectory.fold)

    # Here we could you a trajectory slice t[sl] but this will load
    # everything in ram (getitem doesnt provide a generator). This
    # will be fixed with python 3.
    ts = trajectory.Sliced(tu, sl)

    # Change density and temperature
    if args.rho is not None:
        ts.register_callback(trajectory.decorators.set_density, args.rho)
    if args.temperature is not None:
        ts.register_callback(trajectory.decorators.set_temperature, args.temperature)
    # Change species layout if requested
    if args.species_layout is not None:
        ts.register_callback(trajectory.decorators.change_species, args.species_layout)

    # We enforce regular periodicity; steps is None is trajectory is not periodic
    steps = check_block_size(ts.steps, ts.block_size, prune=True)
    
    #
    # ---------------------
    # Trajectory conversion
    # ---------------------
    #
    include_list, exclude_list = [], []
    if len(args.fmt_include) > 0:
        include_list = args.fmt_include.split(',')
    if len(args.fmt_exclude) > 0:
        exclude_list = args.fmt_exclude.split(',')
    fout = trajectory.convert(ts, out_class, args.file_out,
                              fmt=args.fmt, include=include_list,
                              exclude=exclude_list, steps=steps)

    if args.ff:
        from atooms.trajectory.hdf5 import add_interaction_hdf5
        add_interaction_hdf5(fout, args.ff)
    
    if args.file_out != '/dev/stdout':
        print '%s' % fout

    t.close()

if __name__ == '__main__':

    parser = argparse.ArgumentParser(epilog=formats(), 
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser = add_first_last_skip(parser)
    parser.add_argument(      '--fmt-fields', dest='fmt', help='format fields')
    parser.add_argument('-I', '--fmt-include', dest='fmt_include', type=str, default='', help='include patterns in format')
    parser.add_argument('-E', '--fmt-exclude', dest='fmt_exclude', type=str, default='', help='exclude patterns from format')
    parser.add_argument('-i', '--fmt-inp', dest='inp', help='input format ')
    parser.add_argument('-o', '--fmt-out', dest='out', help='output format for conversion')
    parser.add_argument(      '--folder', dest='folder', action='store_true', help='force folder-based layout')
    parser.add_argument('-F', '--ff', dest='ff', type=str, default='', help='force field file')
    parser.add_argument(      '--flatten-steps',dest='flatten_steps', action='store_true', help='use sample index instead of steps')
    parser.add_argument(      '--unfold',dest='unfold', action='store_true', help='unfold')
    parser.add_argument(      '--fix-cm',dest='fix_cm', action='store_true', help='fix cm')
    parser.add_argument(      '--side', dest='side', type=float, default=None, help='set cell side')
    parser.add_argument(      '--density', dest='rho', type=float, default=None, help='new density')
    parser.add_argument('-T', '--temperature', dest='temperature', type=float, default=None, help='new temperature')
    parser.add_argument(      '--precision', dest='precision', type=int, default=None, help='write precision')
    parser.add_argument(      '--species-layout',dest='species_layout', default=None, help='modify species layout (A, C, F)')
    parser.add_argument(      '--info', dest='info', action='store_true', help='print info')
    parser.add_argument(      '--seed', dest='seed', type=int, help='set seed of random number generator')
    parser.add_argument(nargs=1, dest='file_inp', default='-', help='input file')
    parser.add_argument(nargs='?', dest='file_out', default='-', help='output file')
    args = parser.parse_args()

    if args.fmt is not None:
        args.fmt = args.fmt.split(',')

    if args.out is not None and not args.out in trajectory.Trajectory.formats:
        available_formats()   
        raise ValueError('Unknown output format %s' % args.out)

    args.file_inp = args.file_inp[0]

    main(args)
