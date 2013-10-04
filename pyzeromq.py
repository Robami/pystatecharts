#! /usr/local/bin/python
#
#
# pyzeromq.py
#
import sys    			# input/output
import string 			# atoi
import time   			# sleep, time
import os     			# pid
import fcntl                    # for gevent safe readline

#import zmq
from gevent import spawn, spawn_later, Timeout, Greenlet, sleep, monkey
from gevent_zeromq import zmq
from gevent.socket import wait_read
from gevent.pool import Pool

from KThread import *  		# killable thread

monkey.patch_all()

#------------------------------------------------------
#
#
#
# classes/functions:
#  class ExceptionString
#  class ThreadedGetThread   - threaded get inside a class
#     __init__               - takes parameters
#     run                    - call .start(), not run
#     shutdown               - "killable" thread
#
#  class CommObject
#   preSend                  - gets socket and calls bind
#   __init__
#   Put                      - put to socket
#   Get_onepass              - get inside a timed greenlet
#   Get                      - nonthreaded get from socket (timed looping timed blocking)
#   ThreadedGet              - threaded get entry point
#   GeventGet                - threaded get, nonblocking on recv ("join" not called)
#   TerminateGet             - terminates get (if get is also polling console)
#   Subscribe                - subscribe tag is part of message
#   Unsubscribe              - removes tag from subscribe list
#   Close                    - closes socket
#   Dbg_if                   - attaches callback for Get polling console 
#   Sc_if                    - attaches callback for Get polling statechart 
#
# functions outside of classes
#   myreadline               - console read in a timed greenlet
#   myreadline2              - loop of myreadline
#
# class zmq_menu             - tailored generic menu for debu
#       __init__
#       print_menu           - the menu
#       process_line         - processes console input
#       loop_menu            - loops on console
#       user_onepass         - console in a greenlet
#
#-----------------------------------------------------------

PROMPT = " > "

#----------------------------------------------
#
# exceptions are objects, python 2 has the .message operation
# which is deprecated in python 3 
# the key is knowing that the exception message is the first param in the
# exception
#
#----------------------------------------------
class ExceptionString(Exception):
    def __str__(self):
        return repr(self.args[0])
# end ExceptionString
#-----------------------------------------------------------------
#
class ThreadedGetThread(KThread):

  def __init__(self,interface,    # the socket
               wait_sec=60,       # timeout
               callback=None,     # place one [callback] in list 
               debug_f=False):    # if true then echo incoming   

    KThread.__init__(self)      
    self.interface = interface   # the statechart
    self.wait_sec = wait_sec     # used for debugging
    self.callback = callback     # statechart msg to event conversion
    self.running   = False       # thread loop control
    self.forever_f = True
    if (wait_sec > 0):
     self.forever_f = False
     print "wait=",wait_sec
    self.suppress_f = True
    if debug_f:
      self.suppress_f = False   # don't suppress echo
     
  # end __init__
  #-----------------------------------------------------------------
  def run(self):                      # call .start() NOT .run()           
    interface = self.interface
    startTime = time.time()
    self.running = True
    while (self.running) and (interface.get_enable):
      retval = 0
      msg = None  
      
      if (interface.sock_code == zmq.SUB):          
         msg = interface.socket.recv()
      else:
        msg = interface.socket.recv_pyobj() # blocking call
    
 
      # complete handshake
      if (interface.sock_code==zmq.REP):
          interface.socket.send(".")     # mandatory handshake    

      if (msg!=None):              
       quit_f = interface.processMsg(msg,self.callback,0,self.suppress_f)
       if (quit_f):
         self.running = False

      if (not self.forever_f):
        nowTime = time.time()
        if (nowTime > startTime + self.wait_sec):
          print "timeout: Get"
          self.running = False
    # end while running
       
  #end run
  #-----------------------------------------------------------------                                                                                           
  def shutdown(self):       
      self.running = False 
      self.kill() 
  #end shutdown
      
#end class ThreadedGetThread 
 
#-----------------------------------------------------------

