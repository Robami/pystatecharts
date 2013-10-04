# StatechartNoThread
# Purpose: decouples event generator from event server
#          listens to queue for events - not a thread - must be polled
#
# class StatechartNoThread
#  functions:
#     __init__
#     onepass
#     start
#     shutdown
#     log
#
import sys
from scbObjects import *             # converts event id to its name
from gevent import spawn, spawn_later, Timeout, Greenlet, monkey, sleep
from gevent.pool import Pool

monkey.patch_thread()

import traceback

def exceptionInfo(eobj):
  print "\nException in user code:"    
  print '-'*80
  traceback.print_exc(file=sys.stdout)  # print details of error
  print '-'*80
  print "*** Error:", eobj, " ***"
  print
#end exceptionInfo

class StatechartNoThread():          # abbreviated as scnt_
  #----------------------------------------------------------
  def __init__(self, sc_self):
        self.sc_self = sc_self   # statechart context
        self.dbg_self = None     # debug context added after instantiation
        self.running = False
  #----------------------------------------------------------
  def scnt_onepass(self,debug=False):
        sc_self = self.sc_self
        if self.running:           # acquire mutex to critical region
          event = None
          if not sc_self.lock.acquire(False):          
              return
          if len(sc_self.events):              # if event
              event = sc_self.events.pop(0)    # get event
          sc_self.lock.release()               # exit mutex
          if event:
              #
              #         printing events to terminal is useful for debugging
              #         but high-rate events become noise
              #         this code enables throttling of printing
              #         (the spe.count is defined in the design file -
              #          spe = Suppress Printing Event)
              print_f = True  
              if (self.sc_self.spe.count(event.id)>0):
                   print_f = False
              #
              # convert the event as integer into event as
              # enumerated type, class and element
              # (evo = EVent Object, defined in the design file)
              #
              m_f, evStr = EventObject.idToEvent(sc_self.evo,event)
              if m_f:
                info_text = "event dispatch: %s" % (evStr)
              else:
                info_text = "unrecognized event id: %d" % (event.id)
              self.log(info_text,print_f)
              try:
                 sc_self.statechart.dispatch(event)
              except Exception as eobj:
                 #
                 # exception may occur during event processing
                 # prevent exception from rippling through statechart
                 #
                 exceptionInfo(eobj)

              event = None
          # end if event
          else:              # no event - let me know its alive
            if (debug==True):
              print ".",
              sys.stdout.flush()
  # end scnt_onepass
  #----------------------------------------------------------
  def dbg_interface(self,dbg_self):
    self.dbg_self = dbg_self
  # end dbg_interface
  #----------------------------------------------------------
  def start(self,debug_f=False):
     self.sc_self.subscribe()           # ties comms Get 
     self.running = True
     while (self.running==True):
       self.scnt_onepass()
       sleep(0.1)
       if (self.dbg_self != None):
         status = self.dbg_self.user_onepass() # needed for script
         if (status <0):
           self.shutdown()
           break
       if (debug_f):
         print ".",
         sys.stdout.flush()         # debugging liveness
     #end while
  # end start
  #----------------------------------------------------------
  #
  def gevent_start(self):          # does not work any different than start

    pool = Pool(1)  
    result = pool.spawn(self.start)
    #pool.join()

  # end gevent_start
  #----------------------------------------------------------
  def shutdown(self):
      self.running = False
  # end shutdown
  #----------------------------------------------------------
  def log(self,datum, print_f):
        sc_self=self.sc_self
        if (sc_self.txtlog != None):
           sc_self.txtlog.info(datum)  # logger invocation has print flag
        else:
           if (print_f):   # support print suppression
             print datum
  # end log
  #----------------------------------------------------------
# end class StatechartNoThread
#------------------------------------------------------------

if __name__ == "__main__":

  print "StatechartNoThread syntaxed ok"
