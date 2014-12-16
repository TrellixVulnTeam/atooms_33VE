# This file is part of atooms
# Copyright 2010-2014, Daniele Coslovich

"""Simulation base class handling callbacks logic"""

import sys
import os
import time
import logging
import copy

log = logging.getLogger('atooms')

# Default exceptions

class SimulationEnd(Exception):
    pass

class WallTimeLimit(Exception):
    pass

class SchedulerError(Exception):
    pass

# Default observers

# Different approaches are possible:
# 1. use callable classes passing args to __init__ and period to add()
#    Exemple of client code:
#      sim.add(simulation.WriterThermo(), period=100)
#      sim.add(simulation.TargetRMSD(5.0))

# 2. use functions passing period and args as kwargs 
#    args are then passed to the function upon calling
#    In this case, we should differentiate types of callbacks via different add() methods
#    Exemple of client code:
#      sim.add(simulation.writer_thermo, period=100)
#      sim.add(simulation.target_rmsd, rmsd=5.0)

# At least for default observers, it should be possible to use shortcuts
#   sim.writer_thermo_period = 100
#   sim.target_rmsd = 5.0
# which will then add / modify the callbacks

# We identify callbacks by some types
# * target : these callbacks raise a SimualtionEnd when it's over
# * writer : these callbacks dump useful stuff to file
# and of course general purpose callback can be passed to do whatever

# It os the backend's responsibility to implement specific Writer observers.

class WriterThermo(object):
    def __call__(self, e):
        log.debug('thermo writer')

class WriterConfig(object):
    def __call__(self, e):
        log.debug('config writer')

class WriterCheckpoint(object):
    def __call__(self, e):
        log.debug('checkpoint writer')

class Target(object):

    def __init__(self, name, target):
        self.name = name
        self.target = target

    def __call__(self, sim):
        x = float(getattr(sim, self.name))
        logging.debug('targeting %s to %g [%d]' % (self.name, x, int(float(x) / self.target * 100)))
        if x >= self.target:
            raise SimulationEnd('target %s achieved' % self.name)

    def fraction(self, sim):
        """Fraction of target value already achieved"""
        return float(getattr(sim, self.name)) / self.target

class TargetSteps(Target):

    # Note: this class is there just as an insane proof of principle
    # Steps targeting can/should be implemented by checking a simple int variable
    def __init__(self, target):
        Target.__init__(self, 'steps', target)

class TargetRMSD(Target):

    def __init__(self, target):
        Target.__init__(self, 'rmsd', target)

TIME_START = time.time()

def _elapsed_time():
    return time.time() - TIME_START

class TargetWallTime(Target):

    def __init__(self, wall_time):
        self.wtime_limit = wall_time

    def __call__(self, sim):
        if _elapsed_time() > self.wtime_limit:
            raise WallTimeLimit('target wall time reached')
        else:
            t = _elapsed_time()
            dt = self.wtime_limit - t
            logging.debug('elapsed time %g, reamining time %g' % (t, dt))

class UserStop(object):
    """Allows a user to stop the simulation smoothly by touching a STOP
    file in the output root directory.
    Currently the file is not deleted to allow parallel jobs to all exit.
    """
    def __call__(self, e):
        # To make it work in parallel we should broadcast and then rm 
        # or subclass userstop in classes that use parallel execution
        log.debug('User Stop %s/STOP' % e.output_path)
        # TODO: support files as well
        if os.path.exists('%s/STOP' % e.output_path):
            raise SimulationEnd('user has stopped the simulation')

#TODO: period can be a function to allow non linear sampling
class Scheduler(object):

    """Scheduler to call observer during the simulation"""

    def __init__(self, period=None, calls=None, target=None):
        self._period = period
        self.calls = calls
        self.target = target

    @property
    def period(self):
        if not self._period:
            if self.target:
                if self.calls:
                    self._period = max(1, self.target / self.calls)
                else:
                    self._period = self.target
            else:
                raise SchedulerError('scheduler needs target to estimate period')

        return self._period

    def next(self, this):
        return (this / self.period + 1) * self.period

    def now(self, this):
        return this % self.period == 0