class CommObject():

  @staticmethod
  def inputSocketTypes():
   return ["reply","pull","subscribe"]

  @staticmethod
  def outputSocketTypes():
   return ["request","push","publish"]

    
  def _SockType2Code(self,sock_type): # private 
    match_f = False
    sock_code = None
    valid = [["request",zmq.REQ],
             ["reply",zmq.REP],
             ["push",zmq.PUSH],
             ["pull",zmq.PULL],
             ["publish",zmq.PUB],
             ["subscribe",zmq.SUB]]
    ii = 0
    while (ii<len(valid)):
      if (sock_type==valid[ii][0]):
        sock_code = valid[ii][1]
        match_f = True
        break
      ii = ii +1
    return match_f, sock_code
  # end _SockType2Code
  #-----------------------------------------------------------
  def preSend(self): 
    err_f = False

    self.getSocket()     
    try:
      self.socket.bind(self.sockname)
    except Exception as eobj:
      eobjstr = ExceptionString(eobj)  # drat! still an object
      estr = str(eobjstr)              # now its a string
      print "Exception on socket bind:", self.sockname+",",estr
      if (estr.find("Address already in use") != -1):     # zombie socket?
        print "Attempting close"
        self.socket.close()                               # close socket
        print "Attempting reconnect"                      # belts and suspenders
        sleep(0.1)                  			  # socket might hang around after close
        self.socket = self.context.socket(self.sock_code) # reaquire (don't know side-effects of close)
        try:                            		  # try again
          self.socket.bind(self.sockname)
        except Exception as eobj:
          print "Exception on binding:",sockname,eobj
          print "Another process was here first"
          err_f = True
      else:
        print "Excepting during socket binding:",self.sockname+",",estr
    else:
       self.error= False   # clear old errors

    return err_f
  # end preSend
  #-----------------------------------------------------------
  def getSocket(self):
    self.socket = self.context.socket(self.sock_code)    
    self.socket.setsockopt(zmq.LINGER, 0)
  # end getSocket 
  #-----------------------------------------------------------
  #
  def __init__(self, host='127.0.0.1', port=5000, sock_type=None, rpc_f=False): 

    self.host = host            # tcp/ip  host
    self.port = str(port)       # tcp/ip port
    self.rpc_f = rpc_f          # if true then close socket after Put
    self.error = False
    self.dbg_if = None          # debugger callback context
    self.subscribe = []         # subscription tags
    self.context = None         # zmq context
    self.socket = None          # zmq socket
    self.sock_code = None       # zmq socket type
    self.sc_if = None           # statechart callback context
    self.get_enable = True      # gate on Get()
    self.thread = None          # listen thread
    

    self.context = zmq.Context()   # context is key 

    match_f, self.sock_code = self._SockType2Code(sock_type)
    if (not match_f):
      print "unknown socket type:", sock_type
      self.error = True
      return
 
    self.sockname = "tcp://" + self.host + ":" + self.port 
    if ((self.sock_code == zmq.REQ) or 
        (self.sock_code == zmq.SUB) or
        (self.sock_code == zmq.PULL)): 
      self.getSocket()                         
      try:
        self.socket.connect(self.sockname)
      except Exception as eobj:
        print "socket.connect", eobj
        self.error = True  
    elif ((self.sock_code == zmq.REP) or 
          (self.sock_code == zmq.PUB) or
          (self.sock_code == zmq.PUSH)):
      #
      # bind doesn't like localhost
      # convert to 127.0.0.1
      #
      if (self.host == 'localhost'):
        self.sockname = "tcp://127.0.0.1" + ":" + self.port
      
      if not self.rpc_f:
        self.preSend()   
      #
      # History: Original design was to leave socket open for sending for
      #          duration of program. That was ok until RPC's were added
      #          where the RPC client is on the same host as the RPC driver
      #          (why do this? decoupling for updating w/o shutting down.
      #           Not sure the side-effects were well thought out)
      #
      #          Current design is to bind, send, and close for each call to Put()
      #          The concern is, close too soon and the message doesn't go out
      
    else:
      print "coding error - unrecognized socket type"
      self.error = True
      
  # end __init__
  #-----------------------------------------------------------
  def Dbg_if(self,interface):
    self.dbg_if = interface    # debug interface - permits a Send inside blocking Get

  #end Dbg_if
  #-----------------------------------------------------------
  def Sc_if(self,interface):
    self.sc_if = interface     # statechart interface - permits state advance in blocking Get
  #end Sc_if   
  #-----------------------------------------------------------     
  def Put(self,msg_out,        # the data to send
          exchange=None,       # holdover from rabbitmq
          routing_key=None):   # holdover from rabbitmq
    
    #base_time = time.time()   # for instrumenting "spawn"

    #
    # spawn is gevent 
    # .join() forces wait to completion
    #
    # Note: send_pyobj does json underneath
    # can't jason a PUB because first word is the routing_key
    # (the key is not separate from the message)
    # 
    # Fix? - Not necessary - at a higher level, the statechart event object is 
    # converted within the statechart 
    #
    if self.rpc_f:
      self.preSend()                    # preSend() before Put(), socket.close() after
    if (self.sock_code == zmq.PUB):
      self.socket.send(msg_out)
    else:
      spawn(self.socket.send_pyobj, msg_out)          # it works without .join()!
    
    #print "sec:", time.time() - base_time
    if (self.sock_code==zmq.REQ):
      msg = self.socket.recv()    # mandatory handshake 

    if self.rpc_f:
      sleep(0.8)                    # delay is a hack for send to complete
      self.socket.close()           # allow another thread to bind and use same socket
  # end Put
  #-----------------------------------------------------------
  #  
  def Get_onepass(self, wait_sec=0.1):
    
    retval = 0
    msg = None
    timeout = Timeout(wait_sec)  # gevent timeout
    timeout.start()
        
    try: 
        if (self.sock_code == zmq.SUB):          
           msg = self.socket.recv()
        else:
          msg = self.socket.recv_pyobj() # blocking call
    except Timeout,t:
        if (t is not timeout):
          raise
        else:
          retval = -1    # timeout
    finally:
      timeout.cancel()     # reset timeout
 
    if (retval != -1):   # if not timeout then complete handshake
      if (self.sock_code==zmq.REP):
        try:
          #self.socket.send(".")     # mandatory handshake
          spawn(self.socket.send_pyobj,".").join() 
        except Exception as eobj:   # fatal error
          print eobj
          print "Something is very wrong" 
          sys.exit()  # quit() doesn't work here                  
    return msg
       
  # end Get_onepass
  #
  #--------------------------------------------------------------
  # 
  def processMsg(self,msg,         # message to process
                 callback=None,    # array handlers for message
                 jj=0,             # index into callback array of procs
                 suppress_f=True): # suppress print for debug          
    quit_f = False
    if (msg != None):             # process message
       if (not suppress_f):
         print "received:", msg
       base_time = time.time()    # reset timer
       if (callback != None):
         if type(callback[jj]) is str:  # used to test this call
           try:
             exec(callback[jj])
           except Exception as eobj:
              print "Get callback eval exception:", eobj
         else:
           try:
             callback[jj](msg)              # ties "Get" to statechart 
           except Exception as eobj:
              print "Get callback exception:"
              raise                         # re-raise to print context 
       else:
         if (self.sock_code == zmq.SUB): # subscribe needs special  handling
           params = msg.split(" ")
           ii = 0
           while (ii < len(params)):
             params[ii] = params[ii].lstrip(" ")  # remove space from left
             params[ii] = params[ii].rstrip(" ")  # remove space from right
             ii = ii + 1
           if (params[1]=='quit'): # if subscribed, 'quit' in 2nd field
             quit_f = True
         else:
           if (msg=='quit'):
             quit_f = True        
    # endif message present
    return quit_f
  # end processMsg
  #
  #--------------------------------------------------------------
  #  
  def Get(self,wait_sec=60,   # timeout on wait
          nblist=None,        # nonblocking list of get calls (console hook)
          callback=None,      # message handler
          idle_f=False,       # when set and idling, sends chars to console
          debug_f=False):     # if true then echo incoming    
     #
     # subscribing to nothing is not the same as
     # subscribing to an empty string "" means subscribed to all
     #
     
     suppress_f = not debug_f          # if debug then don't suppress echo
     if (self.sock_code == zmq.SUB):
       print "subscribed to:", self.subscribe
       if (len(self.subscribe)==0):     # subscribed to nothing? nothing to get 
         return

     if (nblist==None):
       nblist = [self.Get_onepass]  # default

     forever_f = True
     if (wait_sec > 0):
       forever_f = False
       print "wait=",wait_sec
       base_time = time.time()
     #
     # there are two "get" methods with timeouts
     # the outer has a long (or no) timeout that loops
     # calling the inner with a short gevent timeout
     # The outer can poll a background task while processing the inner.
     # There are three possible background tasks: 
     #   1. the debug interface that allows testing this code
     #   2. the statechart interface that advances the states
     #   3. the callback interface - used for statechart message-to-event conversions
     #
     sobj = []
     jj = 0
     self.get_enable = True
     load_f = True
     quit_f = False
     while (self.get_enable):
       msg = None
       #
       # need to fill array until max, then overwrite element
       #
       if (load_f):
         sobj += [spawn(nblist[jj])]  # fill
       else:
         sobj[jj] = spawn(nblist[jj])  # overwrite
       sobj[jj].join()
       if (sobj[jj].exception):        # fatal
         print "Get() exception:",jj,nblist
         break
       msg = sobj[jj].value
       quit_f = self.processMsg(msg,callback,jj,suppress_f)
       if (quit_f):
         break
       
       # Still  here?
       # 1. check polled interfaces
       # 2. check timeout
       #
       if (self.sc_if !=None):
          self.sc_if.scnt_onepass()  # StateChart No Thread
          if (idle_f==True):             # signals its alive
            print "-",
            sys.stdout.flush()

       if (self.dbg_if !=None):      # statechart builder user interface
         retval = self.dbg_if.user_onepass()
         if (retval<0):
           print "user quit"
           break          

       if (not forever_f):
         if (base_time + wait_sec < time.time()):
           print "timeout: Get"
           break

       jj = (jj+1)%len(nblist)  # point to next in non-blocking list
       if (jj==0):              # done building array
         load_f = False 
     #end while
     print "exiting Get"
  # end Get
  #
  #----------------------------------------------------------- 
  # 
  def ThreadedGet(self,wait_sec=60,    # timeout
                       callback=None,  # add [callback] to list
                       debug_f=False): # if true, then echo incoming

    #
    # subscribing to nothing is not the same as
    # subscribing to an empty string "" means subscribed to all
    #
    if (self.sock_code == zmq.SUB):
      print "subscribed to:", self.subscribe
      if (len(self.subscribe)==0):     # subscribed to nothing? nothing to get 
        return
    
    self.thread = ThreadedGetThread(self,wait_sec,callback,debug_f)
    self.thread.start() 

  # end ThreadedGet
  #----------------------------------------------------------- 
  # 
  # This routine has the unwanted side effect of doubling what it hears!
  # Use ThreadedGetThread instead
  #
  def GeventGet(self,wait_sec=60,    # if 0 then forever
                     callback=None,
                     debug_f=False): # one [callback] in list 

    #
    # subscribing to nothing is not the same as
    # subscribing to an empty string "" means subscribed to all
    #
    if (self.sock_code == zmq.SUB):
      print "subscribed to:", self.subscribe
      if (len(self.subscribe)==0):     # subscribed to nothing? nothing to get 
        return

    pool = Pool(1)
  
    result = pool.spawn(self.Get,        # parameters follow:
                        wait_sec,   # timout
                        None,       # list of nonblocking calls (console hook)
                        callback,   # callback for message
                        False,      # send '.' while waiting (testing liveness)
                        debug_f) # echo output
    #
    # What makes this powerful is without the join()
    # the call to GeventGet immediately returns!
    #
    #pool.join() 

  # end GeventGet
  #
  #----------------------------------------------------------- 
  # 
  def TerminateGet(self):
    self.get_enable = False
    if (self.thread != None):
      self.thread.kill()
      self.thread = None
  # end TerminateGet
  #
  #----------------------------------------------------------- 
  #    
  def Subscribe(self,what):
  
     # what is a subscribe tag of type string
     # if publish/subscribe, the subscribe "tag" is the first word
     #  in the publish message
     #
     print "subscribing to:",what
     if what[0]!='[':                   # subscribe single tag
       self.socket.setsockopt(zmq.SUBSCRIBE,what)
       self.subscribe = self.subscribe + [what]
     else:
       try:                                # eval can always go wrong
         what_list = eval(what)            # convert string to list 
       except Exception as eobj:
         print "Subscribe: Exception",eobj # error, but don't die
       else:
         ii = 0
         while ii < len(what_list):       # subscribe to a list of tags
           self.socket.setsockopt(zmq.SUBSCRIBE,what_list[ii])
           self.subscribe = self.subscribe + [what_list[ii]]
           ii = ii + 1              
     
  # end Subscribe
  #----------------------------------------------------------- 
  #
  def Unsubscribe(self): 
     self.socket.setsockopt(zmq.UNSUBSCRIBE)
     self.subscribe=[]   
  # end Unsubscribe
  #----------------------------------------------------------- 
  #   
  def Close(self):
    self.socket.close()  # close socket 
    self.context.term()  # close context - prevents socket from reuse
  # end Close
  #----------------------------------------------------------- 
  #

