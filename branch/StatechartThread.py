# StatechartThread
#                purpose: decouples event generator from event server
#                         listens to queue for events
#
#
from KThread import *                # killable threads
from scbObjects import *             # converts event id to its name
import EventLogger as EL             # bespoke instead of python logger
class StatechartThread(KThread):
    def __init__(self, interface):
        KThread.__init__(self)       # thread init
        self.interface = interface   # link to statechart 
        self.running = False
    def run(self):
        interface = self.interface
        self.running = True
        try:
          while self.running:         # acquire mutex to critical region
            event = None
            while (not interface.lock.acquire(False) and self.running):
              pass
            if (not self.running):    # someone somewhere sent a shutdown
              break
            if len(interface.events):              # if event
                event = interface.events.pop(0)    # get event
            interface.lock.release()               # exit mutex
            if event:
              #
              #         printing events is useful for debugging
              #         but high-rate events become noise
              #         this code enables throttling of printing
              #         (the spe.count is defined in the design file -
              #          spe = Suppress Printing Event)
              print_f = True       
              if (self.interface.spe.count(event.id)>0):
                   print_f = False
              #
              # convert the event as integer into event as
              # enumerated type, class and element
              # (evo = EVent Object, defined in the design file)
              #
              m_f, evStr = EventObject.idToEvent(interface.evo,event)
              if m_f:
                info_text = "event dispatch: %s" % (evStr)
              else:
                info_text = "unrecognized event id: %d" % (event.id)
              self.log(info_text,print_f)
              interface.statechart.dispatch(event)
              event = None
        finally:
          print "Statechart thread stopped"
    def shutdown(self):
        self.running = False
        self.kill()                  # kill defined in KThread
    def log(self,datum, print_f):
        interface=self.interface
        if (interface.txtlog != None):
           interface.txtlog.put(EL.LogStatusEvent(datum,print_f))
        else:
           print datum
