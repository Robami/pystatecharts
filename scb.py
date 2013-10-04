#! /usr/local/bin/python
#
"""
  statechartbuilder (scb)
 
  robert schaefer
  mit haystack observatory
  11/5/2010

  Design:
  
     This program takes an ini file that contains
     options, states, events and transitions and builds a 
     Harel statechart of concurrent and hierarchical states
     as an executable python program.
    
  ---------------------------------------------
  functions:
    myreadline            - gevent non-blocking readline
    readlineTMO           - gevent readline with gevent timeout
    enlist_string         - converst string to list of words
    isKnownToPython       - used to suppress warnings 
    exceptionInfo         - print info from exception on interpreter command line
    sc_help               - prints useful functions
    startsc               - invokes statechart, generates handle

  class scb functions:
    isStateValid          - test state presence 
    parent_state          - parent state of state
    getIniKeySet          - bundles repetitions of calls
    unique_events         - tests events to make sure values are unique
    verify_xition_state   - tests transition names match state names
    verify_xition_start   - all hierarchial states and below must be started
    valid_event           - check event against event list
    get_parents           - creates list of states ordered by parent
    common_hierarchy      - finds common hierarch state
    xition_check          - check for faults in xitions
    getIniPortZmq         - ini parameters for zeromq
    getIniPortRmq         - ini parameters for rabbitmq
    verify_ports          - verifies ports parameters
    get_ini_params        - get ini parameters
    isParamKeyword        - expands shortcut
    proc_func_list        - converts a list to a statechart function call
    proc_func_stub        - converts a stub to a statechart function call
    installProxy          - installs proxy call instead of inline callback
    gen_code_hooks        - common subroutine to generate code hooks
    commsCallbacksRmq     - rabbitmq communciation callbacks 
    commsCallbacksZmq     - zeromq communciation callbacks 
    listEvents            - lists events as strings
    listStates            - lists states as strings, identifies active states
    isStateActive         - test for active state
    listTransitions       - lists transitions  
    commsParamsRmq        - copy rabbitmq params into generated python file
    commsParamsZmq        - copy zeromq params into generated python file
    user_onepass          - commandline aquisition and processing, once
    process_line          - command line processing
    user_loop             - commandline acquistion and processing in loop
    process_files         - process ini file, produce py file
  

  generated class functions:
    sendEvent           - send event to statechart
    shutdown            - shutdown statechart
    sendEventAsMsg      - xlate event to message, send message to rabbitmq queue
    getMsgSendEvent     - (debug), reads messages in queue, converts to statechart event
  
"""
  
#---------------------------- imports ----------------------------------------------

import sys
import os
ARGPARSE = True
try:
  import argparse       # argparse needs python 2.7, transitioning from optparse
except Exception as eobj:
  print eobj
  print "Please update your python version to 2.7+. Importing optparse" 
  ARGPARSE = False
  import optparse                 # parses command line options

import ConfigParser               # parses ini file
import re                         # parsing tools
import traceback                  # exception trace
import datetime                   # time
import scbObjects as SCBO
import scbUtilities as SCBU      

sys.path.append(os.getcwd())      # needed when scb.py is a logical link

# use of gevents precludes use of threads
# gevents require sys-calls to not block
#
from gevent.socket import wait_read   # gevent safe readline
from gevent import spawn, spawn_later, Timeout, Greenlet

# non-blocking io
#
import fcntl                      
fcntl.fcntl(sys.stdin, fcntl.F_SETFL, os.O_NONBLOCK) 
#
# Transitioning from optparse to argparse
# Note: -h help is built-in for both
# Note: argparse requires python 2.7+ 
#
if ARGPARSE:
    parser = argparse.ArgumentParser()
    parser.add_argument('-d','--design',    help='-d <design_file>:')
    parser.add_argument('-o','--output',    help='-o <output_file>')
    parser.add_argument('-m','--mqtype',    help='-m rmq: message queue override, default is zeromq')
    parser.add_argument('-c','--callbacks', help='-c <callbacks_file>')
    #
    # initialize object with instantiation parameters
    #
    args = parser.parse_args()        # get params
    g_des_file = None
    if args.design != None:
       g_des_file = args.design
    g_out_file = None
    if args.output != None:
       g_out_file = args.output
    g_mq_type = "zeromq"
    if args.mqtype != None:
      g_mq_type = args.mqtype
    g_cb_file = None
    if args.callbacks!=None:
      g_cb_file = args.callbacks
     
else:    
  opin = optparse.OptionParser()
  opin.add_option("-d", action="store", type="string", dest="des_file",help="design file")
  opin.add_option("-o", action="store", type="string", dest="out_file",help="python output file")
  opin.add_option("-m", action="store", type="string", dest="mq_type",help="zmq default, or rmq")
  opin.add_option("-c", action="store", type="string", dest="cb_file",help="callbacks file")
  opin.set_defaults(des_file="", out_file="",mq_type="zeromq",cb_file=None)
  opt, args = opin.parse_args()
  
  g_des_file = opt.des_file
  g_out_file = opt.out_file
  g_mq_type  = opt.mq_type
  g_cb_file = opt.cb_file

RMQ = False             # Rabbitmq
ZMQ = True              # Zeromq is default
if (g_mq_type =="rmq"): # override default
   RMQ = True
   ZMQ = False
                    
if (RMQ):
  import scbPortObjects as SCBPR
else:
  import scbPortObjectsZmq as SCBPZ      # port objects
  from pyzeromq import CommObject as cmo # comm object

#
#---------------------------------------------
# sc_help
#    purpose: debugger help
#
def sc_help(objname="my_sc"):
  print
  print " ---------- statechart python debugger------------"
  print 
  print " useful functions:  "
  print 
  print "\tstartsc(%s) # instantiates statechart"%objname   
  print "\t%s.listStates(<active> =None, True, False)"%objname
  print "\tprint %s.isStateActive(\"<handle>\",\"<state>\")"%objname
  print "\t%s.listTransitions(\"<state>\")"%objname
  print "\t%s.listEvents()"%objname
  print "\t%s.scobj.sendEvent(<event>, [<event_data>])"%objname
  print "\t%s.scobj.shutdown()"%objname
  print "\tsc_help()"
  print ""
#end sc_help
#
#---------------------------------------------
#
# myreadline replaces readline or raw_input because these block
# and gevents cannot work through blocking system calls
#
# quit_f used because myreadline is placed in loop for scb interpreter
# user_loop() and a quit() in one part of program doesn't propagate through
#
def myreadline():
  quit_f = False
  line = ""
  try:
    wait_read(sys.stdin.fileno())       # gevent safe readline of stdin
  except Exception as eobj:
    emsg = str(ExceptionString(eobj))
    if (emsg.find('I/O operation on closed file')>=0):  # quit() call detected
      print "quit() detected"
      quit_f = True
  else:
    line = sys.stdin.readline()
  return quit_f,line  
# end myreadline
#
#-----------------------------------------------------------
#  
def readlineTMO(wait_sec):
        
  line = None
  quit_f = False
  timeout = Timeout(wait_sec)  # gevent timeout
  timeout.start()
            
  try: 
      quit_f,line = myreadline()
  except Timeout,t:
      if (t is not timeout):
        if (not quit_f): # because raise is inside spawn in user_onepass(),    
          raise  # this exception will loop   
  finally:
    timeout.cancel()     # reset timeout
  #
  # must return two parameters as one because readlineTMO()  
  # is used in gevent timeout call and only 1 param can come back
  # - used in user_onepass, which is passed into pyzeromq
  #
  return (quit_f,line)  
           
# end readlineTMO
#
#---------------------------------------------
# enlist_string
#              purpose: turn ini value into a list
# 
def enlist_string(entry,      # string as list
                  rmspace_f): # remove spaces
  #
  # Note: the list in the ini design file is a string mimicking a list
  #
  elist = []
  if (entry[0] == '['):              # brackets indicate a list
                                     # [ <method>, <event>, <event>, ... ]				     
      # NOTE: 
      #
      # trimming spaces at start and end
      # will still leave spaces after commas
      #
      # removing all spaces before splitting
      # will collapse sequences of strings
      # 
      # removing spaces only after splitting
      # will harm indenting needed by python
      #
          
      # heuristic:				     
      # assume event, remove all spaces
      #	if caller then can't find event in event list
      # then assume code, re-enlist, but don't remove spaces
      #
          
      if (rmspace_f == 1):
        entry = re.sub(' ','',entry)   # remove spaces
      entry = entry[1:len(entry)-1]  # remove [ ] brackets           
      idx = entry.find(',')       # first element is method, remainder are events 
      #
      # split off first element, remove first commma, then split by semicolon
      #
      if (idx <= 0):
        elist = elist + [entry]
      else:
        elist = elist + [entry[0:idx]] + entry[idx+1:len(entry)].split(";")               
   
  return elist
           
#end enlist_string  
#
#-------------------------------------------------------------------------
# isKnownToPython
#                 purpose: unexpected words raise warnings
#                          this list of python keywords reduces the number of warnings raised
#
def isKnownToPython(word_to_test):   # word to test
  retval = False
  #
  # commonly used python calls
  #
  test_table = [ "print", "param.", "time.", "return", "pass"]
      
  for test_word in test_table:
    word_to_test = word_to_test.lstrip()   # remove leading whitespace
    if (word_to_test[0:len(test_word)] == test_word):
      return True
      
  return retval
# end isKnownToPython

#---------------------------------------------
# exceptionInfo
#         purpose: if the debugger raises an exception, 
#                  this routine is printed out afterwardss
#
def exceptionInfo(eobj):
  print "\nException in user code:"    
  print '-'*80
  traceback.print_exc(file=sys.stdout)  # print details of error
  print '-'*80
  print "*** Error:", eobj, " ***"
  print
  print "for help, type sc_help()"
#end exceptionInfo
    