class Simulation(object):

    """Simulation abstract class using callback support."""

    # TODO: write initial configuration as well

    # Comvoluted trick to allow subclass to use custom observers for
    # target and writer without overriding setup(): have class
    # variables to point to the default observer classes that may be
    # switched to custom ones in subclasses
    _TARGET_STEPS = TargetSteps
    _TARGET_RMSD = TargetRMSD
    _WRITER_THERMO = WriterThermo
    _WRITER_CONFIG = WriterConfig    
    _WRITER_CHECKPOINT = WriterCheckpoint

    # Storage class attribute: backends can either dump to a directory
    # or following a file suffix logic. Meant to be subclassed.
    STORAGE = 'directory'

    def __init__(self, initial_state, output_path):
        """We expect input and output paths as input.
        Alternatively, input might be a system (or trajectory?) instance.
        """
        self._callback = []
        self._scheduler = []
        self.steps = 0
        self.target_steps = 0
        self.restart = False
        self.output_path = output_path # can be file or directory
        self.system = initial_state
        # Store a copy of the initial state to calculate RMSD
        self.initial_system = copy.deepcopy(self.system)

    @property
    def rmsd(self):
        # TODO: provide rmsd by species 07.12.2014
        return self.system.mean_square_displacement(self.initial_system)**0.5

    def add(self, callback, scheduler):
        """Add an observer (callback) to be called along a scheduler"""
        self._callback.append(callback)
        self._scheduler.append(scheduler)
        
    def report(self):
        for f, s in zip(self._callback, self._scheduler):
            logging.info('Observer %s: period=%s calls=%s target=%s' % (type(f), s.period, s.calls, s.target))

    def setup(self, 
              target_steps=None, target_rmsd=None,
              thermo_period=None, thermo_number=None, 
              config_period=None, config_number=None,
              checkpoint_period=None, checkpoint_number=None,
              reset=False):
        """Convenience function to set default observers"""

        #TODO: we should allow to modify just one parameter of callback without reset
        if reset:
            self._callback = []
            self._scheduler = []

        # Add check for user stop
        self.add(UserStop(), Scheduler(1))
        
        if target_steps:
            self.target_steps = target_steps
            self.add(self._TARGET_STEPS(target_steps), Scheduler())
        if target_rmsd:
            #self.target_steps = None
            # For the time being rmsd targeting is checked at every step
            # Of course, this could be relaxed with some more dynamic
            # scheduling
            self.add(self._TARGET_RMSD(target_rmsd), Scheduler(period=1))

        if thermo_period or thermo_number:
            self.add(self._WRITER_THERMO(), Scheduler(thermo_period, thermo_number))
        if config_period or config_number:
            self.add(self._WRITER_CONFIG(), Scheduler(config_period, config_number))
        # Checkpoint must be after other writers
        # TODO: implement sort callbacks to enforce checkpoint being last when not using setup()        
        if checkpoint_period or checkpoint_number:
            self.add(self._WRITER_CHECKPOINT(), Scheduler(checkpoint_period, checkpoint_number))

    def notify(self, condition=lambda x : True): #, callback, scheduler):
        for f, s in zip(self._callback, self._scheduler):
            try:
                # TODO: this check should be done internally by observer
                if s.now(self.steps) and condition(f):
                    f(self)
            except SchedulerError:
                logging.error('error with %s' % f, s.period, s.calls)
                raise
    
    def wall_time_per_step(self):
        """Return the wall time in seconds per step.
        Can be conventiently subclassed by more complex simulation classes."""
        return _elapsed_time() / self.steps

    # Our template consists of three steps: pre, until and end
    # Typically a backend will implement the until method.
    # It is recommended to *extend* (not override) the base run_pre() in subclasses
    # TODO: when should checkpoint be read? The logic must be set here
    # Having a read_checkpoint() stub method would be OK here.
    def run_pre(self):
        """This is safe to called by subclassing before or after reading checkpoint"""
        # Some schedulers need target steps to estimate the period
        for s in self._scheduler:
            # TODO: introduce dynamic scheduling for rmsd and similar
            if self.target_steps is None:
                s.target = 1000
            else:
                s.target = self.target_steps

        if self.target_steps is None:
            self.target_steps = sys.maxint
        
        self.report()
            
    def run_until(self, n):
        # Design: it is run_until responsability to set steps
        # bear it in mind when subclassing 
        # self.steps = n
        pass

    def run_end(self):
        pass

    def run(self, target_steps=None):
        if target_steps:
            self.target_steps = target_steps

        try:
            self.run_pre()
            # Before entering the simulation, check if we can quit right away
            # TODO: find a more elegant way to notify targeters only / order observers
            self.notify(lambda x : isinstance(x, Target))
            if not self.restart:
                self.notify(lambda x : not isinstance(x, Target))
            logging.info('simulation started at %d' % self.steps)
            logging.info('targeted number of steps: %s' % self.target_steps)

            while True:
#                if self.steps >= self.target_steps:
#                    raise SimulationEnd('target steps achieved')

                # Run simulation until any of the observers need to be called
                #next_step = min([self.target_steps]+[s.next(self.steps) for s in self._scheduler])
                next_step = min([s.next(self.steps) for s in self._scheduler])
                self.run_until(next_step)
                self.steps = next_step
                logging.debug('step=%d out of %d' % (self.steps, self.target_steps))
                # Notify writer and generic observers before targeters
                self.notify(lambda x : not isinstance(x, Target))
                self.notify(lambda x : isinstance(x, Target))

        except SimulationEnd as s:
            # Checkpoint is always called at the end 
            self.notify(lambda x : isinstance(x, WriterCheckpoint))
            logging.info('simulation wall time [s]: %.1f' % _elapsed_time())
            logging.info('simulation wall time/step [s]: %.2g' % self.wall_time_per_step())
            logging.info('simulation ended successfully: %s' % s.message)
            self.run_end()

        finally:
            logging.info('exiting')

