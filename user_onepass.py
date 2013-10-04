"""
 user_hook - Why?
    Because gevents are incompatible with threads
    If you create a background gevent thread from a python command line
    there has to be a way to pass in command from the console to control what
    happens next. This class contains tools for that purpose.
    Tailored to work with scb (StateChart Builder) but outside of scb
    (uses names known to the scb class and scb related functions)

 classes:
   ExceptionString 		- returns exception string inside exception object
   user_hook            - gevent read from console as a class
   functions:
     __init__           - init
     process_line       - if command exceptions, modify context, try again
     user_loop          - used for testing
     user_onepass       - the expected name for console input

 functions:
    myreadline          - wrapper on gevent wait_read for console read
    readlineTMO         - read from console or timeout
    recover             - prints details of exception


 Usage:
    import user_onepass
    xx = <statechart instantiation>()
    uh = user_onepass.user_hook(" > ",xx)
    xx.thread.dbg_interface(uh)    # xx is the instantiation of a scb created program
    xx.thread.start()
    # you should now be able to pass in statchart commands via console
"""
import sys                            # sys library
import os                             # os library
import traceback                      # exception trace
from gevent.socket import wait_read   # gevent safe readline
from gevent import spawn, spawn_later, Timeout, Greenlet
#
# non-blocking io
#
import fcntl                      
fcntl.fcntl(sys.stdin, fcntl.F_SETFL, os.O_NONBLOCK) 
 
#
#-------------------------------------------------------------
#
class ExceptionString(Exception):

    def __str__(self):
        return repr(self.args[0])
    # end __str__
#end class ExceptionString 
#
#---------------------------------------------
#
# myreadline replaces readline or raw_input because these block
# and gevents cannot work through blocking system calls
#
def myreadline():
  wait_read(sys.stdin.fileno())  # gevent safe readline
  return sys.stdin.readline() 
# end myreadline
#
#-----------------------------------------------------------
#  
def readlineTMO(wait_sec):
        
  line = None
  timeout = Timeout(wait_sec)  # gevent timeout
  timeout.start()
            
  try: 
      line = myreadline()
  except Timeout,t:
      if (t is not timeout):
        raise
  finally:
    timeout.cancel()     # reset timeout
                       
  return line
           
# end readlineTMO

#---------------------------------------------
# recover
#         purpose: if the debugger raises an exception, 
#                  this routine is printed out afterwardss
#
def recover(eobj):
  print "\nException in user code:"    
  print '-'*80
  traceback.print_exc(file=sys.stdout)  # print details of error
  print '-'*80
  print "*** Error:", eobj, " ***"
  print
#end recover
#
#---------------------------------------------
#
class user_hook:

    def __init__(self,prompt,interface):
      self.PROMPT = prompt
      self.scobj = interface
      
    #
    #-------------------------------------------------------------
    # 
    #

    def process_line(self,line):
       
      #
      # process_line uses "self" and "self.interface" to enable shortcut commands
      # If the <context> of  <context>.command is missing,
      # this routine just might figure it out 
      #
      status = 0
      line = line.lstrip()         # strip leading whitespace
      params = line.split(" ")     # grab first word
      try:                             
        exec(line)                    # execute as python command
      except Exception as eobj:       # don't exit if command fails
        eobj_bis = ExceptionString(eobj)  # convert obj to string extractable
        emsg = eobj_bis.__str__()     # get the error string
        recover(eobj)        
        #
        # try again
        #
        print "Adding context and retrying..."
        line2 = "self." + line          # prefix is statechart builder handle 
        try:                             
          exec(line2)                     # execute as python command
        except Exception as eobj1:       # don't exit if command fails
          eobj_bis = ExceptionString(eobj1)  # convert obj to string extractable
          emsg = eobj_bis.__str__()      # get the error string
          #
          # try again
          #
          line3 = "self.scobj." + line       # prefix is statechart handle
          try:                             
            exec(line3)                    # execute as python command
          except Exception as eobj2:       # don't exit if command fails
            eobj_bis = ExceptionString(eobj2)  # convert obj to string extractable
            emsg = eobj_bis.__str__()      # get the error string
            print "Cannot recover"
          else:
            print "Success"
        else:
          print "Success"

      sys.stdout.flush()           # cleanup flush
      return status
    # end process_line
    #
    #-------------------------------------------------------------
    # 
    def user_loop(self):
         
      while 1:                   # loop forever, or until quit()
        print self.PROMPT,            # print prompt
        sys.stdout.flush()       # flush
        line = myreadline()      # "special" readline works with gevents 
        
        self.process_line(line)       # 'exec' the line
        
      # end while
    #end user_loop
    #
    #-----------------------------------------------------------
    #
    def user_onepass(self):
      status = 0
      data_f = False
      line = ""
      #
      # no initial prompt, enter empty line to refresh menu
      # 
      sobj = spawn(readlineTMO,0.1)
      sobj.join()
      #
      # the call below does not catch the fatal error
      #
      if (sobj.exception):
         pass
      else:
        line = sobj.value
        if (line!=None):
          status = self.process_line(line)
          if (status>=0):
            print self.PROMPT,
            sys.stdout.flush()
      return status
    #end user_onepass
    #
    #-----------------------------------------------------------
    #

if __name__ == "__main__":

  hook = user_hook(" > ")
  hook.user_loop()

  #while True:            # testing gevents
  #  self.user_onepass()  
