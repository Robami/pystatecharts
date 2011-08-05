#!/usr/bin/env python

from action import Action
from states import Statechart

class Event(object):
    def __init__(self, id, event_data = None):
        self.id = id
	self.event_data = event_data

    def __eq__(self, event):
        if event == None:
            return False                
           
        # rps 3/30/2011 Note: 
        # In the original code events were solely a number
        # Now events are id (that number) plus data 
        # Events remain solely a number in the
        # Transaction call event parameter, which eventually
        # ends up being compared here during statechart 
        # thread initialization
        #
        return self.id == event

    def __ne__(self, event):
        return not self.__eq__(event)

    def __str__(self):
        #return "Event:%s" % str(self.id)
        return self.id
        
    def event_data(self):
      return self.event_data

class Guard(object):
                 
    def check(self, runtime, param):
	  raise NotImplementedError
          
class CountingGuard(Guard):
    def __init__(self, threshold, retrigger_f):
      self.counter = 0
      self.threshold = threshold
      self.retrigger_f = retrigger_f
          
    def check(self, runtime, param):
       if ((self.counter == None) or self.threshold ==None):
          return False
       elif (self.counter < self.threshold):
          self.counter = self.counter + 1
          return False
       elif (self.retrigger_f):
          self.counter = 0
          return True
       else:
          self.counter = None   # never trigger again
          return True
         