# end CommObj 
#-----------------------------------------------------------  
#
def myreadline():
  wait_read(sys.stdin.fileno())  # gevent safe readline
  return sys.stdin.readline()

#-----------------------------------------------------------  
def myreadline2(wait_sec):
    
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
       
# end myreadline2
#----------------------------------------------------------
#----------------------------------------------------------

class zmq_menu():

  def __init__(self):
  
    self.msg_cnt =0     # used for testing Put
    self.comm = None    # the comm object
    
  # end __init__

#-------------------------------

  def print_menu(self):
    print 
    print "*** welcome to the menu ***"
    print "\t1: Cfg,request|reply|push|pull|publish|subscribe[,tag]"
    print "\t2: Send [,<string>]"
    print "\t3: Get,[,<callback>] # send quit to break loop"
    print "\t4: Gevent Get" 
    print "\t5: Close"
    print "\t6: Subscribe"
    print "\t7: Unsubscribe"
    print "\t8: Threaded Get"
    print "\t99: exit"
  #end print_menu
  
  #------------------------------

  def process_line(self,line_in):

    status = 0

    line = line_in
    if ((len(line)==0) or (line=='\n')): # skip empty lines
      print "<no value entered>" 
      sys.stdout.flush()
      return status

    if (len(line_in)>1):
      if (line_in[len(line_in)-1]=='\n'):
        line = line_in[0:len(line_in)-1] 
 
    params = line.split(",")
    ii = 0
    while (ii < len(params)):
      params[ii] = params[ii].lstrip(" ")  # remove space from left
      params[ii] = params[ii].rstrip(" ")  # remove space from right
      ii = ii + 1
         
    try:  
      ival = string.atoi(params[0])  
    except ValueError, emsg:
       print "ValueError: ", emsg
       ival = 0

    #print "the value selected is " + str(ival)

    if ival == 1:
      if (len(params)<2):
        print "socket type missing: request, reply"
      else:
        self.comm = CommObject(sock_type=params[1]) 
        if ((self.comm.error!= True) and 
            (params[1] == "subscribe") and
            (len(params)>2)):
          ii = 0
          while (ii < len(params)-2):
             self.comm.Subscribe(params[ii+2])
             ii = ii + 1  
        self.comm.Dbg_if(self)  # add context for callback        

    elif ival == 2:
      if (len(params)>1):
        msg_string = params[1]
      else:
        msg_string ='%d: hello world!' % self.msg_cnt
        self.msg_cnt = self.msg_cnt + 1  
      print "sending:", msg_string
      try: 
        self.comm.Put(msg_string)
      except Exception as eobj:
        print eobj 

    elif ival == 3:
      wait = 60
      cb = None
      if (len(params)>1):
        cb = []
        cb += [params[1]]
        print "callback=",cb
      try:  
        self.comm.Get(wait_sec=wait,callback=cb,idle_f=False,debug_f=True)
      except Exception as eobj:
        print "Get:",eobj
 
    elif ival == 4:
      self.comm.GeventGet(wait_sec=60,callback=None,debug_f=True)
      
    elif ival == 5:
      try:
        self.comm.Close()   
      except Exception as eobj:
        print eobj
    elif ival == 6:   # subscribe 
      subval = "mytag"
      if (len(params)>1):
          subval = params[1]
      try:
        self.comm.Subscribe(subval)
      except Exception as eobj:
        print eobj
    elif (ival == 7):  # unsubscribe
      try:
        self.comm.Unsubscribe()
      except Exception as eobj:
        print eobj

    elif (ival == 8):  # threaded get
      try:
        self.comm.ThreadedGet(debug_f=True)
      except Exception as eobj:
        print eobj
    
    elif ival == 99:
      print "exiting menu"
      if self.comm != None:
        try:
          self.comm.Close()
        except Exception as eobj:
          print eobj
      status = -1  # cleaner than quit()
    else:
      print "invalid entry"

    return status
  
  #end process_line

  #------------------------------

  def loop_menu(self): 
    
    self.print_menu()
    print PROMPT,
    sys.stdout.flush()
    while True:
      
      line = myreadline()  # outside of this class        
      if (self.process_line(line)<0):
          break
      else:
          self.print_menu()
          print PROMPT,
          sys.stdout.flush()
    #end while
  #end loop_menu
  #------------------------------

  def user_onepass(self):
    status = 0
    data_f = False
    line = ""
    #
    # no initial prompt, enter empty line to refresh menu
    # 
    sobj = spawn(myreadline2,0.1)
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
          self.print_menu()
          print PROMPT,
    return status
  #end user_onepass
# end zmq_menu

#-------------------------------

#   *** main ***

if __name__ == "__main__":

  fcntl.fcntl(sys.stdin, fcntl.F_SETFL, os.O_NONBLOCK) 
  zz = zmq_menu()
  zz.loop_menu()
  
  #while True:
  #  zz.user_onepass()

  print "menu ran"
  