class scb:

    def __init__(self,name="my_sc",
                      the_des_file=g_des_file,
                      the_out_file=g_out_file,
                      the_mq_type=g_mq_type):
      # globals 
               
      self.PROMPT = " scb > "                # user prompt
      self.VERSION = "1.0"
      self.name = name
      self.des_file = the_des_file  # in design ini file
      self.out_file = the_out_file  # out python file
      self.mq_type = the_mq_type    # flag for imports
      self.RMQ = True 
      if (g_mq_type =="zeromq"):
         self.RMQ = False  

      self.states = None          # list of states
      self.warning_count = None   # count of warnings
      self.evo = None             # event objects
      self.states = None          # state objects
      self.xitions = None         # transition objects
                              
      self.statetypes = SCBO.StateListObject(concurrent="ConcurrentState", 
                                    hierarchical="HierarchicalState", 
                                    history="HistoryState", 
                                    state="State")  # valid state types
      self.spe = None             # suppressed printing events
      self.chart_name = None      # chart name
      self.py_init = None         # python intializer
      self.iniDebug = None        # debug flag in ini file
      self.iniPrint = None        # print flag in ini file
      self.iniLimitAction = None  # limit action flag in ini file (prevent embedding code)
      self.iniGenCode = None      # generate python (verus syntax check only)
      self.iniGenCallbacks = None # generate callbacks versus read from file
      self.iniInterpret = None    # enter interpreter
      self.iniInsertCB = None     # name of callbacks file
      self.iniInsertCB_sav = None # copy of
      self.funcFromFile = None    # function copied from callback file
      self.scobj = None           # the instantiated statechart object
      self.callbacks_file = None  # callbacks file
      self.pio = None             # port initializer object
      self.pdo = None             # port definition object
      self.pco = None             # port configuration object

    #end __init__
                                   
    #---------------------------------------------
    # isStateValid
    #               purpose: returns true if state is known
    #
    def isStateValid(self,stateStr,            # state name 
                     disabled_f=False):   # also check disabled states 
      
      ii = 0
      while ii < len(self.states):
        if (self.states[ii].name == stateStr):  # if name matches name
          if (self.states[ii].disable):   # skip testing disable
            if (disabled_f):
               return True
            else:
              return False
          else:
            return True
        ii = ii + 1
      return False
    #end isStateValid
    
    
    #---------------------------------------------
    # parent_state
    #              purpose: returns parent of state
    #
    
    def parent_state(self,stateStr):        # state name
      
      # for each state, if match then return parent
      ii = 0
      while ii < len(self.states):
        if (self.states[ii].disable):   # skip disabled
          ii = ii + 1
          continue
        if (self.states[ii].name == stateStr):  # if name matches name
          return self.states[ii].parent, ii     # return parent, index (no error)
        ii = ii + 1
      return "", -1                 # return empty string, error
      
    #end parent_state
       
    #------------------------------------------------------------------------------
    # getIniKeySet
    #              purpose: simplifies getting data from ini file
    #              design: given an ini file, section, key, and list of params
    #                      get all params.
    #                      python code is permitted in ini file - check for
    #                      ambiguity ini comment versus python end of line ";"
    #
    def getIniKeySet(self,filename,   # ini file name
                    iniHandle,        # ini handle
                    section,          # ini section
                    keylist,          # list of keys in section
                    valuelist):       # return valuelist
      
      cmt_warn_f = False        # comment warning has high rate of false positives
      ii = 0                    # iterator
      err_f = False             # error flag
      while (ii < len(keylist)):                # for each key
        key = keylist[ii]                       # get key
        if iniHandle.has_option(section,key):   # if section and key exist in ini file
          value = iniHandle.get(section,key)    # then get value at section,key
          #
          # semicolons not in first column are not ini comments - if not followed by '
          # known' word then semantically ambiguous (high false positive rate)
          #
          idx = value.find(';')              # search for comment    
          if (idx != -1):
            if (not isKnownToPython(value[idx+1:len(value)]) and cmt_warn_f):
              self.warning_count += 1
              errm = "*** Warning: %d: ini comment ';' not in column 0, Python separator?\n"%(self.warning_count)
              errm = errm + "[%s]\n %s = %s ***" %(section,key,value)
              print errm
            # endif keyword not found      
          valuelist = valuelist + [ value ]
        else:
          #
          # second chance, value might be a list
          #
          sublist = []   # list as element of list
          count = 1      # look for KEY_n where n = 1,2,3...
          key_base = key + "_"
          new_key = key_base + str(count)
          if iniHandle.has_option(section,new_key):     # yes a list
            while True:
              subvalue = iniHandle.get(section,new_key)     # get value at section,key
              sublist = sublist + [subvalue]                # build sublist
              count = count + 1                             # increment key's index
              new_key = key_base + str(count)
              if not iniHandle.has_option(section,new_key): # test for next
                break                                       # not an error
            # end while
            valuelist = valuelist + [ sublist ]            # add sublist to list
          else:
            print "*** Error: %s, missing key \"%s\" in [%s] section ***" % (filename, key, section)
            err_f = True
    	    break
    	
        ii = ii +1
      #end while
      
      return err_f, valuelist
    # end getIniKeySet
    #------------------------------------------------------------------------------
    # unique_events
    #                purpose: checks uniqueness of events
    #                         fixes up "base = None" 
    # 
    def unique_events(self):
      #
      # test 1: removed
      # test 2:
      #  if any event id range set overlaps with any other event set id range  
      #   then collision return error 
           
      
      err_f = False
      
      if (not err_f):        # test 2
        ii = 0
        while (ii < (len(self.evo) -1)) and (not err_f):
           if (self.evo[ii].base == None):
             self.warning_count += 1
             print "*** Warning, event base cannot be None, Event: %s" % self.evo[ii].name 
             if (ii==0):
               self.evo[ii].base = 1
               print "Setting base to 1"  
             else:
               nextbase = int(self.evo[ii-1].base) + len(self.evo[ii-1].events) 
               print "Setting base to", nextbase 
               self.evo[ii].base = nextbase 
             # end else
           min1 = int(self.evo[ii].base)
           max1 = int(self.evo[ii].base) + len(self.evo[ii].events)
           jj = ii + 1
           while (jj < len(self.evo)) and (not err_f):
             if (self.evo[jj].base == None):
               self.warning_count += 1
               print "*** Warning, event base cannot be None, Event: %s" % self.evo[jj].name 
               nextbase = int(self.evo[jj-1].base) + len(self.evo[jj-1].events) 
               print "Setting base to", nextbase 
               self.evo[jj].base = nextbase
             # end if
             min2 = int(self.evo[jj].base)
             max2 = int(self.evo[jj].base) + len(self.evo[jj].events)
             if (min1 < min2):
               if (max1 > min2):
                 print  "*** Error, event collision, %s: base %d, %s: base %d ***"%(self.evo[ii].name,min1,
                                                                                        self.evo[jj].name,min2)
                 err_f = True
                 break
             else:
               if (max2 > min1):
                 print  "*** Error, event collision, %s: base %d, %s: base %d ***"%(self.evo[ii].name,min1,
                                                                                        self.evo[jj].name, min2)
                 err_f = True
                 break
             
             jj = jj +1
           #end while (jj)
          
           ii = ii + 1    
        #end while (ii) 
        
        # Make Unique:
        #
        # For every event, add the base to the index, save as list of ids, 
        # this value can be reverse mapped (as an index) back to the name and event name
        #
      if (not err_f):
        ii = 0
        while ((ii < len(self.evo)) and not err_f):
          event_set = self.evo[ii]
            
          event_set.ids = []
          event_offset = int(event_set.base)
          if (event_offset ==0):
             err_f = True
             print "*** Error: %s: Event base 0 is invalid ***" % event_set.name
             break; 
             
          jj = 0  
          while (jj < len(event_set.events)):
            event_set.ids = event_set.ids + [jj +  event_offset]         
            jj = jj +1
                      
          #end while events in group
            
          self.evo[ii].ids = event_set.ids   # put back
          self.evo[ii].updateList()          # updates combineLists function
                    
          ii = ii +1
            
        #end while all event sets   
        
      #endif not error
        
      return err_f
        
    # end unique_events
    
    #-------------------------------------------------------------------
    # verify_xition_state
    #                     purpose: make sure all transitions have a start
    # 
    def verify_xition_state(self):
      #
      # for every transition
      #  if transition not "start" or "end" 
      #   does start/end transition exist in list of states?

      err_f = False
      err_cnt = 0
      jj = 0
      while (jj < len(self.xitions)):   # catch all errors of this type
        xition_set = self.xitions[jj]
        if (xition_set.disable==True):  # skip disabled transitions
          jj = jj + 1
          continue
        xstart = xition_set.startState  
        xend = xition_set.endState
        if (xstart != "start"): 
           ii = 0
           match_f = False
           while (ii < len(self.states)):
             if (self.states[ii].disable):   # skip disabled
               ii = ii + 1
               continue
             state_set = self.states[ii]
             sname = state_set.name
             if (xstart == sname):
               match_f = True
               break
             ii = ii +1
           # end while
           if (not match_f):
             err_f = True
             err_cnt += 1
             print "*** Error %d: xition start state %s not found in states. ***"%(err_cnt,xstart)
        # endif start xition
        #
        if (xend != "end"): 
          ii = 0
          match_f = False
          while (ii < len(self.states)):
           if (self.states[ii].disable):   # skip disabled
             ii = ii + 1
             continue
           state_set = self.states[ii]
           sname = state_set.name
           if (xend == sname):
             match_f = True
             break
           ii = ii +1
          # end while
          if (not match_f):
            err_f = True
            err_cnt += 1
            print "*** Error %d: xition end state %s not found in states. ***"%(err_cnt,xend)
        # endif end xition
                                
        jj = jj + 1
      #end while inner loop
      
      return err_f
    # end verify_xition_state

    #-------------------------------------------------------------------
    # verify_xition_start
    #                     purpose: make sure all transitions have a start
    # 
    def verify_xition_start(self):
       
      # ----------------------------------------------------------------------------------------
      #
      # Check start transitions for states
      # a missing start will return the error below:
      #     "AttributeError: 'NoneType' object has no attribute 'activate'"
      #     With no other clues as to what is wrong
      # 
      # case
      # 1. For each state, if concurrent or hierarchical
      #    verify a start 'start', end <state> transition  
      #    
      # 2. For each state, concurrent or hierarchical
      #       if any child is also conc or hier, skip - covered in case 1
      #       else one of these child states must have a start 'start', end <state> transition
      #
      # ----------------------------------------------------------------------------------------
      
      print "Verifying transition starts"
      #
      # case 1:
      #
      err_f = False
      ii = 0
      while (ii < len(self.states)):
          if (self.states[ii].disable):   # skip disabled
            ii = ii + 1
            continue
          state_set = self.states[ii]
          stype = state_set.type
          sname = state_set.name
          if ((stype == self.statetypes.concurrent)  or (stype == self.statetypes.hierarchical)):
            match_f = False
            jj = 0
            while (jj < len(self.xitions)):
              xition_set = self.xitions[jj]
              if (xition_set.disable==True):  # skip disabled transitions
                jj = jj + 1
                continue
              xstart = xition_set.startState  
              xend = xition_set.endState
              if ((xstart == "start") and (xend==sname)):  
                 match_f = True          # hier or conc has start
                 break                   # done
              jj = jj + 1
            #end while inner loop
            if (not match_f):
              self.warning_count += 1
              print "*** Warning: %d: hier/conc state %s needs a start transition. ***" % (self.warning_count,sname)          
              # no break on warning          
          ii = ii + 1    
      #end while outer loop
    
      if (not err_f):
        #
        # case 2:
        #
        ii = 0
        while (ii < len(self.states) and (not err_f)):  # for each state hierarch or concurrent
          if (self.states[ii].disable):   # skip disabled
            ii = ii + 1
            continue
          state_set1 = self.states[ii]      
          stype1 = state_set1.type
          sparent1 = state_set1.parent         # the parent in the next search
          if ((stype1 == self.statetypes.concurrent) or (stype1 == self.statetypes.hierarchical)):       
            ii = ii + 1
            continue
          #
          # only regular states in this loop
          #
          jj = 0
          choices = []
          while (jj < len(self.states) and (not err_f)):  # search each child for common parent
            if (self.states[jj].disable):   # skip disabled
              jj = jj + 1
              continue
            state_set2 = self.states[jj]
            sname2   = state_set2.name  
            sparent2 = state_set2.parent
            
            if (sparent2==sparent1):
              choices = choices + [ sname2 ]     # make list of children of common parent
            jj = jj + 1
          # end while
         
          if (len(choices)!=0):
            match_f = False              # search list of children, find start, if any
            kk = 0  
            disabled=0   
            while(kk < len(self.xitions)): 
              if (self.xitions[kk].disable):   # count and skip disabled
                kk = kk + 1
                disabled = disabled+1
                continue
              xition_set = self.xitions[kk]
              xstart = xition_set.startState
              xend   = xition_set.endState               # search for start in list of children
              if (xstart=='start') and (SCBU.isInlist(choices,xend)):
                match_f = True
                break
              kk = kk + 1
            #end while 
            
            if (not match_f):
              print "*** Error: One of state(s) %s needs a start transition. ***" % choices
              if (disabled>0):
                print "Diagnostic: %d transition(s) disabled" % disabled
              err_f = True
              break             # stop searching on error        
          # end if list of children needing a start          
          
          ii = ii + 1    
        #end while outer loop 
           
      return err_f
      
    #end verify_xition_start  
    #-------------------------------------------------------------------------
    # valid_event
    #                purpose:
    # returns True if event found from class and event, or from event alone if unique
    #         False if event not found or event not unique w/o class 
    #
    def valid_event(self,event_phrase):
      
      event_f = False
      event_fixup = None
      
      idx0 = event_phrase.find(".")
      if (idx0 > 0):
        event_name = event_phrase[idx0+1:len(event_phrase)] # starting from "."
        class_name = event_phrase[0:idx0]                   # before "."
      else:
        event_name = event_phrase
        class_name = None
                 
      if (class_name == None):
        event_f, event_info = SCBO.NamedObject.namedListMatch(list_of_lists=self.evo,
                                                    name="events",
                                                    value =event_name,
                                                    unique_f = True)      # find all occurrences
        if (event_f):
          if (len(event_info)==1):                # unique, return class name
            class_name = event_info[0].name
            #
            # fixup allows the class to be added to the event info for later use
            #
            event_fixup = "%s.%s"%(class_name,event_name)
          else:
            event_f = False                       # non-unique, cannot resolve
            print "*** Error: Non-unique event: %s without class specifier ***" %(event_phrase)
      else:
        event_f, dummy = SCBO.NamedObject.namedListMatch(self.evo,"name",class_name,"events",event_name)
        
      return event_f, event_fixup 
    #end valid_event
    #-------------------------------------------------------------------
    # get_parents
    #             purpose: returns all parents of a state
    #
    def get_parents(self,state):
      
      err_f = False
      array=[]
      while(True):
        pstate, idx = self.parent_state(state)  # get parent
        if (idx<0):                        # error
          break
        array = array + [self.states[idx]]    # ordered list
        state = pstate
        if (pstate=='None'):               # top state
          break
      # end while
      if (idx <0):
        err_f = True
       
      return err_f, array
        
    # end get_parents
    #-------------------------------------------------------------------
    # common_hierarchy
    #                   purpose: finds common hierarchical parent
    #
    def common_hierarchy(self,list1,   # list of parents of state
                         list2):  # list of parents of state
      ii = len(list1) -1
      jj = len(list2) -1
      match_f = False
      match_value = ""
      #
      # work backwards, root is last element
      #
      while (ii >= 0):
        if (list1[ii].type == self.statetypes.hierarchical):
          match_value = list1[ii].name
          break
        ii = ii -1
      #end while
      if (ii >=0):
        while (jj >=0):
          if (list2[jj].name == match_value):
            match_f = True
            break
          jj = jj -1
        # end while
          
      return match_f, match_value
    #end common_hierarchy
    #-------------------------------------------------------------------
    # xition_check
    #         purpose: some transitions might, some will blow up, detect these before execution
    #
    def xition_check(self):
          
       err_f = False           # error
       disable_f = False       # flags disabled transitions
       
       # case: 
       # 1. Warning: any transition from A to X, when A's parent is not hierarchical will not transition 
       #
       # 2a. warning - a transition without an event may do nothing 
       #         (except for start, which is required -> Error).
       # 2b. Transitions without events that also have starts, will cause transition bugs on 'end', Error 
       # 2c. Events should be in the event list, Error
       #
       # 3. Any event that transitions to "end", the event can't be reused elsewhere - it prioritized
       #    the non-end transition over the "end" transition
       #
       # Note: case 3 must be run before case 2, because case 3 sets up exceptions for
       #       conditions tested in case 2
       # 
       # 4. Any transition to a state that is not in from's hierarchy will cause a failure when "to's" hierarchy
       #     restarts 
       
       #
       # case 1: for each transition, find the parent in the states, if the parent is not
       # hierarchical then generate a warning
       #
       ulist = []
       ii = 0     
       while(ii<len (self.xitions)):     
         xition_set = self.xitions[ii]
         if (xition_set.disable == True):  # skip disabled
           ii = ii +1
           disable_f = True
           continue
         xstart = xition_set.startState
         #
         # make a unique set of states so that if the state has been checked once, 
         # it doesn't need to be checked again
         #
         if (not SCBU.isInlist(ulist,xstart)): # if state in transition first time seen
           ulist = ulist + [ xstart ]   # then add to unique list (prevent duplicates)
            
           jj = 0
           break_f = False
           while (jj<len(self.states) and (not break_f)):
             if (self.states[jj].disable):   # skip disabled
                jj = jj + 1
                continue
             state_set1 = self.states[jj]
             state_name1   = state_set1.name
             if (state_name1 == xstart):
               type1 = state_set1.type
               if (type1 !=  self.statetypes.hierarchical):
                 parent1 = state_set1.parent
                 kk = 0
                 while(kk<len(self.states) and (not break_f)):
                   if (self.states[kk].disable):   # skip disabled
                     kk = kk + 1
                     continue
                   state_set2 = self.states[kk]
                   state_name2 = state_set2.name
                   if (state_name2 == parent1):
                     if (state_set2.type != self.statetypes.hierarchical):
                       self.warning_count += 1
                       print "*** Warning: %d: State %s is not hierarchical, nor its parent %s. ***" % (self.warning_count,
                                                                                                    state_name1, parent1)
                       print "    Transition will not trigger.\n"
                     #endif parent not hierarchical
                     
                     break_f = True   # parent found, break irregardless
                     break
                     
                   #endif found parent
                                
                   kk = kk + 1
                 
                 #end while inner loop - while searching for parent state info
               else:    # hierarchical, can stop here
                 break_f = True
                 break  
               #endif state not hierarchical
             
             jj = jj + 1      
           
           #end while middle loop - while searching for start state info 
    
         #endif state in transition first time seen      
    
         ii = ii + 1
       
       #end while outer loop - while transitions
       
       #
       # case 3:
       #
       end_f = False      # 'end' not yet detected
       if not err_f:  
         ii = 0
         while ((ii < len(self.xitions)) and (not err_f)):
            xition_set1 = self.xitions[ii]
            if (xition_set1.disable == True):  # skip disabled
              ii = ii +1
              disable_f = True
              continue
            xend = xition_set1.endState  
            if (xend == 'end'):
              xevent = xition_set1.event
              end_f = True
              jj = 0  
              while (jj < len(self.xitions)):
                xition_set2 = self.xitions[jj]
                if (xition_set2.disable == True):  # skip disabled
                   jj = jj +1
                   disable_f = True
                   continue
                if ((xevent == xition_set2.event) and 
                   (xition_set2.endState != 'end') and
                   (xevent != "None")):    # if "None" then missing "end", caught elsewhere
                  xstart = xition_set2.startState
                  print "*** Error: reused end event %s, with state %s, prevents end transition. ***" % (xevent,xstart)                  
                  err_f = True
                  break
                jj = jj + 1
              #end while inner loop
            ii = ii + 1
          #end while outer loop     
       #end if not error 
       
       #
       # case 2:
       #
       ii = 0     
       while(ii<len (self.xitions)):     
         event_f = False    
         xition_set1 = self.xitions[ii]
         if (xition_set1.disable == True):  # skip disabled
           ii = ii +1
           disable_f = True
           continue
           
         if (xition_set1.event=='None'):
           if (xition_set1.startState == 'start'):   # starts are necessary for concurrent and hierarchical states
             pass                                   # but, a state to state w/o event when the starting state 
           else:                                     # is hierarchical (but not 'start') introduces bugs on 'end'
             match_f = False
             jj = 0     
             while(jj<len (self.xitions)):     
               xition_set2 = self.xitions[jj] 
               if (xition_set2.disable == True):  # skip disabled
                  jj = jj +1
                  disable_f = True
                  continue          
               
               if ((xition_set1.startState == xition_set2.endState) and 
                 (xition_set2.startState=='start') and end_f):
                 print "Error (statechart bug) - missing event: "
                 print "state: %s, to state: %s, will transition incorrectly on end event." % (xition_set1.startState,
                                                                                        xition_set1.endState)
                 err_f = True
                 match_f = True
                 break
               jj = jj + 1
               
             #end while 
             if (not match_f):
               self.warning_count += 1
               print "*** Warning: %d: Transition %d, from state: %s, to state: %s, transition w/o event. ***" % (self.warning_count,
                                                                                    ii+1,
                                                                                    xition_set1.startState,
                                                                                    xition_set1.endState)
           #end else not start transition
         else: # not None event
           event_f, event_fixup = self.valid_event(xition_set1.event)
           if (not event_f):
             print "*** Error: In section [%s], Unresolved event: %s ***" % (xition_set1.name,
                                                                               xition_set1.event)
             err_f = True
             break
           else:
             if (event_fixup != None):
               
               self.warning_count += 1
               print "*** Warning: %d: In section [%s], event: %s, class added ***" % (self.warning_count,
                                                                                    xition_set1.name,
                                                                                    xition_set1.event)  
               self.xitions[ii].event = event_fixup  
         ii = ii + 1
       #end while 
       
       #
       # case 4: 'to' and 'from' must have a common hierarchical parent else 
       #         side-effects will occur
       #
       if not err_f:  
         ii = 0
         while ((ii < len(self.xitions)) and (not err_f)):
            xition_set = self.xitions[ii]
            if (xition_set.disable == True):  # skip disabled
              ii = ii +1
              disable_f = True
              continue
            xstart = xition_set.startState
            xend = xition_set.endState
            xname = xition_set.name
            array1 = None
            array2 = None
            
            if (xstart != 'start'):
              err_f, array1 = self.get_parents(xstart)
              if (err_f):
                #
                # if state is disabled, then convert to warning and disable the transition
                #
                if (self.isStateValid(value=xstart, disabled_f=True)): 
                  self.warning_count += 1
                  print "*** Warning: %d: Transition: %s, %s disabled, transition also ***"%(
                                                                                    self.warning_count,
                                                                                    xname,
                                                                                    xstart) 
                  self.xitions[ii].disable = True
                  err_f = False
                else:
                  print "*** Error: Transition %s, bad start state: \'%s\' ***" % (xname,xstart)
            
            if (not err_f):
              if ((xend != 'end') and (not self.xitions[ii].disable)):    
                err_f, array2 = self.get_parents(xend) 
                if (err_f):
                  #
                  # if state is disabled, then convert to warning and disable the transition
                  #
                  if (self.isStateValid(value=xend, disabled_f=True)): 
                    self.warning_count += 1
                    print "*** Warning: %d: Transition: %s, %s disabled, transition also ***"%(
                                                                                    self.warning_count,
                                                                                    xname,
                                                                                    xend) 
                    self.xitions[ii].disable = True
                    err_f = False
                  else:
                    print "*** Error: Transition %s, bad end state: \'%s\' ***" % (xname,xend)
              
            if (not err_f):
              if (array1 !=None) and (array2 != None):
                match_f, cv = self.common_hierarchy(array1,array2)
                if (not match_f):
                  print "*** Error: Transition %s, states %s, %s have no common hierarchical parent. ***" % (xname,
                                                                     xstart,xend)
                  err_f = True
                  break
            
            ii = ii + 1
         #end while
         
       if (not err_f):
         if (disable_f):         
           ii = 0
           while (ii < len(self.xitions)):
             if (self.xitions[ii].disable):
               self.warning_count += 1
               print "*** Warning: %d: In section [%s], transition disabled ***" % (self.warning_count,
                                                                                    self.xitions[ii].name)
             ii = ii + 1  
           #end while
           
       return err_f
       
    #end xition_check
    #-------------------------------------------------------------------------------------
    #
    #  get port parameters from ini file for zeromq
    def getIniPortZmq(self,fname, cp):
      
      err_f = False 
      pio = []   # port initialization
      pdo = []   # port definition
    
      section = "PORT_INIT"
      port_init = []               # initialization of list of params
      err_f, port_init = self.getIniKeySet(fname, cp, section,
             ['import_type','import_name'],port_init)		            
         
         
      if (not err_f):
        if (RMQ == True) and (port_init[0] == "zeromq"):
           print "*** Error: %s, unexpected import type [%s],  ***" % (fname, section)
           err_f = True
        else:  
          pio = SCBPZ.PortInitObject(import_type=port_init[0],import_name = port_init[1])
                      
      if (not err_f): 
          # count = 1
          # list = []
          # repeat:
          #   attach count to section [PORT_<X>]
          #   grab parameters from file
          #   put parameters into list
          #   append list
          #   increment count
          #
          count = 1
          section_base = "PORT_"
          section = section_base + str(count)
          if (not cp.has_section(section)):   # not optional if port  has been configured
            print "*** Error: %s, missing [%s] section ***" % (fname, section)
    	    err_f = True
          
          disable_cnt = 0
          pdo = []                     # list of [ ports and parameters ]
          while (cp.has_section(section) and (not err_f)):
            #
            # skip disabled ports
            #
            # why should ports ever be disabled?
            # if you are distributing a statechart, the ports "listened to" on the distant side
            # must not be "listened to" on the local side - else
            # the 2nd listener will get an "address in use" error.)
            #
            disable_f = False         # default is enabled (undistributed)
            key = 'disable'                                                 
            if cp.has_option(section,key):
              value = cp.get(section,key)
              value = value.strip()
              value = value.upper()          
              if (value=='TRUE'):
                disable_f = True
                disable_cnt = disable_cnt + 1
            
            iniPort = []                   # [ states and parameters ]
            err_f, iniPort = self.getIniKeySet(fname, cp, section,
                                    ['host','port','name','type','format','events'],iniPort)
            if (err_f):
              break
    	 
    	    pdo = pdo + [SCBPZ.PortDataObject(host=iniPort[0], # ip address
                         port=iniPort[1],                      # ip port
                         name=iniPort[2],                      # label
    	                 type=iniPort[3],                      # zeromq connection type
                         format = iniPort[4],                  # json/yaml                
                         events = iniPort[5],                  # class of events valid for port
                         disable = disable_f)]                 # if disabled then don't listen
            
            count = count + 1
            section = section_base + str(count)
          #end while
      return err_f, pio, pdo, disable_cnt 
    # end getIniPortZmq
    #-------------------------------------------------------------------------------------
    #
    #  get port parameters from ini file for Rabbitmq
    def getIniPortRmq(self,fname, cp):
      
      err_f = False 
      pio = []   # port initialization
      pco = []   # port configuration
      pdo = []   # port definition
    
      section = "PORT_INIT"
      port_init = []               # initialization of list of params
      err_f, port_init = self.getIniKeySet(fname, cp, section,
             ['import_name','host','userid','password'],port_init)		            
         
         
      if (not err_f):
          pio = SCBPR.PortInitObject(import_name = port_init[0],
                                    host        = port_init[1],
    		                    userid      = port_init[2],
    			            password    = port_init[3]) 
            
      if (not err_f):
          count = 1
          section_base = "PORT_CONFIG_"
          section = section_base + str(count)
          if (not cp.has_section(section)):   # optional for distributed state machines
            print "*** Error: %s, missing [%s] section ***" % (fname, section)
    	    err_f = True
        
      if (not err_f):
          while (cp.has_section(section) and (not err_f)):
            iniPort = []                   # [ states and parameters ]
            err_f, iniPort = self.getIniKeySet(fname, cp, section,
                                        ['channel_id','exchange','type', 'queue','msg_tag'],
    			            iniPort)
            if (err_f):
              break
    	  
    	    #
    	    # convert channel_id string to number
    	    # now the array can be passed directly into the configuration call
    	    # 
    	    iniPort[0] = int(iniPort[0])
            
            iniPort[3] = iniPort[3].strip()
            if (iniPort[3] == 'None'):
              iniPort[3] = None
    	
            pco = pco + [PortConfigObject(channel_id = iniPort[0],
                                          exchange   = iniPort[1],
                                          type       = iniPort[2],
                                          queue      = iniPort[3],
                                          msg_tag    = iniPort[4])]
            count = count + 1
            section = section_base + str(count)
          #end while                
           
      if (not err_f): # list of input and output ports
          port_data = []                     # list of [ ports and parameters ]
          count = 1
          section_base = "PORT_"
          section = section_base + str(count)
          if (not cp.has_section(section)):   # not optional if port  has been configured
            print "*** Error: %s, missing [%s] section ***" % (fname, section)
    	    err_f = True
          
          pdo = []
          while (cp.has_section(section) and (not err_f)):
            iniPort = []                   # [ states and parameters ]
            err_f, iniPort = self.getIniKeySet(fname, cp, section,
                                        ['name','type','port','event_id'],
    			            iniPort)
            if (err_f):
              break
    	 
    	    pdo = pdo + [SCBPR.PortDataObject(name=iniPort[0],
                         type=iniPort[1],port=iniPort[2],
    	                             event_id =iniPort[3])] 
            port_data = port_data + [iniPort]
            count = count + 1
            section = section_base + str(count)
          #end while
      return err_f, pio, pco, pdo 
    # end getIniPortRmq
    #-------------------------------------------------------------------
    # verify_ports 
    # 
    # 1. test event in outgoing port against event-set => Warning
    #    ("None" indicates port not used)
    def verify_ports(self,pdo,evo):
      err_f = False

      ii = 0                       # case 1
      while ii < len(pdo):
        pdo_set = pdo[ii]          # look at talkers
        if (not SCBU.isInlist(cmo.inputSocketTypes(),pdo[ii].type) and (pdo_set.events != "None")):
          event_f, dummy = SCBO.NamedObject.namedListMatch(self.evo,"name",pdo_set.events)
          if (not event_f): 
             self.warning_count += 1
             print "*** Warning: %d, Unrecognized port event: %s in [PORT_%d].***"%(
             (self.warning_count,pdo_set.events,ii+1))   
             print "Use \'None\' in events field to disable warning"         
        ii += 1
      # end while

      return err_f

    # end verify_ports
    #------------------------------------------------------------------- 
    # get_ini_params
    #                purpose: get parameters from the ini file
    #   
    def get_ini_params(self,cp,fname):   # configparams, filename
      global g_cb_file      
      err_f = False
      port_f = False
      pio = None  # port initialization    
      pco = []    # port configuration
      pdo = []    # port definition
          
      if (not err_f):
        section = "STATECHART"
        if (not cp.has_section(section)):
          print "*** Error:", fname, "missing [%s] section ***" % (section)
          err_f = True  
      
      if (not err_f):     
        key = "name"              # The "name" of the statechart => <name>.py
        if cp.has_option(section,key):
          self.chart_name = cp.get(section,key)  
        else:
          print "*** Error: %s, missing key \"%s\" in [%s] section ***" % (fname, key, section)
          err_f = True    
      
      if (not err_f): 
        self.py_init = []
        section = "INITIAL"        # Startup python code can be placed directly into the ini file
        if (not cp.has_section(section)):
          self.warning_count += 1
          print "*** Warning: %d, %s: missing [%s] section ***" % (self.warning_count,fname,section)      
        else:   
          count = 1
          key = "Python_"
          key = key + str(count)       
          while cp.has_option(section,key):
            value = cp.get(section,key) 
            self.py_init = self.py_init + [ value ] # initial python program stored here
            count = count +1
            key = "Python_" + str(count)
          #end while
          key = "file"           # Startup python code can be read/executed from file
          if cp.has_option(section,key):                    
            pyinit_name = cp.get(section,key) 
            if (pyinit_name=='None') or (pyinit_name==''):
              pass
            else:
              if (len (self.py_init) >0):
                self.warning_count +=  1 
                print "*** Warning: %d, %s: section [%s] two forms of initialization ***" %(self.warning_count,fname,section)          
              try:
    	        pyfp = open(pyinit_name,'r')
              except IOError:
                print "*** Error: %s, [%s] section, key [%s], cannot open: %s ***" %(fname,section,key,pyinit_name)
                err_f = True
              
              if (not err_f):
                line = pyfp.readline()    
                while (line != ""):            
                  sz = len(line)
                  if (line[sz-1] == '\n'):   # remove linefeed, but preserve indenting
                      line = line[0:sz-1]
                
                  self.py_init = self.py_init + [ line ]  # initial python program stored here
                  line = pyfp.readline()
                #end while
                pyfp.close()
          #
          # Callbacks is a file that contains class(Actions) for handling events
          # and may also be a commandline parameter. 
          # If present, the commandline overrides this ini file (with a warning)
          #
          # The key is:  "InsertCB"   
  
      if (not err_f):  
        section = "OPTIONS"
        if (not cp.has_section(section)):
          print "*** Error: %s, missing [%s] section ***" % (fname, section)
          err_f = True
      #
      # these are optional options
      #
      if (not err_f):
        self.iniDebug = 0           
        key = "Debug"
        if cp.has_option(section,key):
          tmp = cp.get(section,key)   # remember param comes in as string
          tmp = tmp.strip()
          tmp = tmp.upper()      
          if ((tmp=='TRUE') or (tmp=='1')):
            self.iniDebug = 1
          
        self.iniPrint = 0
        key = "Print"
        if cp.has_option(section,key):
          tmp = cp.get(section,key)
          tmp = tmp.strip()
          tmp = tmp.upper()
          if ((tmp=='TRUE') or (tmp=='1')):
            self.iniPrint = 1
        
        self.iniLimitAction = 0                    # for future use
        key = "LimitAction"
        if cp.has_option(section,key):
          tmp = cp.get(section,key)
          tmp = tmp.strip()
          tmp = tmp.upper()
          if ((tmp=='TRUE') or (tmp=='1')):
            self.iniLimitAction = 1
        
        self.iniGenCode = 0                      # is this needed?
        key = "GenCode"
        if cp.has_option(section,key):
          tmp = cp.get(section,key)
          tmp = tmp.strip()
          tmp = tmp.upper() 
          if ((tmp=='TRUE') or (tmp=='1')):
             self.iniGenCode = 1
        
        self.iniGenCallbacks = 0                # is this needed?
        key = "GenCallbacks"
        if cp.has_option(section,key):
          tmp = cp.get(section,key)       
          tmp = tmp.strip()
          tmp = tmp.upper()
          if ((tmp=='TRUE') or (tmp=='1')):
            self.iniGenCallbacks = 1   
        
        self.iniInterpret = 0                    # is this needed?
        key = "Interpret"
        if cp.has_option(section,key):
          tmp = cp.get(section,key) 
          tmp = tmp.strip()
          tmp = tmp.upper()
          if ((tmp=='TRUE') or (tmp=='1')):
            self.iniInterpret = 1 
              
        self.iniInsertCB = ""
        if (g_cb_file != None):    # command line callbacks file takes precidence
          self.iniInsertCB = g_cb_file
        key = "InsertCB"
        tmp = "None"
        if cp.has_option(section,key):       
          tmp = cp.get(section,key) 
          if (g_cb_file == tmp): # both point to same file
            pass
          else:                  # see if both point to different files
            tmp1 = tmp.strip()
            tmp1 = tmp1.upper()                  
            if (g_cb_file != None) and (tmp1 != "NONE"): # command line takes precedence
               self.warning_count += 1
               print "\n*** Warning, callbacks in command line (%s) and design file (%s) ***"%(tmp,g_cb_file)
               print "    Command line takes presidence and overrides design file."
               self.iniInsertCB = cp.get(section,key) 

      # ------------------         rpc          ---------------------
      if (not err_f):
        iniRpc_f = False
        self.iniRpc = None
        section = "RPC" 
        if cp.has_section(section):
           iniRpc_f = True 
           iniRpc = []                   # [ rpc parameters ]
           err_f, iniRpc = self.getIniKeySet(fname, cp, section,
                                        ['enable','ip','port','server','client'],iniRpc)
                                        # [0]     [1]   [2]    [3]      [4]   
        else:
          print "\n*** RPCs Disabled ***" 

        if (iniRpc_f and not err_f): 
          tmp = iniRpc[0]       # param conversion 
          tmp = tmp.strip()
          tmp = tmp.upper()
          if ((tmp=='TRUE') or (tmp=='1')):
            iniRpc[0] = True
            print "\n*** RPCs Enabled ***"
          else:
            iniRpc[0] = False
            print "\n*** RPCs Disabled ***"
          
          skiplist = []                      # build a skip list
          count = 1
          key_base = "skip_"                 
          key = key_base + str(count)
          while True:                   
            if cp.has_option(section,key):   # if section and key exist in ini file
              key = key_base + str(count)
              value = cp.get(section,key)
              skiplist = skiplist + [value]
              count = count + 1
              key = key_base + str(count)
            else:
              break                          # done
          # end while
          
          self.iniRpc = SCBO.IniRpcObject(enable=iniRpc[0],  # enable process
                                          ip=iniRpc[1],      # server ip address
                                          port=iniRpc[2],    # ip port
                                          server=iniRpc[3],  # server file
                                          client=iniRpc[4],  # client classes file
                                          skiplist=skiplist )# skiplist  
          
      # ------------------         states          ---------------------
       
      # states may be partitioned in the design file:
      # chunk 1 = 		STATE_1, STATE_2
      # chunk 2 = 		STATE_1_1, STATE 1_2, ...
      # chunk 3 = 		STATE_2_1, STATE 2_2, ...
      
      if (not err_f):           
        base_count = 0
        first_f = True
        count = 1
        section_base = "STATE_"
        section = section_base + str(count)
        if (not cp.has_section(section)):
          print "*** Error: %s, missing [%s] section ***" % (fname, section)
          err_f = True
       
      if (not err_f):
        self.states = []                     # list of [ states and parameters ]
        stateSet = []
        while (not err_f):
          if cp.has_section(section): 
            iniState = []                   # [ states and parameters ]
            err_f, iniState = self.getIniKeySet(fname, cp, section,
                                        ['name','parent','type','entry','do', 'exit'],iniState)
                                        # [0]    [1]      [2]    [3]    [4]   [5]
            if (err_f):
                break
     
            #
            # disable is an option 
            #
            disable_f = False         # default is enabled
            key = 'disable'           # disabling has use in debugging
            if cp.has_option(section,key):
              value = cp.get(section,key)
              value = value.strip()
              value = value.upper()          
              if (value=='TRUE'):
                disable_f = True 
            
            stateObject = SCBO.StatesObject(name   = iniState[0],
                                       parent = iniState[1],
                                       type   = iniState[2],
                                       entry  = iniState[3],
                                       do     = iniState[4],
                                       exit   = iniState[5],
                                       disable = disable_f)
            if (stateObject.name == "None"): 
              print "*** Error: %s, section [%s], \"None\" not permitted for state name  ***" % (fname, section)
              err_f = True
              break
              
            if (not disable_f): 
              parent = stateObject.parent              # check for valid parent                      
              if not self.isStateValid(parent):             # catches spelling errors
                #
                # if state is not there, check to see if it has been defined but disabled 
                # if so, then warning, ask user if they want dependencies disabled.
                #
                if self.isStateValid(stateStr=parent,disabled_f = True):
                  self.warning_count +=  1
                  print "*** Warning: %d, State %s disable, disabling dependent state %s.***" % (
                    (self.warning_count,parent,stateObject.name))  
                  disable_f = True
                else:
                  # if a parent is 'None', then that is ok, indicates top hierarchy
                  if (parent!='None'):
                    print "*** Error: %s, section [%s], \"%s\" has no parent  ***" % (fname, section, parent)
                    err_f = True
                    break
    
              type = stateObject.type              # check for valid type
              if (not SCBU.isInlist(self.statetypes.list,type)): 
                print "*** Error: %s, section [%s], invalid state \"%s\" for key \"%s\" ***" % (fname, 
                                                                              section, type, key)
                print "Valid states - ", self.statetypes.list
                err_f = True
                break
            
            #endif not disabled       
            
              
            self.states = self.states + [stateObject]    # next
            stateSet = stateSet + [stateObject]
                
            count = count +1
            section = section_base + str(count)
          else:                                 # appending _1 and trying again
            last_count = count -1
            count = 1                           # reset counter
            base_count = base_count + 1         # create a middlefix
            if (first_f):                       # first time only
              new_base = section_base           # save the original base
              first_f = False
            
            #
            # name of state set is the name of the first hierarchial state found, 
            # else, the first entry's name
            #
            state_f = False
            state_f, state_list = SCBO.NamedObject.namedListMatch(stateSet,"type",self.statetypes.hierarchical)
            if (state_f):
              top_name = state_list.name 
            else:
              top_name = stateSet[0].name
              
            print  "\nState set %d, %s: %d states" % (base_count,top_name,last_count)
              
            stateSet = []
          
            section_base = new_base + str(base_count) + "_"   # append middlefix
              
            section = section_base + str(count)               # append postfix
            
            if not cp.has_section(section):                   # test for no more   
              break          
              
          #end if
        #end while  
        
      if (not err_f):  # count states, skipping disabled  
        ii = 0
        esum = 0
        dsum = 0
        while (ii < len(self.states)):
          if (self.states[ii].disable == False):
            esum = esum + 1
          else:
            dsum = dsum + 1
          ii = ii + 1
    
        ssum = 0
        match = "[STATE_"
        inifp = open(fname,'r') # 
        
        line = inifp.readline()
        while (line !=""):
          if (line[0:len(match)]==match):
            ssum= ssum + 1
          line = inifp.readline()  
        # end while
        
        inifp.close()
        print "States: %d total, %d enabled, %d disabled" % (ssum,esum,dsum)
        if (ssum != esum + dsum):
          self.warning_count += 1 
          print "*** Warning: %d, %s, States don't add up. Duplicate section or badly named section? ***" % (self.warning_count,fname)      
        
      # ------------------         events               --------------------- 
      
        events = []
        scount = 1
        section_base = "EVENTS_"
        section = section_base + str(scount)
        if (not cp.has_section(section)):
          self.warning_count += 1
          print "*** Warning: %d, %s: missing [%s] section ***" % (self.warning_count,fname,section) 
        else: 
                             # list of [ events_by_name ]
          while (cp.has_section(section) and (not err_f)):
            iniEvent = []                   # [ events and parameters ]
          
            key = "base"                   # event value base - keeps event values unique across classes
            if cp.has_option(section,key):
              value = cp.get(section,key)       
              if (value.strip() == 'None'):          # test for string 'None'
                value = None                         # convert to python None
              iniEvent = iniEvent + [ value ]
            else:
               print "*** Error: %s, missing key \"%s\" in [%s] section ***" % (fname, key, section)
               err_f = True
    	       break
          
            key = "name"
            if cp.has_option(section,key):
              value = cp.get(section,key) 
              iniEvent = iniEvent + [ value ]
            else:
               print "*** Error: %s, missing key \"%s\" in [%s] section ***" % (fname, key, section)
               err_f = True
    	       break       
            #
            # pick up a list of events, each identified by event_x where x increments by 1
            #
            kcount = 1
            key_base = "event_"
            key = key_base + str(kcount)
            if (not cp.has_option(section,key)):
              print "*** Error: %s, missing key \"%s\" in [%s] section ***" % (fname, key, section)
              err_f = True
    	      break  
     
            while (cp.has_option(section,key)):  
              value = cp.get(section,key) 
              iniEvent = iniEvent + [ value ]
              kcount = kcount +1                # next key
              key = key_base + str(kcount)
            #end while
            
            scount = scount + 1                 # next section
            section = section_base + str(scount)
            events = events + [iniEvent]
        # end else events section
      # end if no error
      self.evo = []    
      if (not err_f): 
        #
        # turn events into a named object suitable for use
        # 
        ii = 0  
        sum =0
        while ii < len(events):
          #
          # the file is needed when the events have to be imported into python, when
          # objects are used in files distant from where declared
          #
          self.evo += [SCBO.EventObject(file=self.chart_name,base=events[ii][0], 
                                         name=events[ii][1], events=events[ii][2:]) ]
          print "Event set %d - %s: %d events, base: %s " % (ii+1, events[ii][1],
                                                             len(self.evo[ii].events), 
                                                             self.evo[ii].base)
          sum = sum + len(self.evo[ii].events)
          ii = ii + 1
        # end while iterating events    
      
        err_f = self.unique_events()  # test for unique events, 
                                 # if ok, generate unique ids for events
        #
        # errors in event uniqueness are unrecoverable
        #
        if (not err_f):
          print "%d events total" % sum     
          
      # ---------------- optional event suppress print --------------------------- 
       
        section = "SUPPRESS_PRINT"
        if (cp.has_section(section)):
    
          self.spe = []                   # [ <class>.<event> , ... ]      
           
          #
          # pick up a list of events, each identified by event_x where x increments by 1
          # allow section with no entries
          #
          kcount = 1
          key_base = "event_"
          key = key_base + str(kcount)
        
          while (cp.has_option(section,key)):  
            value = cp.get(section,key) 
            self.spe = self.spe + [ value ]
            kcount = kcount +1                # next key
            key = key_base + str(kcount)
          #end while
            
          #
          # check for event validity
          #
          ii = 0
          while ii < len(self.spe):
            event = self.spe[ii]
            event_found, event_fixup = self.valid_event(event)
            if not event_found:
              print "*** Error: section [%s], unresolved event %s ***" %(section,event)
              err_f = True
              break
              if (event_fixup!=None):
                self.spe[ii]=event_fixup
            ii = ii + 1
          # end while
              
          if (not err_f):
            print "%d suppressed printing events\n" % len(self.spe)
        #end if section 
                           
      # ----------------       transitions          --------------------------- 
      
      # transitions may be partitioned in the design file:
      # chunk 1 = 		TRANSITION_1, TRANSITION_2
      # chunk 2 = 		TRANSITION_1_1, TRANSITION 1_2, ...
      # chunk 3 = 		TRANSITION_2_1, TRANSITION 2_2, ...
     
      if (not err_f):
        first_f = True
        base_count = 0
        count = 1
        section_base = "TRANSITION_"
        section = section_base + str(count)
        if (not cp.has_section(section)):
          print "*** Error: %s, missing [%s] section ***" % (fname, section)
          err_f = True
       
      if (not err_f):
        self.xitions = []                     # list of [ transitions and parameters ]
        while (not err_f):
          if cp.has_section(section):
            iniXition = []                   # [ transitions and parameters ]
            err_f, iniXition = self.getIniKeySet(fname, cp, section,
                                        ['start','end','event','guard','action'],iniXition)
                                        #  [0]     [1]     [2]    [3]    [4]
            if (err_f):
                break
            #
            # disable is option 
            #
            disable_f = False         # default is enabled
            key = 'disable'           # disabling has use in debugging
            if cp.has_option(section,key):
              value = cp.get(section,key)
              value = value.strip()
              value = value.upper()          
              if (value=='TRUE'):
                disable_f = True
            
            self.xitions += [SCBO.XitionsObject(name=section,
                                                startState=iniXition[0],
                                                endState=iniXition[1],
                                                event=iniXition[2],
                                                guard=iniXition[3],
                                                action=iniXition[4],
                                                disable=disable_f)]    
            count = count +1
            section = section_base + str(count)
          else:
            last_count = count -1
            count = 1                           # reset counter
            base_count = base_count + 1         # create a middlefix
            if (first_f):                       # first time only
              new_base = section_base           # save the original base
              first_f = False                   # clear first flag
            
            print  "Transition set %d: %d transitions" % (base_count,last_count)
             
            section_base = new_base + str(base_count) + "_"   # append middlefix
              
            section = section_base + str(count)               # append postfix
            
            if not cp.has_section(section):                   # test for no more 
              break      
          #endif
        #end while transitions

        if (not err_f):
          err_f = self.verify_xition_state() # all xitions must have matching states
        
        if (not err_f):
         err_f = self.verify_xition_start()  # all hierarchical states must have start xitions  
         
        if (not err_f):
          err_f = self.xition_check()        # look for other problems in transitions
        
      # endif no error, collect transitions
        
      if (not err_f):  # count transitions, skipping disabled
        ii = 0
        esum = 0
        dsum = 0
        while (ii < len(self.xitions)):
          if (self.xitions[ii].disable == False):
            esum = esum + 1
          else:
            dsum = dsum + 1
          ii = ii + 1
         
        ssum = 0
        match = "[TRANSITION_"
        inifp = open(fname,'r') # 
        
        line = inifp.readline()
        while (line !=""):
          if (line[0:len(match)]==match):
            ssum= ssum + 1
          line = inifp.readline()  
        # end while
        
        inifp.close()
        print "Transitions: %d total, %d enabled, %d disabled\n" % (ssum,esum,dsum)
        if (ssum != esum + dsum):
          self.warning_count += 1 
          print "*** Warning: %d %s, Transitions don't add up. Duplicate section or badly named section? ***" % (self.warning_count,fname)        
      
      # ---------------- optional ports ---------------------------
      #
      # allows switch between types (zmq,rmq) of distributed message queues
      #
            
        section = "PORT_INIT"
        if (cp.has_section(section)):   # optional for distributed harel machines
          port_f = True
          if (RMQ):
            err_f, pio, pco, pdo = self.getIniPortRmq(fname,cp)
          else:
            #
            # all ports are placed into object, even disabled
            #
            err_f, pio, pdo, dcnt = self.getIniPortZmq(fname,cp)
            #
            #print "pdo=",SCBO.NamedObject.combineLists(pdo)
            #
            if not err_f:
              err_f = self.verify_ports(pdo,self.evo)
             
      if not err_f:  
        if port_f: 
          if (RMQ):                                 # only rmq has port config
            print "%d port configuration(s)" % (len(pco)) 
            print "Ports: %d port(s)" % (len(pdo))
          if (ZMQ):                                 # ony zmq permits disabling ports 
            print "Ports: %d port(s), %d disabled" % (len(pdo),dcnt)
        else:  
          print "Ports: No ports"
      
      return err_f, pio, pco, pdo
      
    # end get_ini_params    
     
    #-------------------------------------------------------------------------
    # isParamKeyword
    #                 purpose: unexpected words raise warnings
    #                          this list of statechart keywords reduces the number of warnings raised
    #
    def isParamKeyword(self,word_to_test):  # word to test
      retval = False
      #
      # commonly used shortcuts require "param." prefix
      #
      test_table = [ "sendEvent" ]
      
      for test_word in test_table:
        word_to_test = word_to_test.lstrip()   # remove leading whitespace
        if (word_to_test[0:len(test_word)] == test_word):
          return True
      
      return retval
    # end isParamKeyword
    #-------------------------------------------------------------------------
    # proc_func_list
    # purpose:
    # the parameter is a list containing a function followed by parameters
    #
    # [ <function_name>(), param1, ... ]
    #
    # the parameters may be events or python statements
    #
    
    def proc_func_list(self,plist,     # parameter list
                       type,      # state or transition key
                       wfp,       # write file pointer
                       debug_f):  # debug flag
                        
        method = plist[0]
        port_val = None
            
        # method_name is method with parens removed
        # (and the designer may forget to put the parenthesis in
        # to begin with)
        #
        
        method_name = re.sub("\(\)","",method)
        method = method_name + "()"
    	
        #
        # convert () to (Guard) or (Action)
        #
        
        if (type == "guard"):  # guards are special
          method = re.sub("\(","(Guard",method)
        else:   
          method = re.sub("\(","(Action",method)  
        
        buf1 = "class %s:" % (method)
        if (type == "guard"):
          buf2 = "  def check(self,runtime,param):"
        else:	 
          buf2 = "  def execute(self,param):"
        if (self.iniPrint):  
          print buf1
          print buf2
        if (wfp != None):
          wfp.write(buf1 + "\n")
          wfp.write(buf2 + "\n")             
        # 
        #
        # second pass through function parameter list
        # to interpret what comes after, whether  a port
        # that requires decoding, or a python statement
        #
        jj = 1
        port_f  = False   # each of these are vectors for processing design parameters
        event_f = False
        while (jj < len(plist)):	
              
            phrase = plist[jj]
            idx0 = phrase.find(".")
            if (idx0 > 0):
                event_name = phrase[idx0+1:len(phrase)] # starting after "."
                    
            else:                        # class not given (hope unique event)
                event_name = phrase    
                            
            event_f, event_fixup = self.valid_event(plist[jj])
            if (event_f):
              if (event_fixup != None):
                plist[jj] = event_fixup
              event_name = plist[jj]
                        
            if ((not event_f) and (self.pio != None)):  # search on param (as port)
               port_f, port_list = SCBO.NamedObject.namedListMatch(self.pdo,"name",plist[jj]) 
    
            buf2 = ""
            if (event_f):   # data in list is not python code, interpret as event to be sent
                            # event may be translated to:
                            #
                            # if not port or data then
                            #   sendEvent(<eventclass>.<eventname>, None) 
                            #
                            # if function name matches portname then
                            #   param.sendEventAsMsg(port,event,[data])
    	      
                            # Note1: when building states that emit transition events 
                            #        that are not through ports,then
                            #        event data values are unknown
                            # Note2: when method names match port names then
                            #        event names and also data values are known
                            # Note3: Having the method the name of the port does not scale
                            #        Alternative is to have port immediately before event:
                            #        [<method>(),<port>;<event>]
                                     	      
                match_f, port_list = SCBO.NamedObject.namedListMatch(self.pdo,'name',method_name)
                if (match_f):
                   port_val = method_name   # "old" style does not scale 
                    
                if (match_f or port_f):    # send event to port 
                  event_found, event_fixup = self.valid_event(plist[jj])
                  if (event_found):
                    if (event_fixup!=None):
                      plist[jj]=event_fixup
                    buf1 = "    param.sendEventAsMsg(\'%s\',%s)" % (port_val,plist[jj])
                    port_f = False
                  else:  # invalid event
                    print "*** Error: Undefined event:%s, at %s ***" % (plist[jj],method_name)
                    return -1
                  # endif event found             
                else: # not event or port
                  #
                  # restore event_data by concatenating remainder of list
                  #
                  kk = 1                          # point to next
                  event_data =""
                  while(jj+kk < len(plist)):
                    if (kk > 1):                             # if not first
                      event_data = event_data + ","          # then add comma separator
                          
                    event_data = event_data + plist[jj+kk]   # concatenate param
                    kk = kk + 1
                  #end while
                      
                  jj = jj + kk - 1                           # equalize loop control
                      
                  if (len(event_data)==0):                   # Nothing done, use 'None'
                    event_data = 'None'	
                       	
                  buf1 = "    param.sendEvent(%s,%s)" % (event_name,event_data)            
                #
                # if on entry, a state emits an event and immediately transitions to 
                # another state, this may be the only way to view what's going on
                #
                if (debug_f):	       
                  #
                  # print <method_name>
                  #
                  buf2 =  "    print " +"\"scb_debug=" + plist[0] + "\""
    		
            elif (port_f):         		 	      
               port_val = plist[jj] # to be inserted into sendEventAsMsg
               jj = jj + 1
               continue
    	           
            else:   # not event, flag as warning unknown code, copy out w/o interpretation 
               #
               # check for known code snippets: 
               # "param" is the "self" for the statechart and its imports
               # so all declared functions may be directly called if they are simple
               #
               if (not isKnownToPython(plist[jj])):
                 #
                 # ex. The user may define a function in the Action, Entry, Do, Exit fields
                 #     with events or python code
                 #     These are checked against a list of common python keywords and left
                 #     alone or fixed up, for example, every event needs a sendEvent method.
                 #     For example entry = [<methodname>(), <event>] in an ini file becomes
                 #     in python code:
                 # 
                 #     def class <methodname>(Action): 
                 #        sendEvent(<event>)
                 #      
                 #     Methods known to the statechart may  be directly called too,
                 #     but as these methods are buried in a method declared on-the-fly, the
                 #     statechart parameter becomes a parameter, and their call
                 #     requires a context prefix to work, i.e. sendEvent() needs to become
                 #     param.sendEvent 
                 #     This tool knows that, so if a common method is called,
                 #     the "param." can be added by this tool
                 #
                 if (self.isParamKeyword(plist[jj])):
                   plist[jj] = "param." +  plist[jj]
                 else:
                   self.warning_count += 1
                   info = "# *** Warning: %d: %s, " % (self.warning_count,method)
                   info = info + "\"%s\" is not an Event or Port. ***" % (plist[jj])
                   print info
               #endif
                   
               buf1 = "    %s" % (plist[jj])               
    	#end else
                
            if (self.iniPrint):
              print buf1   
              if (len(buf2) >0):
                print buf2 
            if (wfp != None):
               wfp.write(buf1 + "\n")
               if (len(buf2) >0):
                 wfp.write(buf2 + "\n")
    	      
            jj = jj + 1
        #end while inner loop
    #end proc_func_list 
    #-------------------------------------------------------------------------
    # proc_func_stub
    #                purpose:
    # convert function into a statechart recognized function
    # "stub" indicates no user code from design file follows
    # 
    def proc_func_stub(self,method,    # name of method 
                       type,      # statechart type
                       obj_info,  # section info structured as a named object
                       wfp,       # write file pointer
                       debug_f=True):  # if True add print statements 
        
        # method_name is method with parens removed
        # (and the designer may forget to put the parans in
        # to begin with)
        
        method_name = re.sub("\(\)","",method)
        method = method_name + "()"
                 
        # convert () to (Guard) or (Action)
        #       
        if (type == "guard"):            
          method = re.sub("\(","(Guard",method)    
        else:   
          method = re.sub("\(","(Action",method)
    	    
        buf1 = "class %s:" % (method)                   
        if (type == "guard"):             
          buf2 = "  def check(self,runtime,param):"
          
        else:
          buf2 = "  def execute(self,param):"
    	    
        if (not debug_f):                # provide placeholder for code
           if (type == "guard"):              
             buf3 = "    return True"
           else:
              buf3 = "    pass"                     
        else:                           # add debug/print statements to transition
           if (type=="action"):         # only transitions have start and end
             xfrom = obj_info.startState
             xto   = obj_info.endState
           else:
             xfrom = ""
             xto = obj_info.name
          
           msg1 = "%s -> %s" %(xfrom,xto) 	
           buf3 = "    print \"%s\"" % str(msg1)       # print "print str(message)"  
      
        if (self.iniPrint):
           print buf1
           print buf2
           print buf3
    	    
        if (wfp != None):
          wfp.write(buf1 + "\n")
          wfp.write(buf2 + "\n")
          wfp.write(buf3 + "\n")
    	              
    #end proc_func_stub
    #----------------------------------------------------------------------
    #
    # installProxy is a hack to install proxy call underneath statechart callback
    #
    def installProxy(self,wfp,method,func_text):
      # design:
      # 1. print first two lines of func_text
      #    should look something like:
      #         class foo(Action):
      #            def execute(self,param):
      # 2. print proxy call
      # 3. done
      lines = func_text.split("\n")
      wfp.write(lines[0]+"\n")
      wfp.write(lines[1]+"\n")
      wfp.write("    proxy.%s(param)\n"%method)
    # end installProxy
                  
    #-------------------------------------------------------------------------
    # gen_code_hooks
    #              purpose: from statechart info generate python code   
    #  
    def gen_code_hooks(self,pdo,   # port data object
                       evo,        # event object
                       wfp,        # write file handle
                       ulist,      # built list of unique method labels
                       inlist,     # set of lists of states or transitions
    		       type,       # index of function into states/transitions
    		       debug_f=True): # debug flag, generate debug message
          
      #
      # Note: Events are not processed in the TRANSITION event field.
      #       Badly formed events may slip through.
      #       Events in entry, do, exit, or action fields that are
      #       misspelled, will be assumed to be and treated as 
      #       python code statements - which will generate warnings or errors
      #       during importing the statechart object. 
      # 
      ii = 0          # iterator
      while (ii < len(inlist)):
        section_set = inlist[ii]        # reduce array of arrays
        if (type == "entry"):  # index into design file state list
          entry = section_set.entry
        elif (type == "do"):
          entry = section_set.do
        elif (type == "exit"):
          entry = section_set.exit
        elif (type == "guard"): # index into design file transition  list
          entry = section_set.guard
        elif (type == "action"):
          entry = section_set.action  
         
        entry = entry.strip()           # trim to remove spaces
        if (entry[0] == '['):           # brackets indicate a list
          plist = enlist_string(entry,1)   # turn string list into python list
          #
          # only generate code for method once
          # make sure events listed in methods have been defined
          # 
          
          if (not SCBU.isInlist(ulist,plist[0])):     # if method is unique
            ulist = ulist + [ plist[0] ]         # then add to unique list (to prevent duplicate functions)
      	
            #
            # Note1: Embedded spaces prevent searching for keywords for generating code BUT
            #        embedded spaces are necessary for python indenting for 
            #        copying design file python statements directly into output generated code -
            #        So, this is a two pass process:
            #        1. Remove spaces, if keywords are not found then
            #        2. Put spaces back treat as embedded python
            #
            # Note2: If you create a new keyword for a new feature, and don't test for it here,
            #        the code that tests for the keyword will fail later because of Note-1.
            #        
            # Note3: You can't mix and match embedded code with keywords. If a line without a keyword is 
            #        found the whole thing is treated as a direct copy.
    	
            #
            # first pass through function parameter list
            #
            port_f  = False   # each of these are vectors for processing design parameters
            event_f = False
            jj = 1                               # skip first entry, already processed
            while (jj < len(plist)):             # check for membership in events or ports
                #
                # is the first parameter an event?
                # if it contains a '.', then split into class and event
                # if it doesn't assume no class, assume event unique to all classes 
                # 
                
                event_f, event_fixup = self.valid_event(plist[jj])  # 
                if (event_f):
                  if (event_fixup != None):
                    plist[jj]= event_fixup           
                
                #
                # if not an event, see if value matches a port name
                #
                if (not event_f):
                  port_f,dummy=SCBO.NamedObject.namedListMatch(self.pdo,"name",plist[jj])
                
                if ((not event_f) and (not port_f)): # must be embedded python code, is this permitted?
                  if (self.iniLimitAction == 1):
                    print "*** Error: undefined event at entry = %s ***" % (inlist[ii])
                    return -1
                  else:  # assume embedded python code
                         # Note: A badly formed (i.e. misspelled) event will be interpreted as
                         #       a python statement
                         # space removal as part of enlisting hurts intent -> undo
                    plist = enlist_string(entry,0)
    	        break              # stop processing in  this loop
    	      #end if limitAction	  
      	                
                jj = jj + 1
                
            # end while middle loop
            
            # convert list to a statechart recognized function all
            
            method = plist[0]
            match_f = False
            if (self.funcFromFile != None):   # search callbacks file
              match_f,func_text,method_name = self.funcFromFile.getFuncFromFile(method)
            
            if (match_f):
              if (self.iniInsertCB_sav == None):         # flags first time in
                self.iniInsertCB_sav = self.iniInsertCB  # clear flag
                print                                    # add a blank line for extra separation
                if ((self.iniRpc != None) and self.iniRpc.enable):
                  print "Inserting RPC's"
                print "replacing from:",self.iniInsertCB # procedures read from here
              print " "+method               # debug                    
              if (self.iniPrint):     
                print func_text              # print as debug
              
              elif (wfp !=None):
                if ((self.iniRpc != None) and self.iniRpc.enable):
                  if (SCBU.isInlist(self.iniRpc.skiplist,method_name)): # check the skiplist
                     print "  skipping RPC for %s"%method_name          # intentional extra indent
                     wfp.write(func_text)                               # generate inline code
                  else:
                     self.installProxy(wfp,method_name,func_text)       # generate proxy call        
                else:
                  wfp.write(func_text)                                  # generate inline code
            #endif match in callbacks file    
            else:
              if (len(plist) > 1):
                self.proc_func_list(plist, type, wfp, debug_f) 
              else:
                self.proc_func_stub(method, type, section_set, wfp, debug_f)         
          #end if unique 
          else:
            #
            # states may vector to common routines, but only the first 
            # reference may  have a body
            #
            if (len(plist) > 1):  # if not unique and parameters
              self.warning_count += 1
              print "# *** Warning: %d: non-unique method: %s, ignored ***" % (self.warning_count,plist)        
          
        #end if list 
        else:                    # Alternate case: not list 
            skip_f = False        
            if entry == "None":
              skip_f = True
          
            if not skip_f:
            
              # throw away everything to the right of the "(" in the entry
              # has it been seen before?
              # if so, then skip
            
              if (SCBU.isInlist(ulist,entry)):  # if not seen before
                skip_f = True
      
            if (type == "guard"): 
                method_name = entry
                last_idx = entry.find("(")
                if (last_idx != -1):
                  method_name = entry[0:last_idx]
    
                if (method_name == "CountingGuard"):
                  skip_f = True                  # built-in method    
      
            if not skip_f:
                ulist = ulist + [ entry ]       # add to unique/processed list
                method = entry               
                #
                # convert function into statechart recognized function
                #
                match_f = False
                if (self.funcFromFile != None):   # search callbacks file
                  match_f,func_text,method_name = self.funcFromFile.getFuncFromFile(method)
                
                if (match_f): 
                  if (self.iniInsertCB_sav == None):         # flags first time in
                    self.iniInsertCB_sav = self.iniInsertCB  # clear flag
                    print                                    # add a blank line for extra separation
                    if ((self.iniRpc != None) and self.iniRpc.enable):
                       print "Inserting RPC's"
                    print "replacing from:",self.iniInsertCB # procedures read from here
                  print " "+method
                  if (self.iniPrint):
                     print func_text          
                  if (wfp !=None):
                    if ((self.iniRpc != None) and self.iniRpc.enable):
                      if (SCBU.isInlist(self.iniRpc.skiplist,method_name)): # check skiplist
                         print "  skipping RPC for %s"%method_name          # intentional extra indent
                         wfp.write(func_text)                               # generate inline code
                      else:
                         self.installProxy(wfp,method_name,func_text)       # generate proxy call    
                    else:
                      wfp.write(func_text)                                  # generate inline code
                # endif match in callbacks file

                # functions for which no code has been written
                # are stubbed by "pass" for Actions and
                #                "return True" for Guards
                # or a print statement saying something along the lines of:
                #  "I was here"
                #
                else:   # not a list, just a method alone
                  self.proc_func_stub(method,             # user entered 
                                 type,               # where found
                                 section_set,   # list of state or transition values
                                 wfp, debug_f)  # 
                          
            # endif not skipped
            
        ii = ii+ 1  
      #end while outermost loop (state or transition lists)    
        
      return 0, ulist
    # end gen_code_hooks
    #---------------------------------------------
    # commsCallbacksRmq
    #            purpose: generate the message queue "callbacks" 
    #
    def commsCallbacksRmq(self,pdo, # port data object
                          evo,      # event object
                          wfp):     # write file pointer
    		       
      cbObj = []        # callback object
      ii = 0
      while ii < len(pdo):
        #
        # Only inputs that are in "your" process need to be in callbacks.
        # 
        # Prior to distributing a statechart, there is only 1 process
        # after distributing there will be N processes, each of those N's
        # will be a listener. 
        #
        if (pdo[ii].type == 'input'):      
          cbObj = cbObj + [CallbackObject(queue=pdo[ii].port, event_id=pdo[ii].event_id) ]
        ii = ii +1
      #
      # an output port is an exchange
      # an input port is a queue
      #
      # sort by port, "sorted" is built-in for the purpose of aligning input ports (queues) 
      # with callbacks
      # each callback has all the expected messsages for the queue, if so configured
      #
      
      sortedCbo = sorted(cbObj,key =lambda dummy: dummy.queue)
      
      first_f = True        # statemachine vectors between
                            # 1: function definition+if, 
                            # 2: elif(s), and 
                            # 3: else+return
      last_queue = None
      mbuf = []
      retlist = []
      ii = 0
      
      while (ii < len(sortedCbo)):
      
        if (sortedCbo[ii].queue != last_queue):   # restart for each unique queue
          last_queue = sortedCbo[ii].queue   
          first_f = True
        if (first_f): 
          #
          # the callback function for the message queue listen thread
          # generate an expected messages list for mis-directed messages
          #      
          tbuf = "    def %s_queueCallback(self,msg):"   % (sortedCbo[ii].queue); mbuf += [tbuf]
          tbuf = "      thisFcn = \'%s_queueCallback\'" % (sortedCbo[ii].queue) ; mbuf += [tbuf]
          tbuf = "      err_f = False"                                          ; mbuf += [tbuf]
          tbuf = "      expctd = []"                                            ; mbuf += [tbuf]
          jj = 0
          while (jj<len(sortedCbo)):
            tbuf = "      expctd.append(\"%s\")"  % (sortedCbo[jj].event_id)     ; mbuf += [tbuf]  
            jj = jj +1 
          #
          # the key may be appended with json data
          # and looks like this:
          #
          # <event_class.event_id>:<event_data_as_json_string>
          #
          # match the key (up to the ':' separator), then extract the json data
          #
          first_f = False
        if (ii + 1) == len(sortedCbo) or (sortedCbo[ii+1].queue != last_queue):
          tbuf = "      if (isInlist(expctd,\'JsonData\')):"              ; mbuf += [tbuf]
          tbuf = "        evData = None"                                  ; mbuf += [tbuf]
          tbuf = "        eidx = msg.body.find(\':\')"                    ; mbuf += [tbuf]
          tbuf = "        if (eidx <0):"                                  ; mbuf += [tbuf]  
          tbuf = "          eidx = len(msg.body)"                         ; mbuf += [tbuf]
          tbuf = "        else:"                                          ; mbuf += [tbuf]
          tbuf = "          dataStr=msg.body[msg.body.find(\':\')+1:]"    ; mbuf += [tbuf]
          tbuf = "          evData = jsonpickle.decode(dataStr)"                 ; mbuf += [tbuf]
          tbuf = "        evStr = msg.body[0:eidx]"                       ; mbuf += [tbuf]
          tbuf = "        evid = EventObject.EventToId(self.evo,evStr)"   ; mbuf += [tbuf]
          tbuf = "        if (evid >0):"                                  ; mbuf += [tbuf]
          tbuf = "          self.sendEvent(evid,evData,True)"             ; mbuf += [tbuf]
          tbuf = "        else:"                                          ; mbuf += [tbuf]
          tbuf = "          emsg = \"%s: %s is not an event\" % (thisFcn,evStr)" ; mbuf += [tbuf] 
          tbuf = "          err_f = True"                                 ; mbuf += [tbuf]
          tbuf = "      elif (isInlist(expctd,msg.body) or isInlist(expctd,\'AnyEvent\')):" ; mbuf += [tbuf]
          tbuf = "        eid = EventObject.EventToId(self.evo,msg.body)" ; mbuf += [tbuf]
          tbuf = "        if (eid>0):"                                    ; mbuf += [tbuf]
          tbuf = "          self.sendEvent(eid,None,True)"                ; mbuf += [tbuf]
          tbuf = "        else:"                                          ; mbuf += [tbuf]
          tbuf = "          emsg = \"%s: %s Cannot decode event\" % (thisFcn,msg.body)" ; mbuf += [tbuf] 
          tbuf = "          err_f = True"                                 ; mbuf += [tbuf]   
          tbuf = "      else:"                                            ; mbuf += [tbuf] 
          tbuf = "        emsg = \"%s:Cannot decode header - (rd,[exp]):(%s,%s)\"%(" ; mbuf += [tbuf] 
          tbuf = "thisFcn,msg.body,expctd)"                               ; mbuf += [tbuf] 
          tbuf = "        err_f = True"                                   ; mbuf += [tbuf]
          tbuf = "      if (err_f):"                                      ; mbuf += [tbuf]
          tbuf = "        if (self.txtlog!=None):"                        ; mbuf += [tbuf]
          tbuf = "          self.txtlog.error(emsg)"                      ; mbuf += [tbuf]
          tbuf = "        else:"                                          ; mbuf += [tbuf] 
          tbuf = "          print emsg"                                   ; mbuf += [tbuf]    
          tbuf = "      msg.channel.basic_ack(msg.delivery_tag)"          ; mbuf += [tbuf]	
          #
          # build a list of queues and callbacks that can be input to the Subscribe method
          #
          queue = sortedCbo[ii].queue
          method = sortedCbo[ii].queue + "_queueCallback" 
          retlist = retlist + [[queue, method]]   # list of two-element lists	
          first_f = True 
        ii = ii + 1        
      # end while

      cbo = retlist

      # -------------- subscribe method ------------------
      tbuf =   "    def subscribe(self):" ;   mbuf += [tbuf] 
      if (len(cbo)==0):
        tbuf = "      pass" ;   mbuf += [tbuf] 
      else:
        ii =0
        while (ii<len(cbo)):
          #
          # The subscribe method instantiates a listener on a port
          # and a callback to handle the data that arrives on that port
          #
          tbuf="      self.comm.Subscribe(\"%s\",self.%s)"%(cbo[ii][0],cbo[ii][1]); mbuf += [tbuf]
          ii = ii + 1 
        # end while
      # end else

      # ------------- print/write to file ----------------------

      if (self.iniPrint):                # print code to display
        ii = 0
        while (ii < len(mbuf)):         
           print mbuf[ii]
           ii = ii + 1
        # end while
      # end if 
                                      # generate python code
      if (self.iniGenCode):				  
        ii = 0
        while (ii < len(mbuf)):         
           wfp.write( mbuf[ii] + "\n") 
           ii = ii + 1
        # end while
      #end if
      
      return retlist
      
    #end commsCallbacksRmq
    #---------------------------------------------
    # commsCallbacksZmq
    #            purpose: generate the message "callbacks" 
    #            copy params-of-interest from port definition into
    #            callback object, sort and process callback object
    #
    def commsCallbacksZmq(self,pdo, # port data object
                          evo,      # event object
                          wfp):     # write file pointer
    		       
      cbObj = []        # callback object
      ii = 0
      while ii < len(pdo):
        if SCBU.isInlist(cmo.inputSocketTypes(),pdo[ii].type):    
          cbObj += [SCBPZ.CallbackObject(index=ii,                # index into data def
                                         port=pdo[ii].port,       # port of interest
                                         type=pdo[ii].type,       # type
                                         format=pdo[ii].format,   # format to handle
                                         disable=pdo[ii].disable)]# skip this callback 
        ii = ii +1
 
      # This code is reused from rabbitmq callbacks which were designed first.
      # zeromq has no common exchanges (compared to rabbitmq)
      # however ports may be in common so treat port as exchange - 
      # - but ports are numbers can't be used as variable or function names - What to do? 
      # Solution: prepend a string to the port.
      
      sortedCbo = sorted(cbObj,key =lambda dummy: dummy.port)

      # statemachine vectors between 1: function definition+if, 2: elif(s), and 3: else+return
      first_f = True        
      last_port = None
      mbuf = []
      retlist = []
      ii = 0
      
      while (ii < len(sortedCbo)):
        if (sortedCbo[ii].disable):  # skip generating code for disabled ports
          ii = ii + 1
          continue
        if (sortedCbo[ii].port != last_port):   # restart for each unique port
          last_port = sortedCbo[ii].port   
          first_f = True
        if (first_f): 
          # 
          # Embedded Callbacks
          #
          # Note: The callback function for the port listen thread generates
          #       a list of expected messages to permit detection of mis-directed messages.
          #       Since this list is constant at compile time, it would make sense to 
          #       create the variable in 'self' once and only once rather than rebuild 
          #       the list on each call. 
          #   
          tbuf = "    def port%sCallback(self,msg):"   % (sortedCbo[ii].port); mbuf += [tbuf]
          
          tbuf = "      thisFcn = \'port%sCallback\'" % (sortedCbo[ii].port) ; mbuf += [tbuf]
          tbuf = "      err_f = False"                                       ; mbuf += [tbuf]
          tbuf = "      expctd = []"                                         ; mbuf += [tbuf]
          jj = 0
          while (jj<len(sortedCbo)):
            tbuf = "      expctd.append(\"%s\")"  % (sortedCbo[jj].format) ; mbuf += [tbuf]
            jj = jj +1 
          #
          # The delimiter key may be appended with json data and looks like this:
          #
          # <event_class.event>:<event_data_as_json_string>
          #
          # match the key (up to the ':' separator), then extract the json data
          #
          # Note: rabbitmq/zeromq differences 
          #       rabbitmq messages are objects with metadata and data components
          #       zeromq messages are strictly strings
          #
          first_f = False
        if (ii + 1) == len(sortedCbo) or (sortedCbo[ii+1].port != last_port):
          tbuf="      evData = None"                                    ; mbuf += [tbuf]
          tbuf="      if (isInlist(expctd,\'JsonData\')):"              ; mbuf += [tbuf]
          tbuf="        eidx = msg.find(\':\')"                         ; mbuf += [tbuf]
          tbuf="        if (eidx <0):"                                  ; mbuf += [tbuf]  # no data
          tbuf="          eidx = len(msg)"                              ; mbuf += [tbuf]
          tbuf="        else:"                                          ; mbuf += [tbuf]
          tbuf="          dataStr=msg[msg.find(\':\')+1:]"              ; mbuf += [tbuf]
          tbuf="          evData = jsonpickle.decode(dataStr)"          ; mbuf += [tbuf]
          tbuf="        evStr = msg[0:eidx]"                            ; mbuf += [tbuf]
          tbuf="        evid = EventObject.EventToId(self.evo,evStr)"   ; mbuf += [tbuf]
          tbuf="        if (evid >0):"                                  ; mbuf += [tbuf]
          tbuf="          self.sendEvent(evid,evData,True)"             ; mbuf += [tbuf]
          tbuf="          if (self.spe.count(evid)<=0):"                ; mbuf += [tbuf]
          tbuf="             print \"msg->event:\",msg"                 ; mbuf += [tbuf]
          tbuf="        else:"                                          ; mbuf += [tbuf]
          tbuf="          emsg = \"%s: %s is not an event\" % (thisFcn,evStr)" ; mbuf += [tbuf] 
          tbuf="          err_f = True"                                 ; mbuf += [tbuf]
          tbuf="      elif (isInlist(expctd,\'YamlData\')):"            ; mbuf += [tbuf]
          tbuf="        dataStr=\'\'"                                   ; mbuf += [tbuf]
          tbuf="        eidx = msg.find(\':\')"                         ; mbuf += [tbuf]
          tbuf="        if (eidx <0):"                                  ; mbuf += [tbuf]  # no data
          tbuf="          eidx = len(msg)"                              ; mbuf += [tbuf]
          tbuf="        else:"                                          ; mbuf += [tbuf]
          tbuf="          dataStr=msg[msg.find(\':\')+1:]"              ; mbuf += [tbuf]
          tbuf="        evStr = msg[0:eidx]"                            ; mbuf += [tbuf]
          tbuf="        evData=\'\'"                                    ; mbuf += [tbuf]
          tbuf="        if (len(dataStr)>0):"                           ; mbuf += [tbuf]
          tbuf="          msg_unw=self.serializer.fromSerial(dataStr)"     ; mbuf += [tbuf]
          tbuf="          evData = msg_unw"                             ; mbuf += [tbuf]
          tbuf="        evid = EventObject.EventToId(self.evo,evStr)"   ; mbuf += [tbuf]
          tbuf="        if (evid >0):"                                  ; mbuf += [tbuf]
          tbuf="          self.sendEvent(evid,evData,True)"             ; mbuf += [tbuf]
          tbuf="          if (self.spe.count(evid)<=0):"                ; mbuf += [tbuf]
          tbuf="             print \"msg->event:\",msg"                 ; mbuf += [tbuf]
          tbuf="        else:"                                          ; mbuf += [tbuf]
          tbuf="          emsg = \"%s: %s is not an event\" % (thisFcn,evStr)" ; mbuf += [tbuf] 
          tbuf="          err_f = True"                                 ; mbuf += [tbuf]
          tbuf="      elif (isInlist(expctd,msg) or isInlist(expctd,\'AnyEvent\')):" ; mbuf += [tbuf]
          tbuf="        evid = EventObject.EventToId(self.evo,msg)"     ; mbuf += [tbuf]
          tbuf="        if (evid>0):"                                   ; mbuf += [tbuf]
          tbuf="          self.sendEvent(eid,None,True)"                ; mbuf += [tbuf]
          tbuf="          if (self.spe.count(evid)<=0):"                ; mbuf += [tbuf]
          tbuf="             print \"msg->event:\",msg"                 ; mbuf += [tbuf]
          tbuf="        else:"                                          ; mbuf += [tbuf]
          tbuf="          emsg = \"%s: %s is not an event\" % (thisFcn,msg)" ; mbuf += [tbuf] 
          tbuf="          err_f = True"                                 ; mbuf += [tbuf]   
          tbuf="      else:"                                            ; mbuf += [tbuf] 
          tbuf="        emsg = \"%s:Cannot decode header (rd,[exp]):(%s,%s)\"%(" ; mbuf += [tbuf] 
          tbuf="thisFcn,msg,expctd)"                               ; mbuf += [tbuf] 
          tbuf="        err_f = True"                                   ; mbuf += [tbuf]
          tbuf="      if (err_f):"                                      ; mbuf += [tbuf]
          tbuf="        if (self.txtlog!=None):"                        ; mbuf += [tbuf]
          tbuf="          self.txtlog.error(emsg)"                      ; mbuf += [tbuf]
          tbuf="        else:"                                          ; mbuf += [tbuf] 
          tbuf="          print emsg"                                   ; mbuf += [tbuf]    	
          #
          # build a list of ports and callbacks that can be input to the Subscribe method
          #
          port = sortedCbo[ii].port
          method = "Port_" + sortedCbo[ii].port + "_CB" 
          retlist = retlist + [[port, method]]   # list of two-element lists	
          first_f = True 
        ii = ii + 1
        
      # end while

      cbo = retlist

      # -------------- subscribe method (obsolete) ------------------

      # Obsolete - patch found to allow Threads and Gevents to coexist
      # for each input port:
      #   create an array of Get_onepass(0.1) calls 
      #   create an array of callback calls
      # call Get, no-timeout, pass in the arrays
      """
      tbuf =   "    def subscribe(self):" ; mbuf += [tbuf] 
      if (len(cbo)==0):
        tbuf = "      pass"               ; mbuf += [tbuf] 
      else:
        ii =0
        tbuf="      nbget = []"           ; mbuf += [tbuf]
        tbuf="      getcb = []"           ; mbufsubscribe += [tbuf]
        while (ii<len(cbo)):
          tbuf="      nbget=nbget+[self.comm[%d].Get_onepass]"%(sortedCbo[ii].index)
          mbuf += [tbuf]
          tbuf="      getcb=getcb+[self.port%sCallback]"%(sortedCbo[ii].port)
          mbuf += [tbuf]
          ii += 1
        #end while
        #
        # This next piece of code is a hack because Get() is an endless loop that
        # never returns - so how can Get listen on multiple ports?
        # The solution is to send an list of non-blocking mini/timeout gets
        # to a master Get() having a while loop that runs through the list. 
        # The genius/hack part is - any Get() can be the master Get() because the 
        # Get() context is in the passed-in list, not in the initial Get() call.
        #
        ii = 0
        match_f = False           # find the first valid Get
        while ii < len(pdo):
          if (SCBU.isInlist(cmo.inputSocketTypes(),pdo[ii].type)):
            match_f = True 
            break
          ii += 1
        # end while
        if (match_f):
          tbuf="      self.comm[%d].Get(wait_sec=0,nblist=nbget,callback=getcb)"%ii ; mbuf += [tbuf]
      # end else something to subscribe to
      """
      # -------------- subscribe method ------------------
      #
      #   1. if port type is subscribe then subscribe 
      #   2. call ThreadedGet/GeventGet with callback
      #
      tbuf =      "    def subscribe(self):" ; mbuf += [tbuf] 
      if (len(cbo)==0):
        tbuf =    "      pass"               ; mbuf += [tbuf] 
      else:
        ii = 0   # port indexer
        jj = 0   # callback indexer  
        kk = 0 # enabled indexer     
        while (ii<len(pdo)):
          #
          # if should be listened to AND not disabled
          #   (where disabled signifies distributed process / not local listener)
          #   then add the call to instantiate listen in a thread with callback
          #
          if (pdo[ii].disable):
            ii = ii + 1
            continue
          #print "ii=",ii,"kk=",kk
          if SCBU.isInlist(cmo.inputSocketTypes(),pdo[ii].type):
             if (pdo[ii].type=="subscribe"):
               tbuf="      print \"%s\","%(pdo[ii].name) ; mbuf += [tbuf]
               tbuf="      self.comm[%d].Subscribe(\"%s\")"%(kk,pdo[ii].events) ; mbuf += [tbuf]
             tbuf="      self.comm[%d].GeventGet(0,[self.port%sCallback])"%(
                 (kk,pdo[ii].port)) ; mbuf += [tbuf]
             jj = jj + 1
          kk = kk + 1
          ii = ii + 1
        #end while  

      # ------------- print/write to file ----------------------
      
      if (self.iniPrint):                # print code to display
        ii = 0
        while (ii < len(mbuf)):         
           print mbuf[ii]
           ii = ii + 1 
                                      # generate python code
      if (self.iniGenCode):				  
        ii = 0
        while (ii < len(mbuf)):         
           wfp.write( mbuf[ii] + "\n") 
           ii = ii + 1
      
      return retlist
      
    #end commsCallbacksZmq
    
    #---------------------------------------------
    # listEvents
    #     purpose: list the events found in the design file
    #
    def listEvents(self):
      #
      # search for statename in transitions
      # print as tuple [index,state,parent,type]
      
      ii = 0  
      while ii < len(self.evo):   
        print "event_set %s: %d events" % (self.evo[ii].name, len(self.evo[ii].events))
        jj = 0
        event_set = self.evo[ii]
        while (jj<len(event_set.events)):
          print "%d: %s:%d"%(jj + 1,event_set.events[jj],event_set.ids[jj])
      
          jj = jj +1
      
        #end inner loop
        
        ii = ii + 1
      
      #end outer loop
      
    #end listEvents
    
    #---------------------------------------------
    # listStates
    #     purpose: list the states found in the design file
    #
    def listStates(self,handle=None,active=None):  
      #
      # search for statename in transitions
      # print as tuple [index,state,parent,type]
      
      print "(Index, State, Parent, Type, Active)"
      ii = 0
      while ii < len(self.states):
        if (self.states[ii].disable):   # skip disabled
          ii = ii + 1
          continue
        #
        # this next line took a long time to figure out
        #  
        if (handle!=None):
          cmd = "%s.statechart.runtime.is_active(%s.statechart.%s)" % (handle,handle,self.states[ii].name)
        else:
          cmd = "self.scobj.statechart.runtime.is_active(self.scobj.statechart.%s)"%(self.states[ii].name)
        is_active = eval(cmd)
        if ((active == None) or  ((active ==True) and is_active) or ((active ==False) and (not is_active)) ):
          buf2 = "[%d, %s, %s, %s, %s]" % (ii+1, self.states[ii].name, self.states[ii].parent,
                                         self.states[ii].type, is_active)
            
          print buf2
          
        ii = ii +1
      
      #end while
      
    #end listStates 
    
    #---------------------------------------------
    # isStateActive
    #           purpose: return True if state is active
    #
    def isStateActive(self,handle,     # instantiation of statechart
                      stateName): # state name
            
      # coded this way because statechart is generated on-the-fly from the design file
      # and has an on-the-fly instantiation and state
      #
      cmd = "%s.statechart.runtime.is_active(%s.statechart.%s)" % (handle,handle,stateName)
      
      is_active = eval(cmd)
      
      return is_active
        
    #end isStateActive 
      
    #---------------------------------------------
    # listTransitions
    #                purpose: list the transitions associated with the design file
    #
    def listTransitions(self,stateName):   # state name
      
      # search for statename in transitions
      # print as tuple [index,start,end,event]
      
      print "(Index, Start, End, Event)"
      ii = 0
      while ii < len(self.xitions):
        if (not self.xitions[ii].disable):
          if (self.xitions[ii].startState == stateName) or (self.xitions[ii].endState == stateName):  
            buf = "[%d,%s,%s,%s]" % (ii+1,self.xitions[ii].startState,self.xitions[ii].endState,self.xitions[ii].event)
            print buf
          #end if  
        #end if
        ii = ii +1
      
      #end while
      
    #end listTransitions  

    #
    #-------------------------------------------------------------
    # 
    #
    def commsParamsRmq(self,wfp):
      # simple transfer, not a list of objects 
      mbuf = []
      tbuf = "        self.pio = %s" % self.pio.list         ; mbuf += [tbuf]
      #
      # The design ini file leads directly to the embedded pystatechart code
      # but not the comms parameters, which need to be transfered
      # piece by piece into the object, decoupling scb.py to <unique_design>.py
      #
      tbuf = "        self.pco = []"              ; mbuf += [tbuf]
      ii = 0
      while ii < len(self.pco):
        tbuf = "        self.pco=self.pco+\
    [PortConfigObject(channel_id=\"%s\",exchange=\"%s\",type=\"%s\",queue=\"%s\",msg_tag=\"%s\")]" % (
                          self.pco[ii].channel_id,
                          self.pco[ii].exchange,
                          self.pco[ii].type,
                          self.pco[ii].queue,
                          self.pco[ii].msg_tag)        ;  mbuf += [tbuf]                       
        ii = ii +1
      # end while
      tbuf = "        self.pdo = []"              ; mbuf += [tbuf]
      ii = 0   # list iterator
      while ii < len(self.pdo):
        if (self.pdo[ii].disable):  # only collect enabled ports
          ii = ii + 1
          continue
        tbuf = "        self.pdo = self.pdo +\
    [PortDataObject(name=\"%s\",type=\"%s\",port=\"%s\",event_id=\"%s\")]" % (
                          self.pdo[ii].name,
                          self.pdo[ii].type,
                          self.pdo[ii].port,
                          self.pdo[ii].event_id)      ; mbuf += [tbuf]                      
        ii = ii + 1     
      # end while

      #    
      # NOTE: string elaborations all need quotes
      #
      tbuf = "        self.comm = %s.CommObject(host=\'%s\',userid=\'%s\',password=\'%s\')" % (self.pio.import_name,
                            self.pio.host,  self.pio.userid, self.pio.password)           ;  mbuf += [tbuf]
      tbuf = "        self.comm.ConfigureList(%s)" % (SCBO.NamedObject.combineLists(self.pco)) ;  mbuf += [tbuf]      
           
      # -------------- print and generate comms code from buffers -----------------
             	       
      if (self.iniPrint and (self.pio != None)):  # print python comms code to display
        ii = 0
        while (ii < len(mbuf)):         
           print mbuf[ii]
           ii = ii + 1 	 
                 
      if (self.iniGenCode and (self.pio != None)):      # generate python comms code
        ii = 0
        while (ii < len(mbuf)):         
           wfp.write( mbuf[ii] + "\n") 
           ii = ii + 1
    # end commsParamsRmq 
    #-------------------------------------------------------------
    # 
    #
    def commsParamsZmq(self,wfp):
      #
      # The design ini file leads directly to the embedded pystatechart code
      # but not the comms parameters for initializing the comm object, which 
      # need to be transfered piece by piece into the object.
      # This permits decoupling scb.py from our statechart: <unique_statechart>.py
      #
      # simple transfer, not a list of objects 
      #
      mbuf = []
      tbuf = "        self.pio = %s" % self.pio.list   ; mbuf += [tbuf]  # port init
      tbuf = "        self.pco = []"                   ; mbuf += [tbuf]  # port config (rmq only)
      tbuf = "        self.pdo = []"                   ; mbuf += [tbuf]  # port definition
      ii = 0  # list iterator
      while ii < len(self.pdo): 
        if (self.pdo[ii].disable):  # skip disabled (distributed) ports
          ii = ii + 1
          continue
        tbuf = "        self.pdo = self.pdo +\
    [PortDataObject(host=\"%s\",port=\"%s\",name=\"%s\",type=\"%s\",format=\"%s\",events=\"%s\")]" % (
                          self.pdo[ii].host,    # ip address
                          self.pdo[ii].port,    # ip port
                          self.pdo[ii].name,    # label
                          self.pdo[ii].type,    # push, pull, etc.
                          self.pdo[ii].format,  # dataformat, json, yaml
                          self.pdo[ii].events)      ; mbuf += [tbuf]     
        ii = ii + 1 
      # end while
      
      # NOTE 1: This is the comms object initialization call
      # NOTE 2: embedded string elaboration of parameters need quotes
      #         its a double indirect kind of thing
      #
      tbuf = "        self.comm = []"             ; mbuf += [tbuf]
      
      ii = 0  # in list iterator
      while ii < len(self.pdo): 
        if (self.pdo[ii].disable):  # skip disabled (distributed) ports
          ii = ii + 1
          continue
        tbuf = "        self.comm = self.comm +\
    [%s.CommObject(host=\'%s\',port=\'%s\',sock_type=\'%s\')]" %  (self.pio.import_name,
                            self.pdo[ii].host, 
                            self.pdo[ii].port,
                            self.pdo[ii].type)   ;  mbuf += [tbuf]
        ii = ii + 1
      # end while

      # -------------- print and generate comms code from buffers -----------------
             	       
      if (self.iniPrint and (self.pio != None)):  # print python comms code to display
        ii = 0
        while (ii < len(mbuf)):         
           print mbuf[ii]
           ii = ii + 1 	 
                 
      if (self.iniGenCode and (self.pio != None)):      # generate python comms code
        ii = 0
        while (ii < len(mbuf)):         
           wfp.write( mbuf[ii] + "\n") 
           ii = ii + 1

    # end commsParamsZmq
    #
    #-------------------------------------------------------------
    # 
    def process_line(self,line):
      #
      # process_line uses "self" and "self.scobj" to enable shortcut commands
      # If the <context> of  <context>.command is missing,
      # this routine just might figure it out 
      #
      status = 0
      line = line.lstrip()         # strip leading whitespace
      params = line.split(" ")     # grab first word
      try:                             
        exec(line)                        # execute as python command
      except Exception as eobj:           # don't exit if command fails
        exceptionInfo(eobj)                     # add informaton  

      sys.stdout.flush()           # cleanup flush
      return status
    # end process_line
    #
    #-------------------------------------------------------------
    # 
    def user_loop(self):
      while 1:                   # loop forever, or until quit()
        print self.PROMPT,       # print prompt
        sys.stdout.flush()       # flush
        quit_f,line = myreadline()   # "special" readline works with gevents
        if quit_f:
          break       
        self.process_line(line)      # 'exec' the line
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
        params = sobj.value
        quit_f = params[0]
        line = params[1]
        if (not quit_f):
          if (line!=None):
            status = self.process_line(line)
            if (status>=0):
              print self.PROMPT,
              sys.stdout.flush()
            # endif ok
          # endif line data
        # endif not quit
        else:               # quit() detected
          status = -1      
      return status
    #end user_onepass
    #
    #-----------------------------------------------------------
    #
    def process_files(self):
    
      eflg = False          # error flag
      
      #
      # spelling of types matches pystatechart parameters
      #
      
      #
      # warnings are not fatal but
      # should be checked before continuing
      #
      self.warning_count = 0   
      
      # 
      # initialize globals
      #
      self.pio = None         # port input object
      self.pdo = None         # port data object
      self.pco = None         # port config object
      self.evo = None         # events object
      self.spe = None         # suppressed events
        
      #
      # there are two possibly forms of distributed message queues
      # the second form was only after the first was designed in
      # this snippet of code pre-loads the object definitions
      # which must be done in main's scope, outside of any method
      #
    
      # if design file given, then process
      # else print help
      #  
      if (len(self.des_file) >0):  # configParser doesn't raise error if file doesn't exist!
        if (not os.path.isfile(self.des_file)):
          print "*** Error: File %s does not exist ***" % (self.des_file)
          eflg = True
      else:
        print "statechart builder (scb) version %s" % self.VERSION
        print "for options, try: python scb.py -h"
        eflg = True
      
      if (not eflg):
        cp = ConfigParser.ConfigParser()
        try: 
          cp.read(self.des_file)               
        except Exception as eobj:
          print "*** ConfigParser exception:", eobj, " ***"
          eflg = True
        
      if (not eflg):
        eflg, self.pio, self.pco, self.pdo = self.get_ini_params(cp,self.des_file)  
         
      # enter code generation:
      
      """
         Design:     
           1. first code the imports
           2. next, code the event classes
           3. next, code the state and transition callbacks
           4. next, code the states
           5. next, code transitions
           6. next, code the user callbacks, read a callbacks "overwrite" file
           7. next, code the event handler thread
           8. last, code the statchart object 
           9. enter debug mode, provide a prompt for the user  
        """   
      
      if (eflg):   # error during reading or processing ini file
        print "exiting"
        try:
          quit()                     # unrecoverable
        except Exception as eobj:    # ignore complaining threads
          pass
      else:
      
        #------------------  code generation ---------------------
    
        
        wfp = None  # write file pointer 
        cfp = None  # callback file pointer
        if (self.iniGenCode):
            today = datetime.datetime.now()
            if (len(self.out_file) ==0):
    	      self.out_file = 'iStateChart.py'
    	  
    	#
    	# two files are written:
    	# 1) File that contains callbacks (which a user may add to)
    	# 2) The statemachine which calls the callbacks
    	#
    	
    	#
    	# An ini flag may be set to prevent the generation of callbacks
    	# from overwritting user generated code
    	#
    	base_name = re.sub(".py","",self.out_file)  
    	self.callbacks_file = base_name + "_cb.py"
        wfp = open(self.out_file,'w')
    	wfp.write('#\n')
    	wfp.write('# %s of %s on %s\n' %(self.out_file,self.des_file,today.ctime()))
    	wfp.write('#\n')
    	
        if (self.iniGenCallbacks):
    	  #
    	  # test to prevent accidental overwriting
    	  #
    	  file_exists = True
    	  try:
    	    cfp = open(self.callbacks_file,'r')
    	  except IOError:                          # file does not exist
    	     file_exists =False                    # safe to open write
             ok_overwrite_f =True
          else:
             cfp.close()                           # close 'r' for reopen 'w'       
          #
          # single linefeed used to distance next from previous messages
          #
          
    	  if (g_cb_file==None):                     # No input callbacks file
             print "\nNo callbacks file provided."  # place message in context
    	  if (file_exists == True):                 # overwrite warning
    	      msg = "%s will be overwritten, ok? (y,n,q) > " % self.callbacks_file
              print msg,
              sys.stdout.flush()
              quit_f,line = myreadline()            # get choice from user
    	      line = line.upper()
    	      line.strip()
              if (len(line)==0):                    # default is quit
                print "exiting"
    	        quit()
    	      if (line[0] == 'Y'):                  # Yes, overwrite
    	        ok_overwrite_f = True
    	      elif (line[0] == 'N'):                # No, don't overwrite
    	        ok_overwrite_f = False   
    	      else:                                 # quit
    	        print "exiting"
    	        quit() 
          if (ok_overwrite_f):
             print "Opening",self.callbacks_file,"for writing."
             cfp = open(self.callbacks_file,'w')
    	     cfp.write('#\n')
    	     cfp.write('# %s of %s on %s\n'%(self.callbacks_file,self.des_file,today.ctime()))
    	     cfp.write('#\n')	
    	
        #------------------ code imports ---------------------
       
        ii =0
        while (ii < len(self.py_init)): 
          init_buf = self.py_init[ii]
          if (self.iniPrint):  
            print(init_buf)
          if (self.iniGenCode):
            wfp.write(init_buf + '\n')
          ii = ii +1
          #end while
      
        #------------------  code event classes ---------------------
      
        counting_idx = 0            # used if no base
        for event_set in self.evo:
          
          evbuf = "class" + " " + event_set.name + ":\n"
          
          event_offset = int(event_set.base)
          
          ii = 0
          while (ii < len(event_set.events)):
            evline = "  %s = %d\n" % (event_set.events[ii],ii + event_offset)
            evbuf = evbuf + evline 
            ii = ii+1
          #  end while inner loop
             
          if (self.iniPrint):  
            print evbuf,   # comma is newline suppression
          if (self.iniGenCode):
            wfp.write(evbuf)      
          
        #end while outer loop
               
          
      
        #------------------ code state callbacks ------------------
        #
        # for each state entry, do, and exit
        # if method present, if unique create empty call with method as name
        # if list, add event calls after  method declaration
        #
        ulist = []   # unique list
      
        self.funcFromFile = None                       # this is an object used in replacing callbacks
        if (len(self.iniInsertCB) != 0):               # this is the name of the callbacks file
          self.iniInsertCB = self.iniInsertCB.strip()     # cleanup
          if (self.iniInsertCB == 'None') or (self.iniInsertCB == 'False'):  # indicates no file, not a filename
            self.iniInsertCB = None
          else:
            self.funcFromFile = SCBU.funcFromFile(self.iniInsertCB)
          
        
        #
        # entry
        #   
        stat, ulist = self.gen_code_hooks(self.pdo,self.evo,cfp,ulist,self.states,"entry")
        if (stat !=0):
           print "error in file: %s" % (self.des_file)  # error in ini file
           quit()
      
        #
        # do
        # 
        stat, ulist = self.gen_code_hooks(self.pdo,self.evo,cfp,ulist,self.states,"do")
        if (stat !=0):
           print "error in file: %s" % (self.des_file)  # error in ini file
           quit()
          
        #
        # exit
        #    
        stat, ulist = self.gen_code_hooks(self.pdo,self.evo,cfp,ulist,self.states,"exit")
        if (stat !=0):
           print "error in file: %s" % (self.des_file)  # error in ini file
           quit()
        
        #------------------ code transition callbacks ------------------  
        
        # 1. check for validity of events 
        # 2. calls for guard  
        # 3. calls for action, actions may be in list
         
        #
        # look for illegal conditions (event declarations) in transitions
        #
        ii = 0
        while (ii < len(self.xitions)):  
            if (not self.xitions[ii].disable) and (self.xitions[ii].event != 'None'):
              #
              # "Event(class_name.event_name,<optional_params>)"
              #
              phrase = self.xitions[ii].event      # index to event
              idx1 = phrase.find("Event(")        
              if (idx1 != -1):   # read until close parens or comma 
                print "*** Error: Event declarations not allowed in Transitions. %s ***" % phrase
                print "error in design file: %s" % self.des_file
                quit()
                            
              #end if event found
              
            #end if not None  
            
            ii = ii+1    # next transition
          
        #end while outer loop
       
        #
        # guards in transitions
        #
        stat, ulist = self.gen_code_hooks(self.pdo,self.evo,cfp,ulist,self.xitions,"guard")
        if (stat !=0):
           print "error in file: %s" % (self.des_file)  # error in ini file
           quit()
        #
        # transition action, can be used for generating debugging messages
        #  
        stat, ulist = self.gen_code_hooks(self.pdo,self.evo,cfp,ulist,self.xitions,"action",True)
        if (stat !=0):
           print "*** Error: Design file: %s ***" % (self.des_file)  # error in ini file
           quit()  
           
        if (self.funcFromFile != None):
          err_f, missingList = self.funcFromFile.findMissing()
          if (err_f):
            print "*** Error in file: %s, defined in file: %s ***" %(self.iniInsertCB,self.des_file)
            quit()
            
          if (missingList != []):
            self.warning_count += 1
            print "*** Warning: %d:  function(s):%s, in file:%s ***" %(self.warning_count, 
                                                                       missingList,
                                                                       self.iniInsertCB)
            print "not found in file:", self.des_file
            
           
        #------------------ insert user designed callbacks -------------
        
        if (self.iniGenCode):
        
          if cfp != None:  # close file
             cfp.write("# end of callbacks file\n")
             cfp.close()
    	 
          # callback file is subset
          # can't be imported, must be inserted to get proper context for "exec"
          
          cfp = open(self.callbacks_file,"r")        
          line = " "                     # loop initializer
          while (line != ""):
            line = cfp.readline()        # copy callbacks into statechart program
            wfp.write(line)   	
          cfp.close()	                 # close readfile
    
        #------------------ the statechart class ------------------- 
      
        # topmost class and states
      
        buf1 = "class %sStatechart(Statechart):" %(self.chart_name)
        buf2 = "  def __init__(self,param):"
        buf3 = "    Statechart.__init__(self,param)"
        
        if (self.iniPrint):
          print buf1
          print buf2
          print buf3
        if (self.iniGenCode):
          wfp.write(buf1 + "\n")
          wfp.write(buf2 + "\n")
          wfp.write(buf3 + "\n")
      
        # if state's parent is 'None', then code 'self'
      
        # -------------- statechart state declarations -----------------
      
        ii =0
        while (ii<len(self.states)):
          if (self.states[ii].disable):   # skip disabled
            ii = ii + 1
            continue
          state_set = self.states[ii]  # unpack ini list
          sname = state_set.name
          sparent = state_set.parent
          stype = state_set.type
          #
          # if any of the next are lists, then use first element
          #
          # entry, do, exit
          #
          sentry = state_set.entry
          if (sentry[0] == '['):
            sentry = enlist_string(sentry,1)  # remove syntactic sugar
            sentry = sentry[0]             # first element is method
          
          sdo = state_set.do
          if (sdo[0] == '['):
            sdo = enlist_string(sdo,1)  # remove syntactic sugar
            sdo = sdo[0]             # first element is method
          
          sexit = state_set.exit
          if (sexit[0] == '['):
            sexit = enlist_string(sexit,1)  # remove syntactic sugar
            sexit = sexit[0]             # first element is method
          
          if (sparent == 'None'):
            sparent = 'self'
          else:                        
            sparent = 'self.' + sparent    # make variable visible to debugger
               
          buf =  "    self.%s = %s(%s, %s, %s, %s)" % (sname,stype,sparent,sentry,sdo,sexit)                       
          if (self.iniPrint):
            print buf
          if (self.iniGenCode):
            wfp.write(buf + "\n")	
          
          ii = ii +1
        #end while
      
        # -------------- statechart transition declarations -----------------
          
        ii =0
        startUnique=0                # make startState objects unique
        startList =[]                # list of start states and  parents
        while (ii<len(self.xitions)):   # while there are transitions
        
          xition_set = self.xitions[ii]  # unpack the transition
          
          if (xition_set.disable==True):  # skip disabled transitions
            ii = ii + 1
            continue
            
          xstart = xition_set.startState
          xend   = xition_set.endState
          xevent = xition_set.event
            
          #
          # if any of the next are lists, then use first element
          #
          xguard = xition_set.guard
          if (xguard[0] == '['):
            xguard = enlist_string(xguard,1)  # remove syntactic sugar
            xguard = xguard[0]                # first element is method
      	
          xaction = xition_set.action
          if (xaction[0] == '['):
            xaction = enlist_string(xaction,1)  # remove syntactic sugar
            xaction = xaction[0]             # first element is method
            
          # if start state is "start" then find parent 
          # to generate start state to pass into transition
          # if end state is "end" then find parent to
          # generate end state to pass into transition
          # if parent is None then parent is "self"
          #
          # StartState and EndState are pseudo-states
          # Notes:
          #   1. Each concurrent or hierarchical state MUST have a 'start' transition
          #      else the statemachine.init() will fail with this error
          #      'NoneType' object has no attribute 'activate'
          #
          #   2. If two or more hierarchical states have same parent, those
          #      states cannot be started twice by declaring the startState twice  - 
          #      (statechart returns an error)
          #      but the 'start' state object itself can (has to) be reused
          #      in the transition call for each child.
          #
          #   3. Only one end state is allowed, and it must be a transition for the top state
          #   
          
          if (xstart == "start"):
            xstart = "startState%d" %startUnique       # arbitrary but consistent label change
            startUnique = startUnique +1 
            xparent,err = self.parent_state(xend)
            if (err<0):
              print "*** Error: in design file: %s, Parent of %s not found ***" % (self.des_file,xend)
              quit()	  
            if (xparent == "None"):
              xparent = "self"       # this is the tip-tippity topmost state
            else:
               xparent = "self." + xparent      
            #
            # check for previous start of parent
            # if not present, add to list
            # else, use the stateobject rather than make the stateobject
            #
            match_f = False
            skip_f = False
            match_f, startSet = SCBO.NamedObject.namedListMatch(startList,"parentState",xparent)
            if (match_f):
              xstart = startSet.startState   # use the previously used value
              skip_f = True                  # do not create a new start for xition
            else:                            # save in list to be tested against
              startList+=[SCBO.StartStateObject(startState=xstart,parentState=xparent)]
              
            if (not skip_f):
              buf1 = "    %s = StartState(%s)" % (xstart,xparent) 
              if (self.iniPrint):
                print buf1
              if (self.iniGenCode):
                wfp.write(buf1 + "\n")
          	   
          elif (xend == "end"):
            xend = "endState"        # arbitrary but consistent label change
            xparent,err = self.parent_state(xstart)
            if (err<0):
               print "*** Error: in design file: %s, Parent of %s not found ***" % (self.des_file,xstart)
               quit()
            if (xparent == "None"):
              xparent = "self"
            else:
              print "*** Error: in design file: %s ***" % (self.des_file)
              print "Only one end state is permitted. Parent: %s is not top state" % (xstart)
              quit()
            
            buf2 = "    %s = EndState(%s)" % (xend,xparent)
            if (self.iniPrint):
              print buf2
            if (self.iniGenCode):
              wfp.write(buf2 + "\n")
          #
          # startstate is not stored in self - no need for it.
          #       
          if (xstart[0:len("startState")] != "startState"):
            xstart = "self." + xstart
          if (xend != "endState"):	
            xend = "self." + xend
      	
          if (xevent != 'None'):
            #
            # check for keyword 'Event'
            # if found then leave phrase alone
            # else add synctactic sugar (i.e. 'Event(<class_name>.' to event
            #     
             
            comma_f = False  
            event_data =0   
            phrase = xevent      
        
          buf3 = "    Transition(%s, %s, %s, %s, %s)" % (xstart,xend,xevent,xguard,xaction)
          if (self.iniPrint):
            print buf3
          if (self.iniGenCode):
            wfp.write(buf3 + "\n")	
      	
          ii = ii+1
        #end while Transitions
           
        # -------------- begin statechart class -----------------
        #
        # Note 1. On shutdown: logger may not be present but if present then  
        #         shut logger down first because logger depends on statechart thread
        # 
        # Note 2. Port parameters evolved over time, for RMQ "event_id" may not always be  
        #         an event, it may also be a control code for formating event data 
        #         The newer ZMQ exchanged "event_id" for "format" and "events"
        #         "format" is used for data format control 
        #         "events" is used for the event class replacing a singular "event_id"
        # 
        
        # convert <rpc_client>.py to <rpc_client>
        #
        rpc_client = self.iniRpc.client[0:self.iniRpc.client.find(".")] 
        
        mbuf2 = []
        if ((self.iniRpc != None) and self.iniRpc.enable):
          tbuf = "import jsonrpc"                                   ; mbuf2 += [tbuf]
          tbuf = "import %s"%(rpc_client)                           ; mbuf2 += [tbuf]
          tbuf = "proxy = %s.%s()"%(rpc_client,rpc_client)          ; mbuf2 += [tbuf]
        if (self.pio != None):     
          tbuf = "import jsonpickle"                                ; mbuf2 += [tbuf]
          pdo_f, pdo_info = SCBO.NamedObject.namedListMatch(list_of_lists=self.pdo,
                                                    name="format",
                                                    value ="YamlData")
          if (pdo_f):
            try:
               import DynamicObject
            except Exception as eobj:
               print "Exception:",eobj
               quit()
               #
               # two possible problems: 
               #   1. DynamicObject and dependencies not found.
               #      These are: PrecisionTime, OrderedYaml, Lookup.py, DynamicYAML
               #   2. python2.6 doesn't support 'OrderedDict'
               #
            else:
              tbuf = "import DynamicObject"                                ; mbuf2 += [tbuf] # yaml
              tbuf = "import Serializer"                                   ; mbuf2 += [tbuf] # yaml
          
        tbuf = "class ExceptionString(Exception):"                     ; mbuf2 += [tbuf]
        tbuf = "    def __str__(self):"                                ; mbuf2 += [tbuf]
        tbuf = "        return repr(self.args[0])"                     ; mbuf2 += [tbuf]
        tbuf = "class %s(object):" %(self.chart_name)                  ; mbuf2 += [tbuf]  
        tbuf = "    def sendEvent(self,event_id,event_data=None,local_f=False):" ; mbuf2 += [tbuf]
        tbuf = "      err_f=False"                                           ; mbuf2 += [tbuf]
        tbuf = "      m_f, evStr = EventObject.idToEvent(self.evo,event_id)" ; mbuf2 += [tbuf]
        tbuf = "      if (not m_f):"                                         ; mbuf2 += [tbuf]   
        tbuf = "        emsg = \'*** Error: sendEvent ***\\n\'"              ; mbuf2 += [tbuf]
        tbuf = "        emsg = emsg + \'%d: unrecognized event\'%(event_id)" ; mbuf2 += [tbuf]
        tbuf = "        err_f=True"                                          ; mbuf2 += [tbuf]
        tbuf = "      if (not err_f):"                                       ; mbuf2 += [tbuf]
        tbuf = "        event_class = evStr[0:evStr.find('.')]"              ; mbuf2 += [tbuf]
        # Does the the port 'events' field match the event class?
        tbuf = "        port_f, port_info = PortDataObject.namedListMatch(list_of_lists=self.pdo,\
name=\'events\',value =event_class)"                         ; mbuf2 += [tbuf]
        #
        # extra status for debug
        #
        #tbuf = "        print \"port_f=\",port_f,\"event_class=\",event_class" ; mbuf2 += [tbuf]
        
        # local_f prevents sendEvent loop of death via callback
        tbuf = "        if (port_f and (not local_f)):"                 ; mbuf2 += [tbuf]      
        tbuf = "          self.sendEventAsMsg(port_info.name,event_id,event_data)" ; mbuf2 += [tbuf]
        tbuf = "        else:"                                          ; mbuf2 += [tbuf]
        tbuf = "          self.lock.acquire()"                          ; mbuf2 += [tbuf]
        tbuf = "          event = Event(event_id, event_data)"          ; mbuf2 += [tbuf]
        tbuf = "          self.events.append(event)"                    ; mbuf2 += [tbuf]
        tbuf = "          self.lock.release()"                          ; mbuf2 += [tbuf]
       
        tbuf = "    def shutdown(self):"                               ; mbuf2 += [tbuf]
        tbuf = "        if (self.txtlog != None): "                    ; mbuf2 += [tbuf]
        tbuf = "          self.txtlog.info(\'shutting down logger\')" ;mbuf2 += [tbuf]
        tbuf = "          time.sleep(1)"                      ; mbuf2 += [tbuf]
        tbuf = "          self.txtlog.shutdown()"                      ; mbuf2 += [tbuf]
        tbuf = "        print \"Shutting down statechart thread...\""  ; mbuf2 += [tbuf]
        tbuf = "        self.thread.shutdown()"                        ; mbuf2 += [tbuf]      

        tbuf = "    def PrintErr(self,caller,emsg):"                   ; mbuf2 += [tbuf]
        tbuf = "        omsg=\'[\'+caller+\']: \'+emsg"                  ; mbuf2 += [tbuf]
        tbuf = "        if (self.txtlog != None): "                    ; mbuf2 += [tbuf]
        tbuf = "           self.txtlog.error(omsg)"                    ; mbuf2 += [tbuf]
        tbuf = "        else:"                                         ; mbuf2 += [tbuf] 
        tbuf = "           print omsg"                                 ; mbuf2 += [tbuf]
        tbuf = "           sys.stdout.flush()"                         ; mbuf2 += [tbuf]

        tbuf = "    def PrintInfo(self,caller,emsg,eid=None):"         ; mbuf2 += [tbuf]
        tbuf = "        print_f = True"                                ; mbuf2 += [tbuf]
        tbuf = "        if (eid!=None):"                               ; mbuf2 += [tbuf]
        tbuf = "          if (self.spe.count(eid)>0):"                 ; mbuf2 += [tbuf]  
        tbuf = "            print_f = False"                           ; mbuf2 += [tbuf] 
        tbuf = "        if (print_f):"                                 ; mbuf2 += [tbuf] 
        tbuf = "          omsg=\'[\'+caller+\']: \'+emsg"              ; mbuf2 += [tbuf]
        tbuf = "          if (self.txtlog != None): "                  ; mbuf2 += [tbuf]
        tbuf = "            self.txtlog.info(omsg)"                    ; mbuf2 += [tbuf]
        tbuf = "          else:"                                       ; mbuf2 += [tbuf]  
        tbuf = "            print omsg"                                ; mbuf2 += [tbuf]
        tbuf = "            sys.stdout.flush()"                        ; mbuf2 += [tbuf]
       
          
        if (self.pio != None):
          tbuf = "    def sendEventAsMsg(self,port_name,event_id,event_data=None):"; mbuf2 += [tbuf]
          tbuf = "       caller = \'sendEventAsMsg\'"                              ; mbuf2 += [tbuf]
          tbuf = "       err_f,clist,plist=PortObject.getPortOutParams("           ; mbuf2 += [tbuf]
          tbuf = "self.pco,self.pdo,port_name)"                                    ; mbuf2 += [tbuf]
          tbuf = "       if (not err_f):"                                          ; mbuf2 += [tbuf]
          tbuf = "          m_f, evStr = EventObject.idToEvent(self.evo,event_id)" ; mbuf2 += [tbuf]
          tbuf = "          if (not m_f):"                                         ; mbuf2 += [tbuf]
          tbuf = "            emsg=\'unrecognized event=%d\'%(event_id)"           ; mbuf2 += [tbuf]
          tbuf = "            self.PrintErr(caller,emsg)"                          ; mbuf2 += [tbuf]
          tbuf = "            err_f=True"                                   ; mbuf2 += [tbuf]
          tbuf = "       if (not err_f):"                                   ; mbuf2 += [tbuf]          
          if (RMQ):
            tbuf="          if (plist.event_id==\'AnyEvent\')or(plist.event_id==evStr):" ; mbuf2 += [tbuf]
            tbuf="            err_f = self.comm.Put(evStr,plist.port,clist.msg_tag)"     ; mbuf2 += [tbuf]
          else:
            tbuf="          if ((plist[0].format==\'AnyEvent\')or"          ; mbuf2 += [tbuf]
            tbuf="             (plist[0].format==evStr)):"                  ; mbuf2 += [tbuf]           
            tbuf="            err_f = self.comm[clist[0]].Put(evStr)"       ; mbuf2 += [tbuf]
          if (RMQ):
            tbuf="          elif (plist.event_id==\'JsonData\'):"           ; mbuf2 += [tbuf]
          else:
            tbuf="          elif (plist[0].format==\'JsonData\'):"          ; mbuf2 += [tbuf]
          tbuf = "            dataStr=\'\'"                                 ; mbuf2 += [tbuf]
          tbuf = "            if (event_data!=None):"                       ; mbuf2 += [tbuf]
          tbuf = "              try:"                                       ; mbuf2 += [tbuf]
          tbuf = "                dataStr = jsonpickle.encode(event_data)"         ; mbuf2 += [tbuf]
          tbuf = "              except Exception as eobj:"                  ; mbuf2 += [tbuf]
          tbuf = "                emsg = ExceptionString(eobj)"             ; mbuf2 += [tbuf] 
          tbuf = "                emsg = str(emsg)"                         ; mbuf2 += [tbuf] 
          tbuf = "                self.PrintErr(caller,\'Exception:\'+emsg)" ; mbuf2 += [tbuf]
          tbuf = "                err_f = True"                             ; mbuf2 += [tbuf]
          tbuf = "              else:"                                      ; mbuf2 += [tbuf]
          tbuf = "                evStr = evStr+\':\'+dataStr"              ; mbuf2 += [tbuf]
          tbuf = "            if (not err_f):"                              ; mbuf2 += [tbuf]
          if (RMQ): 
            tbuf="              err_f = self.comm.Put(evStr,plist.port,clist.msg_tag)"; mbuf2+=[tbuf]
          else:
            tbuf="              err_f = self.comm[clist[0]].Put(evStr)"     ; mbuf2 += [tbuf] 
          if (not RMQ):
            tbuf="          elif (plist[0].format==\'YamlData\'):"          ; mbuf2 += [tbuf]
            tbuf="            dataStr=\'\'"                                 ; mbuf2 += [tbuf]
            tbuf="            if (event_data!=None):"                       ; mbuf2 += [tbuf]
            tbuf="              serializer = \"yaml\""                             ; mbuf2 += [tbuf]
            tbuf="              if isinstance(serializer, Serializer.Serializer):" ; mbuf2 += [tbuf]
            tbuf="                self.serializer = serializer"                           ; mbuf2 += [tbuf]
            tbuf="                self.serial_type = Serializer.serial_types[serializer]" ; mbuf2 += [tbuf]
            tbuf="              else:"                                                    ; mbuf2 += [tbuf]
            tbuf="                self.serial_type = serializer"                          ; mbuf2 += [tbuf]
            tbuf="                self.serializer = Serializer.serializers[serializer]()" ; mbuf2 += [tbuf]
            tbuf="              dataStr = self.serializer.toSerial(event_data)" ; mbuf2 += [tbuf]
            tbuf="              evStr = evStr+\':\'+dataStr"                ; mbuf2 += [tbuf]
            tbuf="            err_f = self.comm[clist[0]].Put(evStr)"       ; mbuf2 += [tbuf]  
          tbuf = "          else:"                                          ; mbuf2 += [tbuf]
          tbuf = "            emsg = \"no conversion.%s,%s: (rd,[exp]):(%s,%s)\" %(" ; mbuf2 += [tbuf] 
          tbuf = "port_name,evStr,plist[0].format,"                         ; mbuf2 += [tbuf] 
          tbuf = "CommonPortObject.getPortEventValidIDs())"                 ; mbuf2 += [tbuf] 
          tbuf = "            self.PrintErr(caller,emsg)"                   ; mbuf2 += [tbuf]
          tbuf = "            err_f=True"                                   ; mbuf2 += [tbuf]
          tbuf = "       if (not err_f):"                                   ; mbuf2 += [tbuf]
          tbuf = "         lmsg=\'(port,msg)=(%s,%s)\'%(port_name,evStr)"   ; mbuf2 += [tbuf]
          tbuf = "         self.PrintInfo(caller,lmsg,event_id)"            ; mbuf2 += [tbuf]
          tbuf = "       return err_f"                                      ; mbuf2 += [tbuf]   
        
          tbuf = "    def getMsgSendEvent(self,port_name):"                 ; mbuf2 += [tbuf]
          tbuf = "       err_f, event_f = PortObject.getMsgSendEvent(self,\
    port_name, self.evo[0],self.pco, self.pdo)"                             ; mbuf2 += [tbuf]
          tbuf = "       return err_f, event_f"                             ; mbuf2 += [tbuf] 
        
        # -------------- print and generate code from buffers -----------------
                     
        if (self.iniPrint):                # print code to display
          ii = 0
          while (ii < len(mbuf2)):         
             print mbuf2[ii]
             ii = ii + 1 
    	       
        if (self.iniGenCode):              # generate python code
          ii = 0
          while (ii < len(mbuf2)):         
             wfp.write( mbuf2[ii] + "\n") 
    	     ii = ii + 1 
        
        # -------------- comms callbacks for subscribe ------------------
        
        g_cbo = None
        if (self.pio != None):
          if (RMQ):
            g_cbo=self.commsCallbacksRmq(self.pdo,      # port data object
                                         self.evo,      # event object
                                         wfp)        # file print object 
          else:
            g_cbo=self.commsCallbacksZmq(self.pdo,      # port data object
                                         self.evo,      # event object
                                         wfp)
                                   
 
        # ------------------------------------------------------------
        # ---------------------    __init__       --------------------
        # ------------------------------------------------------------
        
        mbuf3 = []
        tbuf =     "    def __init__(self):"            ; mbuf3 = mbuf3 + [tbuf]
          
        # -------------- event object -----------------
         
        tbuf =     "        self.evo = []"              ; mbuf3 = mbuf3 + [tbuf]
        ii = 0
        while ii < len(self.evo):
            tbuf = "        self.evo = self.evo +[EventObject(file=\"%s\",name=\"%s\",events=%s,ids=%s)]" % (
                              self.evo[ii].file,
                              self.evo[ii].name,
                              self.evo[ii].events,
                              self.evo[ii].ids)         ; mbuf3 = mbuf3 + [tbuf]                       
            ii = ii +1  
        
        # -------------- suppressed printing events -----------------
         
        tbuf = "        self.spe = []"                  ; mbuf3 = mbuf3 + [tbuf]
        if (self.spe != None):
          ii = 0
          while ii < len(self.spe):
            tbuf = "        self.spe = self.spe +[%s]" % (self.spe[ii]) ; mbuf3 = mbuf3 + [tbuf]
            ii = ii +1                     
      
        # -------------- print and generate code from buffers -----------------
        
      	       
        if (self.iniPrint):  # print python code to display
          ii = 0
          while (ii < len(mbuf3)):         
             print mbuf3[ii]
             ii = ii + 1 	 
                 
        if (self.iniGenCode):      # generate python code
          ii = 0
          while (ii < len(mbuf3)):         
             wfp.write( mbuf3[ii] + "\n") 
             ii = ii + 1
        
        # ---------------------    comms params in __init__    --------------------
     
        if (self.pio != None):
          if (RMQ):
            self.commsParamsRmq(wfp)
          else:
            self.commsParamsZmq(wfp)
        
       # -------------- statechart and thread are dependent on event object -----------------
        
        mbuf4 = [] 
        tbuf = "        self.events = list()"                 ; mbuf4 += [tbuf]
        tbuf = "        self.lock = Lock()"                   ; mbuf4 += [tbuf]
        tbuf = "        self.txtlog = None"                   ; mbuf4 += [tbuf]
        for event_set in self.evo:
          tbuf="        self.%s = %s" %(event_set.name,event_set.name); mbuf4 += [tbuf]
        tbuf = "        self.statechart = %sStatechart(self)" % (self.chart_name) ; mbuf4 += [tbuf]
        tbuf = "        self.statechart.start()"              ; mbuf4 += [tbuf]
        if (RMQ):
          tbuf="        self.thread = StatechartThread(self)" ; mbuf4 += [tbuf]
          tbuf="        self.thread.start()"                  ; mbuf4 += [tbuf]
        else:
          tbuf="        self.thread = StatechartNoThread(self)" ; mbuf4 += [tbuf]
          #
          # Not a thread but a polling loop, can't be immediately started after instantiation
          # not all pieces are present yet:
          #   The communication object after instantiation needs the not-a-thread object  
          #   inside it for the blocking Get() to call the statechart while waiting
          #
          if (self.pio != None): # if ports 
            ii = 0               #   init pdo iterator
            jj = 0               #   init statechart comms interface iterator
            while ii < len(self.pdo):
              if (not self.pdo[ii].disable):  # for distribution
                tbuf="        self.comm[%d].Sc_if(interface=self.thread)"%jj ; mbuf4 += [tbuf]
                jj = jj + 1
              ii = ii +1      

        # -------------- print and generate code from buffers -----------------
        
      	       
        if (self.iniPrint):  # print python code to display
          ii = 0
          while (ii < len(mbuf4)):         
             print mbuf4[ii]
             ii = ii + 1 	 
                 
        if (self.iniGenCode):      # generate python code
          ii = 0
          while (ii < len(mbuf4)):         
             wfp.write( mbuf4[ii] + "\n") 
             ii = ii + 1    
          # end while
          wfp.close()                   # done, close file 

        # --------------      generate startup program      -----------------

        if (self.iniGenCode):      # generate startup program (only needs to be done once)
          startup_name = self.chart_name+"_startup.py"
          file_exists = True
    	  try:
    	    sfp = open(startup_name,'r')       # open read
    	  except IOError:                      # file does not exist
    	     file_exists =False                # safe to open write
          else:
             sfp.close()                       # close file "r" to reopen "w"
          if not file_exists:                  # create startup program                      
            try:
    	       sfp = open(startup_name,'w')      
            except IOError:
               self.warning_count += 1
               errm = "*** Warning: %d: cannot open startup file: %s ***",startup_name
            else:
               bn = self.chart_name # base name
               sfp.write("import user_onepass\n")
               sfp.write("import %s\n"%bn)
               sfp.write("%sObj = %s.%s()\n"%(bn,bn,bn))
               sfp.write("uh = user_onepass.user_hook(\"dbg> \",%sObj)\n"%bn)
               sfp.write("%sObj.thread.dbg_interface(uh)\n"%bn)
               sfp.write("%sObj.thread.start()\n"%bn)
               sfp.close()
	 	 	         
    # end process_files
    #
    #-----------------------------------------------------------
    #  
  
