"""Nonblocking Egg scan schedule, using the server's cycle clock."""
import math


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


class CycleSchedule:
    def __init__(self,options,interval=None):
        self.options=options
        self.interval=interval
        self.phase='requesting'
        self.role='report'
        self.at=self.reset_at=None

    def request(self,role):
        self.phase='requesting'
        self.role=role
        self.at=self.reset_at=None

    def after_report(self,cycle,now,clock):
        self.at=self.reset_at=None
        if self.interval is not None:
            self.phase='interval'
            self.at=now+self.interval
            return
        if not cycle.get('running',True):
            self.phase='paused'
            return
        if cycle.get('in_night'):
            night=cycle.get('night_seconds')
            if not number(night) or not 0<=night<=310:
                night=self.options['night_fallback']
            self.phase='night'
            self.at=now+night+self.options['reset_grace']
            return
        self.phase='reset'
        remaining=cycle.get('seconds_until_reset')
        sane=number(remaining) and 0<=remaining<=310
        target=cycle.get('reset_at')
        if sane and number(target) and number(clock) and 0<=target-clock<=310:
            self.reset_at=target
        else:
            delay=remaining if sane else self.options['cycle_fallback']
            self.at=now+max(1,delay)

    def after_cycle(self,cycle,now):
        night=cycle.get('night_seconds')
        if not number(night) or not 0<=night<=310:
            night=self.options['night_fallback']
        self.phase='night'
        self.at=now+max(night,self.options['night_fallback'])+self.options['reset_grace']
        self.reset_at=None

    def retry(self,now):
        self.phase='retry'
        self.at=now+30

    def due(self,now,clock,cycle):
        if self.phase in ('reset','paused') and not cycle.get('running',True):
            self.phase='paused'
            return None
        if self.phase=='paused':
            self.after_report(cycle,now,clock)
            return None
        if self.phase=='reset':
            if self.reset_at is not None:
                return 'cycle' if number(clock) and clock>=self.reset_at else None
            return 'cycle' if self.at is not None and now>=self.at else None
        if self.phase in ('night','interval'):
            return 'report' if now>=self.at else None
        if self.phase=='retry':
            return self.role if now>=self.at else None
        return None

    def status(self,now):
        return dict(phase=self.phase,reset_at=self.reset_at,
            wait_seconds=max(0,self.at-now) if self.at is not None else None,
            reset_grace=self.options['reset_grace'])