# end class scb

#---------------------------------------------
#
#                      main
#
#---------------------------------------------


if __name__ == "__main__":

  #---------------------------------------------
  # startsc
  #          purpose: This is a shortcut call to instantiate a statechart
  #                   statecharts are created on the fly, each may be
  #                   named differently - the user types "startsc(my_sc)"  
  #                   at the command prompt
  #
  def startsc(scbobj):  # scbobj = StateChart Builder OBJect = my_sc
    # The name of the statechart is in the design file
    # statechart instantiation invokes the object and assigns it to a handle
    # that is passed back to the statechart builder and the user
       
    print "Statechart:", scbobj.chart_name   # the state chart
    cmd1 = "%s()" % (scbobj.chart_name)      # command to instantiate
    sc_handle = eval(cmd1)                   #  eval() not exec() to return value
    scbobj.scobj = sc_handle                 #  note the handle is an object - not a string
    #
    # if comms portion of ini file is set, then 
    #   initialize according to message queue type
    #
    # Note: The difference between rabbitmq and zeromq is that
    #       rabbitmq is one object that knows all queues, exchanges, and channels
    #       zeromq is one object per channel -> a list of objects 
    #
    
    if (RMQ):
      if (scbobj.pio != None):
        print "Subscribing to rabbitmq server"
        sc_handle.subscribe()
      # end if ports          
    else:
      if (scbobj.pio != None):  # zeromq has no implict server
  
        # zeromq Get() is a gevent timed loop - 
        #    to callback to debug prompt to allow testing
        #    inside get calls user_onepass 
        ii = 0
        while (ii < len(sc_handle.comm)):
          sc_handle.comm[ii].Dbg_if(scbobj)  # puts scb "self" inside comm object
          ii += 1
        # end while
      # end if ports

      # The reason for this next call is that the control polling
      #  loop is in the statechart and not here.
      #
      # Attach statchart builder into statechart master threaded polling loop
      # then start - its called a "thread" but it's really the master control loop
      #
      sc_handle.thread.dbg_interface(scbobj)

      # ************************************************************************************
      #
      # ************************************************************************************
      sc_handle.thread.start()          # passes control to statechart polling loop
      #
      # if there is no "scb" running, to start the statechart, do this:
      # 
      #  $ python
      #  > import <statechart_name>
      #  > sc = <statechart_name>.<statechart_name>()
      #  > uh = user_onepass.user_hook("dbg> ",sc)
      #  > sc.thread.dbg_interface(uh)
      #  > sc.thread.start()  # starts polling loop
      #  > sendEvent(self.scobj.<eventname>,[<data>]) # event
      #
      # The above exists in <statechart_name>_startup.py
      
    # end else zeromq
  
  #end startsc
  #-----------------------------------------------------------------------
  #
  #                     MAIN starts here:
    
  my_sc = scb(name="my_sc") # statechart builder that builds statechart

  my_sc.process_files()	   # process design and optional callback files

  # -------------- the interpreter -----------------
 
  if (my_sc.iniInterpret):                                 
    my_sc.scobj = None                             # erase the handle to the statechart
    import_name = re.sub(".py","",my_sc.out_file)  # strip .py off output file name
    cmd = "from %s import *" %(import_name)        # create a command to import the file 
    exec(cmd)                                      # execute the import  
    if (my_sc.warning_count >0):                   # if warnings then
      print "\nWarnings=%d" % my_sc.warning_count  # offer option to quit        
      msg = "Continue? (y,q) > "
      print msg,                       # print has no linefeed
      sys.stdout.flush()               # flush is for safety 
      quit_f,line = myreadline()              # non-blocking read
      line = line.upper()              # 'y' or 'Y'
      line.strip()                     # remove whitespace
      if (line[0] == 'Y'):             # keep going
        pass
      else:
        print "exiting"                # quit
        quit() 

  sc_help(my_sc.name)                  # display help
    
  my_sc.user_loop()                    # loop processing user commands

  #while True:            # testing gevents
     #self.user_onepass()    
  
 
  # -------------------  the end --------------------------------
  
