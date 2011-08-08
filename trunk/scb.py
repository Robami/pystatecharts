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
  
  invoke_help    	- command line help
  isStateValid          - test state presence 
  parent_state          - parent state of state
  getIniKeySet          - bundles repetitions of calls
  unique_events         - tests events to make sure values are unique
  verify_xition_start   - all hierarchial states and below must be started
  valid_event           - check event against event list
  get_parents           - creates list of states ordered by parent
  common_hierarchy       - finds common hierarch state
  xition_check          - check for faults in xitions
  get_ini_params        - get ini parameters
  enlist_string         - converst string to list of words
  isKnownToPython       - used to suppress warnings
  isParamKeyword        - expands shortcut
  proc_func_list        - converts a list to a statechart function call
  proc_func_stub        - converts a stub to a statechart function call
  gen_code_hooks        - common subroutine to generate code hooks
  genCommCallbacks      - subroutine to generate communciation callbacks 
                          based on port definitions
  listEvents            - lists events as strings
  listStates            - lists states as strings, identifies active states
  isStateActive         - test for active state
  listTransitions       - lists transitions
  startsc               - invokes statechart, generates handle
  help                  - prints useful functions
  recover               - recover from exception on interpreter command line
  main                  - main

  generated class functions:
    sendEvent           - send event to statechart
    shutdown            - shutdown statechart
    sendEventAsMsg      - xlate event to message, send message to rabbitmq queue
    getMsgSendEvent     - (debug - needs to be in thread), read message at queue, 
                           convert to statechart event
  
"""
  

#---------------------------- imports ----------------------------------------------

import sys
import string
import os
import optparse         # parses command line options
import ConfigParser     # parses ini file
import re               # parsing tools
import readline         # command line editing
import traceback        # exception trace
import datetime         # time

import time             # time

from scbUtilities import *  # isInlist
from scbObjects import *    # objects imported into generated code
#from scbExtensions import * # utility functions
                              
#---------------------------------------------
# invoke_help
#              purpose: print help for running this program
#
def invoke_help():
  print "statechart builder (scb) version 1.0"
  print "for options, try: python scb.py -h"
#end invoke_help
   
#---------------------------------------------
# isStateValid
#               purpose: returns true if state is known
#
def isStateValid(stateStr,            # state name 
                 disabled_f=False):   # also check disabled states
  global g_states 
  
  ii = 0
  while ii < len(g_states):
    if (g_states[ii].name == stateStr):  # if name matches name
      if (g_states[ii].disable):   # skip testing disable
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

def parent_state(stateStr):        # state name
  global g_states
  
  # for each state, if match then return parent
  ii = 0
  while ii < len(g_states):
    if (g_states[ii].disable):   # skip disabled
      ii = ii + 1
      continue
    if (g_states[ii].name == stateStr):  # if name matches name
      return g_states[ii].parent, ii     # return parent, index (no error)
    ii = ii + 1
  return "", -1                 # return empty string, error
  
#end parent_state
   
#------------------------------------------------------------------------------
# getIniKeySet
#              purpose: simplifies getting data from ini file
#
def getIniKeySet(filename,        # ini file name
                config_handle,    # ini handle
                section,          # ini section
                keylist,          # list of keys in section
                valuelist):       # return valuelist
  global g_warning_count
  ii = 0
  err_f = False
  while (ii < len(keylist)):                    # for each key
    key = keylist[ii]
    if config_handle.has_option(section,key):   # if section and key exist in ini file
        value = config_handle.get(section,key) 
        #
        # semicolons not in first column are not ini file comments - if not followed by 'known' word
        # then semantically ambiguous 
        #
        idx = value.find(';')                  
        if (idx != -1):
          if (not isKnownToPython(value[idx+1:len(value)])):
            g_warning_count = g_warning_count +1
            print "*** Warning #%d: ini comment ';' not in column 0, Python separator?\n[%s]\n %s = %s ***" % (g_warning_count,
                         section,key,value)
            
        valuelist = valuelist + [ value ]
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
# 
def unique_events():
  #
  # test 1: removed
  # test 2:
  #  if any event id range set overlaps with any other event set id range  
  #   then collision return error 
       
  global g_evo
  
  err_f = False
  
  if (not err_f):        # test 2
    ii = 0
    while (ii < (len(g_evo) -1)) and (not err_f):
       if (g_evo[ii].base == None):
         print "*** Error, event base cannot be None, Event: %s" % g_evo[ii].name 
         err_f = True
         break
       else:          
         min1 = int(g_evo[ii].base)
         max1 = int(g_evo[ii].base) + len(g_evo[ii].events)
         jj = ii + 1
         while (jj < len(g_evo)) and (not err_f):
           if (g_evo[jj].base == None):
             print "*** Error, event base cannot be None, Event: %s" % g_evo[jj].name 
             err_f = True
             break
           else:
             min2 = int(g_evo[jj].base)
             max2 = int(g_evo[jj].base) + len(g_evo[jj].events)
             if (min1 < min2):
               if (max1 > min2):
                 print  "*** Error, event collision, %s: base %d, %s: base %d ***"%(g_evo[ii].name,min1,
                                                                                    g_evo[jj].name,min2)
                 err_f = True
                 break
             else:
               if (max2 > min1):
                 print  "*** Error, event collision, %s: base %d, %s: base %d ***"%(g_evo[ii].name,min1,
                                                                                    g_evo[jj].name, min2)
                 err_f = True
                 break
           #endif not none
         
           jj = jj +1
         #end while (jj)
       #endif not none    
      
       ii = ii + 1    
    #end while (ii) 
    
    # Make Unique:
    #
    # For every event, add the base to the index, save as list of ids, 
    # this value can be reverse mapped (as an index) back to the name and event name
    #
  if (not err_f):
    ii = 0
    while ((ii < len(g_evo)) and not err_f):
      event_set = g_evo[ii]
        
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
        
      g_evo[ii].ids = event_set.ids   # put back
      g_evo[ii].updateList()          # updates combineLists function
                
      ii = ii +1
        
    #end while all event sets   
    
  #endif not error
    
  return err_f
    
# end unique_events

#-------------------------------------------------------------------
# verify_xition_start
#                     purpose: make sure all transitions have a start
# 
def verify_xition_start():

  global g_states         # list of sets of states
  global g_xitions        # list of sets of transition parameters
  global g_warning_count  # warnings 
   
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
  while (ii < len(g_states)):
      if (g_states[ii].disable):   # skip disabled
        ii = ii + 1
        continue
      state_set = g_states[ii]
      stype = state_set.type
      sname = state_set.name
      if ((stype == g_statetypes.concurrent)  or (stype == g_statetypes.hierarchical)):
        match_f = False
        jj = 0
        while (jj < len(g_xitions)):
          xition_set = g_xitions[jj]
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
          g_warning_count = g_warning_count + 1
          print "*** Warning #%d: hier/conc state %s needs a start transition. ***" % (g_warning_count,sname)          
          # no break on warning          
      ii = ii + 1    
  #end while outer loop

  if (not err_f):
    #
    # case 2:
    #
    ii = 0
    while (ii < len(g_states) and (not err_f)):  # for each state hierarch or concurrent
      if (g_states[ii].disable):   # skip disabled
        ii = ii + 1
        continue
      state_set1 = g_states[ii]      
      stype1 = state_set1.type
      sname1 = state_set1.name
      sparent1 = state_set1.parent         # the parent in the next search
      if ((stype1 == g_statetypes.concurrent) or (stype1 == g_statetypes.hierarchical)):       
        ii = ii + 1
        continue
      #
      # only regular states in this loop
      #
      jj = 0
      choices = []
      while (jj < len(g_states) and (not err_f)):  # search each child for common parent
        if (g_states[jj].disable):   # skip disabled
          jj = jj + 1
          continue
        state_set2 = g_states[jj]
        sname2   = state_set2.name  
        sparent2 = state_set2.parent
        
        if (sparent2==sparent1):
          choices = choices + [ sname2 ]     # make list of children of common parent
        jj = jj + 1
      # end while
     
      if (len(choices)!=0):
        match_f = False              # search list of children, find start, if any
        kk = 0     
        while(kk < len(g_xitions)): 
          if (g_xitions[kk].disable):   # skip disabled
            kk = kk + 1
            continue
          xition_set = g_xitions[kk]
          xstart = xition_set.startState
          xend   = xition_set.endState               # search for start in list of children
          if (xstart=='start') and (isInlist(choices,xend)):
            match_f = True
            break
          kk = kk + 1
        #end while 
        
        if (not match_f):
          print "*** Error: One of state(s) %s needs a start transition. ***" % choices
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
def valid_event(event_phrase):
  global g_evo
  
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
    event_f, event_info = NamedObject.namedListMatch(list_of_lists=g_evo,
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
    event_f, dummy = NamedObject.namedListMatch(g_evo,"name",class_name,"events",event_name)
    
  return event_f, event_fixup 
#end valid_event
#-------------------------------------------------------------------
# get_parents
#             purpose: returns all parents of a state
#
def get_parents(state):
  global g_states
  err_f = False
  array=[]
  while(True):
    pstate, idx = parent_state(state)  # get parent
    if (idx<0):                        # error
      break
    array = array + [g_states[idx]]    # ordered list
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
def common_hierarchy(list1,   # list of parents of state
                     list2):  # list of parents of state
  ii = len(list1) -1
  jj = len(list2) -1
  match_f = False
  match_value = ""
  #
  # work backwards, root is last element
  #
  while (ii >= 0):
    if (list1[ii].type == g_statetypes.hierarchical):
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
def xition_check():
   global g_statetypes     # list of valid state types
   global g_xitions        # list of transition objects
   global g_states         # list of state objects
   global g_warning_count  # warning counter   
   err_f = False           # error
   disable_f = False       # flags disabled transitions
   
   # case: 
   # 1. Warning: any transition from A to X, when A's parent is not hierarchical will not transition 
   #
   # 2a. warning - a transition without an event may do nothing (except for start, which is required, Error).
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
   while(ii<len (g_xitions)):     
     xition_set = g_xitions[ii]
     if (xition_set.disable == True):  # skip disabled
       ii = ii +1
       disable_f = True
       continue
     xstart = xition_set.startState
     #
     # make a unique set of states so that if the state has been checked once, 
     # it doesn't need to be checked again
     #
     if (not isInlist(ulist,xstart)):     # if state in transition first time seen
       ulist = ulist + [ xstart ]         # then add to unique list (to prevent duplicate functions)
        
       jj = 0
       break_f = False
       while (jj<len(g_states) and (not break_f)):
         if (g_states[jj].disable):   # skip disabled
            jj = jj + 1
            continue
         state_set1 = g_states[jj]
         state_name1   = state_set1.name
         if (state_name1 == xstart):
           type1 = state_set1.type
           if (type1 !=  g_statetypes.hierarchical):
             parent1 = state_set1.parent
             kk = 0
             while(kk<len(g_states) and (not break_f)):
               if (g_states[kk].disable):   # skip disabled
                 kk = kk + 1
                 continue
               state_set2 = g_states[kk]
               state_name2 = state_set2.name
               if (state_name2 == parent1):
                 if (state_set2.type != g_statetypes.hierarchical):
                   g_warning_count = g_warning_count +1
                   print "*** Warning #%d: State %s is not hierarchical, nor its parent %s. ***" % (g_warning_count,
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
     while ((ii < len(g_xitions)) and (not err_f)):
        xition_set1 = g_xitions[ii]
        if (xition_set1.disable == True):  # skip disabled
          ii = ii +1
          disable_f = True
          continue
        xend = xition_set1.endState  
        if (xend == 'end'):
          xevent = xition_set1.event
          end_f = True
          jj = 0  
          while (jj < len(g_xitions)):
            xition_set2 = g_xitions[jj]
            if (xition_set2.disable == True):  # skip disabled
               jj = jj +1
               disable_f = True
               continue
            if ((xevent == xition_set2.event) and (xition_set2.endState != 'end')):
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
   while(ii<len (g_xitions)):     
     event_f = False    
     xition_set1 = g_xitions[ii]
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
         while(jj<len (g_xitions)):     
           xition_set2 = g_xitions[jj] 
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
           g_warning_count = g_warning_count +1
           print "*** Warning #%d: Transition %d, from state: %s, to state: %s, transition w/o event. ***" % (g_warning_count,
                                                                                ii+1,
                                                                                xition_set1.startState,
                                                                                xition_set1.endState)
       #end else not start transition
     else: # not None event
       event_f, event_fixup = valid_event(xition_set1.event)
       if (not event_f):
         print "*** Error: In section [%s], Unresolved event: %s ***" % (xition_set1.name,
                                                                           xition_set1.event)
         err_f = True
         break
       else:
         if (event_fixup != None):
           
           g_warning_count = g_warning_count +1
           print "*** Warning #%d: In section [%s], event: %s, class added ***" % (g_warning_count,
                                                                                xition_set1.name,
                                                                                xition_set1.event)  
           g_xitions[ii].event = event_fixup  
     ii = ii + 1
   #end while 
   
   #
   # case 4: 'to' and 'from' must have a common hierarchical parent else 
   #         side-effects will occur
   #
   if not err_f:  
     ii = 0
     while ((ii < len(g_xitions)) and (not err_f)):
        xition_set = g_xitions[ii]
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
          err_f, array1 = get_parents(xstart)
          if (err_f):
            #
            # if state is disabled, then convert to warning and disable the transition
            #
            if (isStateValid(value=xstart, disabled_f=True)): 
              g_warning_count = g_warning_count +1
              print "*** Warning #%d: Transition: %s, %s disabled, transition also ***"%(
                                                                                g_warning_count,
                                                                                xname,
                                                                                xstart) 
              g_xitions[ii].disable = True
              err_f = False
            else:
              print "*** Error: Transition %s, bad start state: \'%s\' ***" % (xname,xstart)
        
        if (not err_f):
          if ((xend != 'end') and (not g_xitions[ii].disable)):    
            err_f, array2 = get_parents(xend) 
            if (err_f):
              #
              # if state is disabled, then convert to warning and disable the transition
              #
              if (isStateValid(value=xend, disabled_f=True)): 
                g_warning_count = g_warning_count +1
                print "*** Warning #%d: Transition: %s, %s disabled, transition also ***"%(
                                                                                g_warning_count,
                                                                                xname,
                                                                                xend) 
                g_xitions[ii].disable = True
                err_f = False
              else:
                print "*** Error: Transition %s, bad end state: \'%s\' ***" % (xname,xend)
          
        if (not err_f):
          if (array1 !=None) and (array2 != None):
            match_f, cv = common_hierarchy(array1,array2)
            if (not match_f):
              print "*** Error: Transition %s, states %s, %s have no common hierarchical parent. ***" % (xname,
                                                                 xstart,xend)
              err_f = True
              break
        
        ii = ii + 1
     #end while
     
   if (not err_f):
     if (disable_f):
       g_warning_count = g_warning_count +1
       ii = 0
       while (ii < len(g_xitions)):
         if (g_xitions[ii].disable):
           print "*** Warning #%d: In section [%s], transition disabled ***" % (g_warning_count,
                                                                                g_xitions[ii].name)
         ii = ii + 1  
       #end while
       
   return err_f
   
#end xition_check
#------------------------------------------------------------------- 
# get_ini_params
#                purpose: get parameters from the ini file
#   
def get_ini_params(fname):   # filename
   
  global g_states       # list of sets of states
  global g_xitions      # list of sets of transition parameters
  global g_evo          # list of events
  global g_spe          # list of suppressed printing events
  global g_chart_name   # name of statechart
  global g_initializer  # python initializer
  global g_iniDebug     # enable debug features
  global g_iniPrint     # print to display 
  global g_iniLimitAction   # prevent embedding code
  global g_iniGenCode       # generate code to file
  global g_iniGenCallbacks  # generate/overwrite callbacks
  global g_iniInterpret     # enter code interpreter
  global g_iniInsertCB      # insert callbacks file
  global g_statetypes       # recognized types in statechart
  global g_warning_count    # warnings - syntactically ok, but semantically problematic
   
  err_f = False
  port_f = False
  pio = None
 
 
  if (not os.path.isfile(fname)):
    print "*** Error: File %s does not exist ***" % (fname)
    err_f = True
  
  if (not err_f):
    cp = ConfigParser.ConfigParser()
    try: 
      cp.read(fname)               # no error if file doesn't exist!
    except Exception as eobj:
      print "*** Error:", eobj, " ***"
      err_f = True
      
  if (not err_f):
    section = "STATECHART"
    if (not cp.has_section(section)):
      print "*** Error:", fname, "missing [%s] section ***" % (section)
      err_f = True  
  
  if (not err_f):     
    key = "name"
    if cp.has_option(section,key):
      g_chart_name = cp.get(section,key)  
    else:
      print "*** Error: %s, missing key \"%s\" in [%s] section ***" % (fname, key, section)
      err_f = True    
  
  if (not err_f): 
    g_initializer = []
    section = "INITIAL"
    if (not cp.has_section(section)):
      g_warning_count = g_warning_count + 1
      print "*** Warning #%d, %s: missing [%s] section ***" % (g_warning_count,fname,section)      
    else:   
      count = 1
      key = "Python_"
      key = key + str(count)       
      while cp.has_option(section,key):
        value = cp.get(section,key) 
        g_initializer = g_initializer + [ value ]
        count = count +1
        key = "Python_" + str(count)
      #end while
      key = "file"
      if cp.has_option(section,key):
                
        pyinit_name = cp.get(section,key) 
        if (pyinit_name=='None') or (pyinit_name==''):
          pass
        else:
          if (len (g_initializer) >0):
            g_warning_count = g_warning_count + 1 
            print "*** Warning #%d, %s: section [%s] two forms of initialization ***" % (g_warning_count,fname,section)          
          try:
	    pyfp = open(pyinit_name,'r')
          except IOError:
            print "*** Error: %s, [%s] section, key [%s], cannot open: %s ***" % (fname, section, key, pyinit_name)
            err_f = True
          
          if (not err_f):
            line = pyfp.readline()    
            while (line != ""):            
              sz = len(line)
              if (line[sz-1] == '\n'):   # remove linefeed, but preserve indenting
                  line = line[0:sz-1]
            
              g_initializer = g_initializer + [ line ]
              line = pyfp.readline()
            #end while
            pyfp.close()
    
  if (not err_f):  
    section = "OPTIONS"
    if (not cp.has_section(section)):
      print "*** Error: %s, missing [%s] section ***" % (fname, section)
      err_f = True
  #
  # these are optional options
  #
  if (not err_f):
    g_iniDebug = 0           
    key = "Debug"
    if cp.has_option(section,key):
      tmp = cp.get(section,key)   # remember param comes in as string
      tmp = tmp.strip()
      tmp = tmp.upper()      
      if ((tmp=='TRUE') or (tmp=='1')):
        g_iniDebug = 1
      
    g_iniPrint = 0
    key = "Print"
    if cp.has_option(section,key):
      tmp = cp.get(section,key)
      tmp = tmp.strip()
      tmp = tmp.upper()
      if ((tmp=='TRUE') or (tmp=='1')):
        g_iniPrint = 1
    
    g_iniLimitAction = 0
    key = "LimitAction"
    if cp.has_option(section,key):
      tmp = cp.get(section,key)
      tmp = tmp.strip()
      tmp = tmp.upper()
      if ((tmp=='TRUE') or (tmp=='1')):
        g_iniLimitAction = 1
    
    g_iniGenCode = 0
    key = "GenCode"
    if cp.has_option(section,key):
      tmp = cp.get(section,key)
      tmp = tmp.strip()
      tmp = tmp.upper() 
      if ((tmp=='TRUE') or (tmp=='1')):
         g_iniGenCode = 1
    
    g_iniGenCallbacks = 0
    key = "GenCallbacks"
    if cp.has_option(section,key):
      tmp = cp.get(section,key)       
      tmp = tmp.strip()
      tmp = tmp.upper()
      if ((tmp=='TRUE') or (tmp=='1')):
        g_iniGenCallbacks = 1   
    
    g_iniInterpret = 0
    key = "Interpret"
    if cp.has_option(section,key):
      tmp = cp.get(section,key) 
      tmp = tmp.strip()
      tmp = tmp.upper()
      if ((tmp=='TRUE') or (tmp=='1')):
        g_iniInterpret = 1 
      
    g_iniInsertCB = ""
    key = "InsertCB"
    if cp.has_option(section,key):
      g_iniInsertCB = cp.get(section,key)     
   
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
    g_states = []                     # list of [ states and parameters ]
    stateSet = []
    while (not err_f):
      if cp.has_section(section): 
        iniState = []                   # [ states and parameters ]
        err_f, iniState = getIniKeySet(fname, cp, section,
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
        
        stateObject = StatesObject(name   = iniState[0],
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
          if not isStateValid(parent):             # catches spelling errors
            #
            # if state is not there, check to see if it has been defined but disabled 
            # if so, then warning, ask user if they want dependencies disabled.
            #
            if isStateValid(stateStr=parent,disabled_f = True):
              g_warning_count = g_warning_count + 1
              print "*** Warning #%d, State %s disable, disabling dependent state %s.***" % (
                (g_warning_count,parent,stateObject.name))  
              disable_f = True
            else:
              # if a parent is 'None', then that is ok, indicates top hierarchy
              if (parent!='None'):
                print "*** Error: %s, section [%s], \"%s\" has no parent  ***" % (fname, section, parent)
                err_f = True
                break

          type = stateObject.type              # check for valid type
          if (not isInlist(g_statetypes.list,type)): 
            print "*** Error: %s, section [%s], invalid state \"%s\" for key \"%s\" ***" % (fname, 
                                                                          section, type, key)
            print "Valid states - ", g_statetypes.list
            err_f = True
            break
        
        #endif not disabled       
        
          
        g_states = g_states + [stateObject]    # next
        stateSet = stateSet + [stateObject]
            
        count = count +1
        section = section_base + str(count)
      else:
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
        state_f, state_list = NamedObject.namedListMatch(stateSet,"type",g_statetypes.hierarchical)
        if (state_f):
          top_name = state_list.name 
        else:
          top_name = stateSet[0].name
          
        print  "State set %d, %s: %d states" % (base_count,top_name,last_count)
          
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
    while (ii < len(g_states)):
      if (g_states[ii].disable == False):
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
      g_warning_count = g_warning_count + 1 
      print "*** Warning #%d, %s, States don't add up. Duplicate section or badly named section? ***" % (g_warning_count,fname)      
    print # new line separator
  # ------------------         events               --------------------- 
  
    events = []
    scount = 1
    section_base = "EVENTS_"
    section = section_base + str(scount)
    if (not cp.has_section(section)):
      g_warning_count = g_warning_count + 1
      print "*** Warning #%d, %s: missing [%s] section ***" % (g_warning_count,fname,section) 
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
  g_evo = []    
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
      g_evo = g_evo +  [ EventObject(file=g_chart_name,base=events[ii][0], 
                                     name=events[ii][1], events=events[ii][2:]) ]
      print "Event set %d - %s: %d events, base: %s " % (ii+1, events[ii][1],
                                                         len(g_evo[ii].events), 
                                                         g_evo[ii].base)
      sum = sum + len(g_evo[ii].events)
      ii = ii + 1
    # end while iterating events    
  
    err_f = unique_events()  # test for unique events, 
                             # if ok, generate unique ids for events
    #
    # errors in event uniqueness are unrecoverable
    #
    if (not err_f):
      print "%d events total\n" % sum     
      
  # ---------------- optional event suppress print --------------------------- 
   
    section = "SUPPRESS_PRINT"
    if (cp.has_section(section)):

      g_spe = []                   # [ <class>.<event> , ... ]      
       
      #
      # pick up a list of events, each identified by event_x where x increments by 1
      # allow section with no entries
      #
      kcount = 1
      key_base = "event_"
      key = key_base + str(kcount)
    
      while (cp.has_option(section,key)):  
        value = cp.get(section,key) 
        g_spe = g_spe + [ value ]
        kcount = kcount +1                # next key
        key = key_base + str(kcount)
      #end while
        
      #
      # check for event validity
      #
      ii = 0
      while ii < len(g_spe):
        event = g_spe[ii]
        event_found, event_fixup = valid_event(event)
        if not event_found:
          print "*** Error: section [%s], unresolved event %s ***" %(section,event)
          err_f = True
          break
          if (event_fixup!=None):
            g_spe[ii]=event_fixup
        ii = ii + 1
      # end while
          
      if (not err_f):
        print "%d suppressed printing events\n" % len(g_spe)
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
    g_xitions = []                     # list of [ transitions and parameters ]
    while (not err_f):
      if cp.has_section(section):
        iniXition = []                   # [ transitions and parameters ]
        err_f, iniXition = getIniKeySet(fname, cp, section,
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
        
        g_xitions = g_xitions + [XitionsObject(name=section,
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
     err_f = verify_xition_start()  # all hierarchical states must have a start transitions  
     
    if (not err_f):
      err_f = xition_check()  # look for problems in transitions
    
  # endif no error, collect transitions
    
  if (not err_f):  # count transitions, skipping disabled
    ii = 0
    esum = 0
    dsum = 0
    while (ii < len(g_xitions)):
      if (g_xitions[ii].disable == False):
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
    print "Transitions: %d total, %d enabled, %d disabled" % (ssum,esum,dsum)
    if (ssum != esum + dsum):
      g_warning_count = g_warning_count + 1 
      print "*** Warning #%d %s, Transitions don't add up. Duplicate section or badly named section? ***" % (g_warning_count,fname)
    print  # new line separator
  
  # ---------------- optional ports --------------------------- 
     
    section = "PORT_INIT"
    port_init = []               # initialization of rabbitmq object
    
    if (cp.has_section(section)):   # optional for distributed state machines
      port_f = True
      
    
    if (port_f):                  # not an array of arrays for this section
      err_f, port_init = getIniKeySet(fname, cp, section,['import_name','host','userid','password'],port_init)		            
     
     
  if ((not err_f) and port_f):
      pio = PortInitObject(import_name = port_init[0],
                            host        = port_init[1],
		            userid      = port_init[2],
			    password    = port_init[3]) 
        
  if ((not err_f) and port_f):
      count = 1
      section_base = "PORT_CONFIG_"
      section = section_base + str(count)
      if (not cp.has_section(section)):   # optional for distributed state machines
        print "*** Error: %s, missing [%s] section ***" % (fname, section)
	err_f = True
    
  if ((not err_f) and port_f):
      pco = []                     # list of [ ports and parameters ]
      while (cp.has_section(section) and (not err_f)):
        iniPort = []                   # [ states and parameters ]
        err_f, iniPort = getIniKeySet(fname, cp, section,
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
       
  if ((not err_f) and port_f): # list of input and output ports
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
        err_f, iniPort = getIniKeySet(fname, cp, section,
                                    ['name','type','port','event_id'],
			            iniPort)
        if (err_f):
          break
	 
	pdo = pdo + [PortDataObject(name=iniPort[0],type=iniPort[1],port=iniPort[2],
	                             event_id =iniPort[3])] 
        port_data = port_data + [iniPort]
        count = count + 1
        section = section_base + str(count)
      #end while
      
  if err_f or (not port_f):
    pio = None     # port initialization
    pco = []       # port configuration
    pdo = []       # port definition
    
  if not err_f:  
    if port_f: 
      print "%d port configuration(s)" % (len(pco))
      print "%d port(s)" % (len(pdo))
    else:  
      print "No ports"
  
  return err_f, pio, pco, pdo
  
# end get_ini_params    
 
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
#-------------------------------------------------------------------------
# isKnownToPython
#                 purpose: unexpected words raise warnings
#                          this list of statechart keywords reduces the number of warnings raised
#
def isParamKeyword(word_to_test):  # word to test
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

def proc_func_list(plist,     # parameter list
                   type,      # state or transition key
                   wfp,       # write file pointer
                   debug_f):  # debug flag
        
    global g_iniPrint
    global g_warning_count
         
    method = plist[0]
        
    # method_name is method with parens removed
    # (and the designer may forget to put the parans in
    # to begin with)
    
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
    if (g_iniPrint):  
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
    code_f = False
    while (jj < len(plist)):	
          
        phrase = plist[jj]
        idx0 = phrase.find(".")
        if (idx0 > 0):
            class_name = phrase[0:idx0]             # endit at "."
            event_name = phrase[idx0+1:len(phrase)] # starting after "."
                
        else:                        # class not given (hope unique event)
            class_name = None
            event_name = phrase    
                        
        event_f, event_fixup = valid_event(plist[jj])
        if (event_f):
          if (event_fixup != None):
            plist[jj] = event_fixup
          event_name = plist[jj]
                    
        if ((not event_f) and (g_pio != None)):
           port_f, port_list = NamedObject.namedListMatch(g_pdo,"name",plist[jj]) # search on method                      

        buf2 = ""
        if (event_f):       # data in list is not python code, interpret as event to be sent
                            # event may be translated to:
                            #
                            # if not port then
                            #   sendEvent(<eventclass>.<eventname>, None) 
                            #
                            # if function name matches portname then
                            #   param.sendEventAsMsg(port,event)
	      
                            # Note1: when building states that emit transition events not through ports, 
                            #        event data values are unknown
                            # Note2: when method names match port names then
                            #        event names and also data values are known
                                 	      
            match_f, port_list = NamedObject.namedListMatch(g_pdo,'name',method_name)
                
            if (match_f):    # send event to port 
              event_found, event_fixup = valid_event(plist[jj])
              if (event_found):
                if (event_fixup!=None):
                  plist[jj]=event_fixup
                buf1 = "    param.sendEventAsMsg(\"%s\",%s)" % (method_name,plist[jj])                
              else:  # invalid event
                print "*** Error: Undefined event:%s, at %s ***" % (plist[jj],method_name)                    
                return -1
               
             
            else:
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
              # print <state_name>
              #
              buf2 =  "    print " +"\"" + plist[0] + "\""
		
        elif (port_f):         # data in list may be python code (or keyword)
                               # check for match in port, 
                               # if match then "get" at port
                               # receive event at port		 	      
              #
              # name is an object, need to covert into a string
              #
              match_f, port_list = NamedObject.namedListMatch(g_pdo,'name',plist[jj])
	      
              if (match_f):
                buf1 = "    param.getMsgSendEvent(\"%s\")" % (plist[jj])
              else:	         # no match, error in design file 
                print "*** Error: Undefined port at entry = %s ***" % (plist[jj])                    
                return -1
	           
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
             #     requires a context prefix to work, i.e. sendEvent() needs to be param.sendEvent 
             #     This tool knows that, so if a common method is called,
             #     the "param." can be added by this tool
             #
             if (isParamKeyword(plist[jj])):
               plist[jj] = "param." +  plist[jj]
             else:
               g_warning_count = g_warning_count + 1
               info = "# *** Warning #%d: %s, " % (g_warning_count,method)
               info = info + "%s is not an Event or Port. ***" % (plist[jj])
               print info
           #endif
               
           buf1 = "    %s" % (plist[jj])               
	#end else
            
        if (g_iniPrint):
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
def proc_func_stub(method,    # name of method 
                   type,      # statechart type
                   obj_info,  # section info structured as a named object
                   wfp,       # write file pointer
                   debug_f):  # debug flag
 
    global g_iniPrint  
    
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
	    
    if (debug_f ==0):                # provide placeholder for code
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
  
    if (g_iniPrint):
       print buf1
       print buf2
       print buf3
	    
    if (wfp != None):
      wfp.write(buf1 + "\n")
      wfp.write(buf2 + "\n")
      wfp.write(buf3 + "\n")
	              
#end proc_func_stub
              
#-------------------------------------------------------------------------
# gen_code_hooks
#              purpose: all purpose statechart generate code   
#  
def gen_code_hooks(pdo,      # port data object
                   evo,      # event object
                   wfp,      # write file pointer
                   ulist,    # built list of unique method labels
                   inlist,   # set of lists of states or transitions
		   type,     # index of function into states/transitions
		   debug_f): # debug flag, generate debug message
 
  
  global g_iniLimitAction
  global g_warning_count
  global g_iniPrint
  global g_funcFromFile
  
  #
  # Note 1: Events are not processed in the TRANSITION event field
  #         in this function - badly formed events may slip through to
  #         importing he created python code.
  #
  # Note 2: Events given as part of entry, do, exit, or action fields
  #         but misspelled, will be assumed to be and treated as 
  #         other python code statements - which will generate warnings or errors
  #         during importing the created python code. 
  #
  insProcList = []  
  
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
      
      if (not isInlist(ulist,plist[0])):     # if method is unique
        ulist = ulist + [ plist[0] ]         # then add to unique list (to prevent duplicate functions)
  	
        #
        # Note1: Embedded spaces prevent searching for keywords for generating code BUT
        #        embedded spaces are necessary for python indenting for 
        #        copying design file python statements directly into output generated code -
        #        So, this is a two pass process:
        #        1. Remove spaces, if keywords are not found then
        #        2. Put spaces back treat as embedded python
        #
        # Note2: If you create a new keyword fora new feature, and don't test for it here,
        #        The code that tests for the keyword will fail later because of Note1.
        #        
        # Note3: You can't mix and match embedded code with keywords. If a line without a keyword is 
        #        found the whole thing is treated as a direct copy.
	
        #
        # first pass through function parameter list
        #
        port_f  = False   # each of these are vectors for processing design parameters
        event_f = False
        code_f  = False
        jj = 1                               # skip first entry, already processed
        while (jj < len(plist)):             # check for membership in events or ports
            #
            # is the first parameter an event?
            # if it contains a '.', then split into class and event
            # if it doesn't assume no class, assume event unique to all classes 
            # 
            
            event_f, event_fixup = valid_event(plist[jj])  # 
            if (event_f):
              if (event_fixup != None):
                plist[jj]= event_fixup           
            
            #
            # if not an event, see if value matches a port name
            #
            if (not event_f):
              port_f, dummy = NamedObject.namedListMatch(g_pdo,"name",plist[jj])
            
            if ((not event_f) and (not port_f)):  # must be embedded python code, is this permitted?
              if (g_iniLimitAction == 1):
                print "*** Error: undefined event at entry = %s ***" % (inlist[ii])
                return -1
              else:  # assume embedded python code
                     # Note: A badly formed (i.e. misspelled) event will be interpreted as
                     #       a python statement
                     # space removal as part of enlisting hurts intent -> undo
                plist = enlist_string(entry,0)
                code_f = True
	        break              # stop processing in  this loop
	      #end if limitAction	  
  	                
            jj = jj + 1
            
        # end while middle loop
        
        # convert list to a statechart recognized function all
        
        method = plist[0]
        match_f = False
        if (g_funcFromFile != None):   # search callbacks file
          match_f, func_text = g_funcFromFile.getFuncFromFile(method)
        
        if (match_f):
          print "replacing %s from: %s" % (method,g_iniInsertCB)
          if (g_iniPrint):
            print func_text          
          if (wfp !=None):
            wfp.write(func_text)
        #endif match in callbacks file    
        else:
          if (len(plist) > 1):
            proc_func_list(plist, type, wfp, debug_f) 
          else:
            proc_func_stub(method, type, section_set, wfp, debug_f)         
      #end if unique 
      else:
        #
        # states may vector to common routines, but only the first 
        # reference may  have a body
        #
        if (len(plist) > 1):  # if not unique and parameters
          g_warning_count = g_warning_count + 1
          print "# *** Warning %#d: non-unique method with body: %s, ignored ***" % (g_warning_count,plist)        
      
    #end if list 
    else:                    # not list 
        skip_f = False        
        if entry == "None":
          skip_f = True
      
        if not skip_f:
        
          # throw away everything to the right of the "(" in the entry
          # has it been seen before?
          # if so, then skip
        
          if (isInlist(ulist,entry)):  # if not seen before
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
            if (g_funcFromFile != None):   # search callbacks file
              match_f, func_text = g_funcFromFile.getFuncFromFile(method)
            
            if (match_f): 
              print "%s from %s" % (method,g_iniInsertCB)
              if (g_iniPrint):
                 print func_text          
              if (wfp !=None):
                wfp.write(func_text)
            # endif match in callbacks file
            #
            # functions for which no code has been written
            # are stubbed by "pass" for Actions and
            #                "return True" for Guards
            # or a print statement saying something along the lines of:
            #  "I was here"
            #
            else:   # not a list, just a method alone
              proc_func_stub(method,             # user entered 
                             type,               # where found
                             section_set,   # list of state or transition values
                             wfp, debug_f)  # 
                      
        # endif not skipped
        
    ii = ii+ 1  
  #end while outermost loop (state or transition lists)    
    
  return 0, ulist
# end gen_code_hooks
#---------------------------------------------
# genCommCallbacks
#            purpose: generate the message queue "callbacks" 
#
def genCommCallbacks(pdo,      # port data object
                     evo,      # event object
                     wfp):     # write file pointer
		       
  #
  # using pdo, evo
  #
  
  global g_iniPrint
  global g_iniGenCode
  
  cbObj = []        # callback object
  ii = 0
  while ii < len(pdo):
    if (pdo[ii].type == 'input'):   # only inputs need to be in callbacks    
      cbObj = cbObj + [CallbackObject(queue=pdo[ii].port, event_id=pdo[ii].event_id) ]
    ii = ii +1
  #
  # an output port is an exchange
  # an input port is a queue
  #
  # sort by port, "sorted" is built-in for the purpose of aligning input ports (queues) with callbacks
  # each callback has all the expected messsages for the queue, if so configured
  #
  
  sortedCbo = sorted(cbObj,key =lambda dummy: dummy.queue)
  
  first_f = True        # statemachine vectors between 1: function definition+if, 2: elif(s), and 3: else+return
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
      tbuf = "    def %s_queueCallback(self,msg):"   % (sortedCbo[ii].queue); mbuf = mbuf + [tbuf]
      tbuf = "      thisFcn = \'%s_queueCallback\'" % (sortedCbo[ii].queue) ; mbuf = mbuf + [tbuf]
      tbuf = "      err_f = False"                                          ; mbuf = mbuf + [tbuf]
      tbuf = "      expctd = []"                                            ; mbuf = mbuf + [tbuf]
      jj = 0
      while (jj<len(sortedCbo)):
        tbuf = "      expctd.append(\"%s\")"  % (sortedCbo[jj].event_id)     ; mbuf = mbuf + [tbuf]  
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
      tbuf = "      if (isInlist(expctd,\'JsonData\')):"              ; mbuf = mbuf + [tbuf]
      tbuf = "        evData = None"                                  ; mbuf = mbuf + [tbuf]
      tbuf = "        eidx = msg.body.find(\':\')"                    ; mbuf = mbuf + [tbuf]
      tbuf = "        if (eidx <0):"                                  ; mbuf = mbuf + [tbuf]  # no data
      tbuf = "          eidx = len(msg.body)"                         ; mbuf = mbuf + [tbuf]
      tbuf = "        else:"                                          ; mbuf = mbuf + [tbuf]
      tbuf = "          dataStr=msg.body[msg.body.find(\':\')+1:]"    ; mbuf = mbuf + [tbuf]
      tbuf = "          evData = json.loads(dataStr)"                 ; mbuf = mbuf + [tbuf]
      tbuf = "        evStr = msg.body[0:eidx]"                       ; mbuf = mbuf + [tbuf]
      tbuf = "        evid = EventObject.EventToId(self.evo,evStr)"   ; mbuf = mbuf + [tbuf]
      tbuf = "        if (evid >0):"                                  ; mbuf = mbuf + [tbuf]
      tbuf = "          self.sendEvent(evid,evData)"                  ; mbuf = mbuf + [tbuf]
      tbuf = "        else:"                                          ; mbuf = mbuf + [tbuf]
      tbuf = "          emsg = \"%s: %s is not an event\" % (thisFcn,evStr)" ; mbuf = mbuf + [tbuf] 
      tbuf = "          err_f = True"                                 ; mbuf = mbuf + [tbuf]
      tbuf = "      elif (isInlist(expctd,msg.body) or isInlist(expctd,\'AnyEvent\')):" ; mbuf = mbuf + [tbuf]
      tbuf = "        eid = EventObject.EventToId(self.evo,msg.body)" ; mbuf = mbuf + [tbuf]
      tbuf = "        if (eid>0):"                                    ; mbuf = mbuf + [tbuf]
      tbuf = "          self.sendEvent(eid)"                          ; mbuf = mbuf + [tbuf]
      tbuf = "        else:"                                          ; mbuf = mbuf + [tbuf]
      tbuf = "          emsg = \"%s: %s is not an event\" % (thisFcn,msg.body)" ; mbuf = mbuf + [tbuf] 
      tbuf = "          err_f = True"                                 ; mbuf = mbuf + [tbuf]   
      tbuf = "      else:"                                            ; mbuf = mbuf + [tbuf] 
      tbuf = "        emsg = \"%s:(rd,[exp]):(%s,%s)\" % (thisFcn,msg.body,expctd)" ; mbuf = mbuf + [tbuf] 
      tbuf = "        err_f = True"                                   ; mbuf = mbuf + [tbuf]
      tbuf = "      if (err_f):"                                      ; mbuf = mbuf + [tbuf]
      tbuf = "        if (self.txtlog!=None):"                        ; mbuf = mbuf + [tbuf]
      tbuf = "          self.txtlog.put(EL.LogStatusEvent(emsg))"     ; mbuf = mbuf + [tbuf]
      tbuf = "        else:"                                          ; mbuf = mbuf + [tbuf] 
      tbuf = "          print emsg"                                   ; mbuf = mbuf + [tbuf]    
      tbuf = "      msg.channel.basic_ack(msg.delivery_tag)"          ; mbuf = mbuf + [tbuf]	
      #
      # build a list of queues and callbacks that can be input to the Subscribe method
      #
      queue = sortedCbo[ii].queue
      method = sortedCbo[ii].queue + "_queueCallback" 
      retlist = retlist + [[queue, method]]   # list of two-element lists	
      first_f = True 
    ii = ii + 1
    
  # end while
  
  if (g_iniPrint):                # print code to display
    ii = 0
    while (ii < len(mbuf)):         
       print mbuf[ii]
       ii = ii + 1 
                                  # generate python code
  if (g_iniGenCode):				  
    ii = 0
    while (ii < len(mbuf)):         
       wfp.write( mbuf[ii] + "\n") 
       ii = ii + 1
  
  return retlist
  
#end genCommCallbacks

#---------------------------------------------
# listEvents
#     purpose: list the events found in the design file
#
def listEvents():
  #
  # search for statename in transitions
  # print as tuple [index,state,parent,type]
  
  ii = 0  
  while ii < len(g_evo):   
    print "event_set %s: %d events" % (g_evo[ii].name, len(g_evo[ii].events))
    jj = 0
    event_set = g_evo[ii]
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
def listStates(handle=None,active=None):  
  #
  # search for statename in transitions
  # print as tuple [index,state,parent,type]
  
  global g_states
  global g_handle
  
  print "(Index, State, Parent, Type, Active)"
  ii = 0
  while ii < len(g_states):
    if (g_states[ii].disable):   # skip disabled
      ii = ii + 1
      continue
    #
    # this next line took a long time to figure out
    #  
    if (handle!=None):
      cmd = "%s.statechart.runtime.is_active(%s.statechart.%s)" % (handle,handle,g_states[ii].name)
    else:
      cmd = "g_handle.statechart.runtime.is_active(g_handle.statechart.%s)"%(g_states[ii].name)
    is_active = eval(cmd)
    if ((active == None) or  ((active ==True) and is_active) or ((active ==False) and (not is_active)) ):
      buf2 = "[%d, %s, %s, %s, %s]" % (ii+1, g_states[ii].name, g_states[ii].parent,
                                     g_states[ii].type, is_active)
        
      print buf2
      
    ii = ii +1
  
  #end while
  
#end listStates 

#---------------------------------------------
# isStateActive
#           purpose: return True if state is active
#
def isStateActive(handle,     # instantiation of statechart
                  stateName): # state name
 
  global g_states
    
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
def listTransitions(stateName):   # state name
  #
  # search for statename in transitions
  # print as tuple [index,start,end,event]
  
  global g_xitions
  
  print "(Index, Start, End, Event)"
  ii = 0
  while ii < len(g_xitions):
    if (not g_xitions[ii].disable):
      if (g_xitions[ii].startState == stateName) or (g_xitions[ii].endState == stateName):  
        buf = "[%d,%s,%s,%s]" % (ii+1,g_xitions[ii].startState,g_xitions[ii].endState,g_xitions[ii].event)
        print buf
      #end if  
    #end if
    ii = ii +1
  
  #end while
  
#end listTransitions  
#---------------------------------------------
# startsc
#          purpose: this is a short cut call to instantiating a statechart
#                   because statecharts are created on the fly, each may be
#                   named differently, it may get confusing if one is testing
#                   many statecharts together (regression testing) across known
#                   good design files
#
def startsc():
  global g_handle

  # the name of the statechart is in the design file
  # the next command invokes the object passing in the parameters
  # harvested from the design and assigns it to a handle
  # 
   
  cmd1 = "%s()" % (g_chart_name)
  print "Starting:", cmd1
  handle = eval(cmd1)    # use eval() rather than exec() to return param
  #
  # if comms portion of ini file is set, then subscribe to communication events
  #
  if (g_pio != None):
    print "Subscribing to rabbitmq server"
    handle.subscribe()
  
  g_handle = handle  # the handle is not a string
  return handle
#end startsc

#---------------------------------------------
# help
#    purpose: debugger help
#
def help():
  print
  print " ---------- statechart python debugger------------"
  print 
  print " useful functions:  "
  print 
  print "\t<handle> = startsc() # instantiates statechart"
  print "\t<handle>.subscribe() # registers communication threads"
  print "\tlistStates(<active> =None, True, False)"
  print "\tprint isStateActive(\"<handle>\",\"<state>\")"
  print "\tlistTransitions(\"<state>\")"
  print "\tlistEvents()"
  print "\t<handle>.sendEvent(<event>, [<event_data>])"
  print "\t<handle>.shutdown()"
  print "\thelp()"
  print ""
#end help

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
  print "for help, type help()"
#end recover

#---------------------------------------------
#
#                      main
#
#---------------------------------------------

global g_statetypes      # list of valid state types
global g_states         # list of states and state params
global g_xitions        # list of transitions and transition params
global g_iniPrint       # print to display
global g_initializer    # python commands executed first (typically imports)
global g_iniGenCode     # code generation to file
global g_iniGenCallbacks   # callbacks generation to file
global g_iniInterpret      # starts up python to permit debugging right away
global g_out_file          # state machine output file
global g_des_file          # state machine description file
global g_callbacks_file    # state machine callbacks (separate file)
global g_iniInsertCB       # alternative insert from file
global g_warning_count     # counts warnings
global g_handle            # the entry-point


"""
 the interpreter cannot be defined within a function
 else the imports won't be seen without using
 another name, i.e. name.function() instead of just function()
"""
if __name__ == "__main__":

  eflg = False          # error flag
  
  #
  # spelling of types matches pystatechart parameters
  #
  g_statetypes = StateListObject(concurrent="ConcurrentState", 
                                hierarchical="HierarchicalState", 
                                history="HistoryState", 
                                state="State")
  #
  # warnings are not fatal but
  # should be checked before continuing
  #
  g_warning_count = 0   
    
  opin = optparse.OptionParser()
  
  #
  # note -h help is built-in! 
  #
  opin.add_option("-f", action="store", type="string", dest="des_file")
  opin.add_option("-o", action="store", type="string", dest="out_file")
  
  
  # set defaults
  opin.set_defaults(des_file="", out_file="")
  
  opt, args = opin.parse_args()
  
  # need a design file to begin
  
  g_des_file = opt.des_file
  g_out_file = opt.out_file
  
  # 
  # initialize globals
  #
  g_pio = None         # port input object
  g_pdo = None         # port data object
  g_pco = None         # port config object
  g_evo = None         # events object
  g_spe = None         # suppressed events
  
  #
  # if design file given, then process
  # else print help
  #
  if (len(g_des_file) >0):
      eflg, g_pio, g_pco, g_pdo = get_ini_params(g_des_file)  
      
  else:
      invoke_help()
      eflg = True
  
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
   
  if (not eflg):
  
    #------------------  code generation ---------------------

    
    wfp = None  # write file pointer 
    cfp = None  # callback file pointer
    if (g_iniGenCode):
        today = datetime.datetime.now()
        if (len(g_out_file) ==0):
	  g_out_file = 'iStateChart.py'
	  
	#
	# two files are written:
	# 1) File that contains callbacks (which a user may add to)
	# 2) The statemachine which calls the callbacks
	#
	
	#
	# An ini flag may be set to prevent the generation of callbacks
	# from overwritting user generated code
	#
	base_name = re.sub(".py","",g_out_file)  
	g_callbacks_file = base_name + "_cb.py"
        wfp = open(g_out_file,'w')
	wfp.write('#\n')
	wfp.write('# %s of %s on %s\n' %(g_out_file,g_des_file,today.ctime()))
	wfp.write('#\n')
	
    if (g_iniGenCallbacks):
	#
	# test to prevent accidental overwriting
	#
	file_exists = 1
	try:
	  cfp = open(g_callbacks_file,'r')
	except IOError:                      # file does not exist
	   file_exists =0                    # safe to open write
	   cfp = open(g_callbacks_file,'w')
	   
	if (file_exists == 1):
	  msg = "\n%s will be overwritten, ok? (y,n,q) > " % g_callbacks_file
	  line = raw_input(msg)
	  line = line.upper()
	  line.strip()
          if (len(line)==0):
            print "exiting"
	    quit()
	  if (line[0] == 'Y'):  
	    cfp = open(g_callbacks_file,'w')
	    cfp.write('#\n')
	    cfp.write('# %s of %s on %s\n' %(g_callbacks_file,g_des_file,today.ctime()))
	    cfp.write('#\n')
	  elif (line[0] == 'N'):
	    cfp = None   # continue, skip writing to callbacks file 
	  else:
	    print "exiting"
	    quit() 	
	
    #------------------ code imports ---------------------
   
    ii =0
    while (ii < len(g_initializer)): 
      init_buf = g_initializer[ii]
      if (g_iniPrint):  
        print(init_buf)
      if (g_iniGenCode):
        wfp.write(init_buf + '\n')
      ii = ii +1
      #end while
  
    #------------------  code event classes ---------------------
  
    counting_idx = 0            # used if no base
    for event_set in g_evo:
      
      evbuf = "class" + " " + event_set.name + ":\n"
      
      event_offset = int(event_set.base)
      
      ii = 0
      while (ii < len(event_set.events)):
        evline = "  %s = %d\n" % (event_set.events[ii],ii + event_offset)
        evbuf = evbuf + evline 
        ii = ii+1
      #  end while inner loop
         
      if (g_iniPrint):  
        print evbuf,   # comma is newline suppression
      if (g_iniGenCode):
        wfp.write(evbuf)      
      
    #end while outer loop
           
      
  
    #------------------ code state callbacks ------------------
    #
    # for each state entry, do, and exit
    # if method present, if unique create empty call with method as name
    # if list, add event calls after  method declaration
    #
    ulist = []   # unique list
  
    g_funcFromFile = None                       # this is an object used in replacing callbacks
    if (len(g_iniInsertCB) != 0):               # this is the name of the callbacks file
      g_iniInsertCB = g_iniInsertCB.strip()     # cleanup
      if (g_iniInsertCB == 'None') or (g_iniInsertCB == 'False'):  # indicates no file, not a filename
        g_iniInsertCB = None
      else:
        g_funcFromFile = funcFromFile(g_iniInsertCB)
      
    
    #
    # entry
    #   
    stat, ulist = gen_code_hooks(g_pdo,g_evo,cfp,ulist,g_states,"entry",0)
    if (stat !=0):
       print "error in file: %s" % (g_des_file)  # error in ini file
       quit()
  
    #
    # do
    #
    stat, ulist = gen_code_hooks(g_pdo,g_evo,cfp,ulist,g_states,"do",0)
    if (stat !=0):
       print "error in file: %s" % (g_des_file)  # error in ini file
       quit()
      
    #
    # exit
    #    
    stat, ulist = gen_code_hooks(g_pdo,g_evo,cfp,ulist,g_states,"exit",0)
    if (stat !=0):
       print "error in file: %s" % (g_des_file)  # error in ini file
       quit()
    
    #------------------ code transition callbacks ------------------  
    
    # 1. check for validity of events 
    # 2. calls for guard  
    # 3. calls for action, actions may be in list
     
    #
    # look for illegal conditions (event declarations) in transitions
    #
    ii = 0
    while (ii < len(g_xitions)):  
        if (not g_xitions[ii].disable) and (g_xitions[ii].event != 'None'):
          #
          # "Event(class_name.event_name,<optional_params>)"
          #
          phrase = g_xitions[ii].event      # index to event
          idx1 = phrase.find("Event(")        
          if (idx1 != -1):   # read until close parens or comma 
            print "*** Error: Event declarations not allowed in Transitions. %s ***" % phrase
            print "error in design file: %s" % g_des_file
            quit()
                        
          #end if event found
          
        #end if not None  
        
        ii = ii+1    # next transition
      
    #end while outer loop
   
    #
    # guards in transitions
    #
    stat, ulist = gen_code_hooks(g_pdo,g_evo,cfp,ulist,g_xitions,"guard",0)
    if (stat !=0):
       print "error in file: %s" % (g_des_file)  # error in ini file
       quit()
    #
    # transition action, can be used for generating debugging messages
    #  
    stat, ulist = gen_code_hooks(g_pdo,g_evo,cfp,ulist,g_xitions,"action",1)
    if (stat !=0):
       print "*** Error: Design file: %s ***" % (g_des_file)  # error in ini file
       quit()  
       
    if (g_funcFromFile != None):
      err_f, missingList = g_funcFromFile.findMissing()
      if (err_f):
        print "*** Error in file: %s, defined in file: %s ***" %(g_iniInsertCB,g_des_file)
        quit()
        
      if (missingList != []):
        g_warning_count = g_warning_count +1
        print "*** Warning #%d:  function(s):%s, in file:%s ***" %(g_warning_count, 
                                                                   missingList,
                                                                   g_iniInsertCB)
        print "not found in file:", g_des_file
        
       
    #------------------ insert user designed callbacks -------------
    
    if (g_iniGenCode):
    
      if cfp != None:  # close file
         cfp.write("# end of callbacks file\n")
         cfp.close()
	 
      # callback file is subset
      # can't be imported, must be inserted
      
      cfp = open(g_callbacks_file,"r")
      
      line = " "    # loop initializer
      while (line != ""):
        line = cfp.readline()
        wfp.write(line)
	
      cfp.close()	

    #------------------ the statechart class ------------------- 
  
    # topmost class and states
  
    buf1 = "class %sStatechart(Statechart):" %(g_chart_name)
    buf2 = "  def __init__(self,param):"
    buf3 = "    Statechart.__init__(self,param)"
    
    if (g_iniPrint):
      print buf1
      print buf2
      print buf3
    if (g_iniGenCode):
      wfp.write(buf1 + "\n")
      wfp.write(buf2 + "\n")
      wfp.write(buf3 + "\n")
  
    # if state's parent is 'None', then code 'self'
  
    # -------------- statechart state declarations -----------------
  
    ii =0
    while (ii<len(g_states)):
      if (g_states[ii].disable):   # skip disabled
        ii = ii + 1
        continue
      state_set = g_states[ii]  # unpack ini list
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
      if (g_iniPrint):
        print buf
      if (g_iniGenCode):
        wfp.write(buf + "\n")	
      
      ii = ii +1
    #end while
  
    # -------------- statechart transition declarations -----------------
      
    ii =0
    startUnique=0                # make startState objects unique
    startList =[]                # list of start states and  parents
    while (ii<len(g_xitions)):   # while there are transitions
    
      xition_set = g_xitions[ii]  # unpack the transition
      
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
        xparent,err = parent_state(xend)
        if (err<0):
          print "*** Error: in design file: %s, Parent of %s not found ***" % (g_des_file,xend)
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
        match_f, startSet = NamedObject.namedListMatch(startList,"parentState",xparent)
        if (match_f):
          xstart = startSet.startState   # use the previously used value
          skip_f = True                  # do not create a new start object for the transition
        else:                            # save in list to be tested against
          startList = startList + [ StartStateObject(startState=xstart,parentState=xparent) ]
          
        if (not skip_f):
          buf1 = "    %s = StartState(%s)" % (xstart,xparent) 
          if (g_iniPrint):
            print buf1
          if (g_iniGenCode):
            wfp.write(buf1 + "\n")
      	   
      elif (xend == "end"):
        xend = "endState"        # arbitrary but consistent label change
        xparent,err = parent_state(xstart)
        if (err<0):
           print "*** Error: in design file: %s, Parent of %s not found ***" % (g_des_file,xstart)
           quit()
        if (xparent == "None"):
          xparent = "self"
        else:
          print "*** Error: in design file: %s ***" % (g_des_file)
          print "Only one end state is permitted. Parent: %s is not top state" % (xstart)
          quit()
        
        buf2 = "    %s = EndState(%s)" % (xend,xparent)
        if (g_iniPrint):
          print buf2
        if (g_iniGenCode):
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
      if (g_iniPrint):
        print buf3
      if (g_iniGenCode):
        wfp.write(buf3 + "\n")	
  	
      ii = ii+1
    #end while Transitions
       
    
    # -------------- begin statechart class -----------------
    
    #
    # Note: 1. logger may not be present, if present then shut down before statechart thread 
    #          because logger depends on statechart thread
    # 
    # Note 2. communication methods depend on presence of comms setup
    
    mbuf2 = []
    if (g_pio != None):
      tbuf = "import json"                                         ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "class %s(object):" %(g_chart_name)                     ; mbuf2 = mbuf2 + [tbuf]           	      
    tbuf =  "    def sendEvent(self, event_id, event_data=None):"  ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "        self.lock.acquire()"                           ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "        event = Event(event_id, event_data)"           ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "        self.events.append(event)"                     ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "        self.lock.release()"                           ; mbuf2 = mbuf2 + [tbuf]
   
    tbuf = "    def shutdown(self):"                               ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "        if (self.txtlog != None): "                    ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "          self.txtlog.put(EL.LogStatusEvent(\'shutting down logger\'))" ;mbuf2 = mbuf2 + [tbuf]
    tbuf = "          time.sleep(1)"                      ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "          self.txtlog.shutdown()"                      ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "        print \"Shutting down statechart thread...\""  ; mbuf2 = mbuf2 + [tbuf]
    tbuf = "        self.thread.shutdown()"                        ; mbuf2 = mbuf2 + [tbuf]      
    
    if (g_pio != None):
      tbuf = "    def sendEventAsMsg(self,port_name,event_id,event_data=None):" ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "       err_f, clist, plist = PortObject.getPortOutParams\
(self.pco,self.pdo,port_name)"                                      ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "       if (not err_f):"                                 ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "          m_f, evStr = EventObject.idToEvent(self.evo,event_id)"    ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "          if (not m_f):"                                      ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            emsg = \'*** Error: sendEventAsMsg, no conversion. ***\\n\'" ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            emsg = emsg + \'%d: unrecognized event\'%(event_id)"         ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            err_f=True"                                 ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "       if (not err_f):"                                 ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "          if (plist.event_id==\'AnyEvent\'):"           ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            err_f = self.comm.Put(evStr,plist.port,clist.msg_tag)" ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "          elif (plist.event_id==\'JsonData\'):"         ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            dataStr=\'\'"                             ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            if (event_data!=None):"                   ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "              dataStr = json.dumps(event_data)"       ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "              evStr = evStr+\':\'+dataStr"            ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            err_f = self.comm.Put(evStr,plist.port,clist.msg_tag)" ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "          elif (plist.event_id==evStr):"              ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            err_f = self.comm.Put(evStr,plist.port,clist.msg_tag)" ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "          else:"                                        ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            emsg = \'*** Error: sendEventAsMsg, no conversion. ***\\n\'" ; mbuf2 = mbuf2 + [tbuf] 
      tbuf = "            emsg = emsg + \"%s, %s: (rd,[exp]):(%s,[\'AnyEvent\',\'JsonData\'])\" % \
(port_name,evStr,plist.event_id)"                                   ; mbuf2 = mbuf2 + [tbuf] 
      tbuf = "            if (self.txtlog!=None):"                    ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "              self.txtlog.put(EL.LogStatusEvent(emsg))" ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            else:"                                      ; mbuf2 = mbuf2 + [tbuf] 
      tbuf = "              print emsg"                               ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "            err_f=True"                                 ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "       if (not err_f):"                                 ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "         lmsg = \'message queue: %s\' % evStr"          ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "         if (self.txtlog!=None):"                       ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "           self.txtlog.put(EL.LogStatusEvent(lmsg))"    ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "         else:"                                         ; mbuf2 = mbuf2 + [tbuf] 
      tbuf = "           print lmsg"                                  ; mbuf2 = mbuf2 + [tbuf]    
      tbuf = "       return err_f"                                    ; mbuf2 = mbuf2 + [tbuf]   
    
      tbuf = "    def getMsgSendEvent(self,port_name):"              ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "       err_f, event_f = PortObject.getMsgSendEvent(self,\
port_name, self.evo[0],self.pco, self.pdo)"                          ; mbuf2 = mbuf2 + [tbuf]
      tbuf = "       return err_f, event_f"                          ; mbuf2 = mbuf2 + [tbuf] 
    
    # -------------- print and generate code from buffers -----------------
                 
    if (g_iniPrint):                # print code to display
      ii = 0
      while (ii < len(mbuf2)):         
         print mbuf2[ii]
	 ii = ii + 1 
	       
    if (g_iniGenCode):              # generate python code
      ii = 0
      while (ii < len(mbuf2)):         
         wfp.write( mbuf2[ii] + "\n") 
	 ii = ii + 1 
    
    # -------------- comms callbacks for subscribe ------------------
    
    g_cbo = None
    if (g_pio != None):
      g_cbo = genCommCallbacks(g_pdo,      # port data object
                               g_evo,      # event object
                               wfp)        # file print object   
                               
    
    # -------------- subscribe method ------------------

    mbuf3 = []    
    if (g_pio != None):
      tbuf = "    def subscribe(self):"
      mbuf3 = mbuf3 + [tbuf] 
      ii =0
      while (ii<len(g_cbo)):
        tbuf = "      self.comm.Subscribe(\"%s\",self.%s)" % (g_cbo[ii][0],g_cbo[ii][1])
        mbuf3 = mbuf3 + [tbuf] 
        ii = ii + 1 
                               
    # ---------------------    __init__       --------------------
   
    
    tbuf = "    def __init__(self):"                      ; mbuf3 = mbuf3 + [tbuf]
      
    # -------------- event object -----------------
     
    tbuf = "        self.evo = []"              ; mbuf3 = mbuf3 + [tbuf]
    ii = 0
    while ii < len(g_evo):
        tbuf = "        self.evo = self.evo +[EventObject(file=\"%s\",name=\"%s\",events=%s,ids=%s)]" % (
                          g_evo[ii].file,
                          g_evo[ii].name,
                          g_evo[ii].events,
                          g_evo[ii].ids)         ; mbuf3 = mbuf3 + [tbuf]                       
        ii = ii +1  
    
    # -------------- suppressed printing events -----------------
     
    tbuf = "        self.spe = []"                                ; mbuf3 = mbuf3 + [tbuf]
    if (g_spe != None):
      ii = 0
      while ii < len(g_spe):
        tbuf = "        self.spe = self.spe +[%s]" % (g_spe[ii])  ; mbuf3 = mbuf3 + [tbuf]                       
        ii = ii +1                     

    # -------------- statechart and thread are dependent on event object -----------------
    
    tbuf = "        self.events = list()"                 ; mbuf3 = mbuf3 + [tbuf]
    tbuf = "        self.lock = Lock()"                   ; mbuf3 = mbuf3 + [tbuf]
    tbuf = "        self.txtlog = None"                   ; mbuf3 = mbuf3 + [tbuf]
    tbuf = "        self.statechart = %sStatechart(self)" % (g_chart_name) ; mbuf3 = mbuf3 + [tbuf]
    tbuf = "        self.statechart.start()"              ; mbuf3 = mbuf3 + [tbuf]
    tbuf = "        self.thread = StatechartThread(self)" ; mbuf3 = mbuf3 + [tbuf]
    tbuf = "        self.thread.start()"                  ; mbuf3 = mbuf3 + [tbuf]
  
    # -------------- print and generate code from buffers -----------------
    
  	       
    if (g_iniPrint):  # print python code to display
      ii = 0
      while (ii < len(mbuf3)):         
         print mbuf3[ii]
	 ii = ii + 1 	 
             
    if (g_iniGenCode):      # generate python code
      ii = 0
      while (ii < len(mbuf3)):         
         wfp.write( mbuf3[ii] + "\n") 
	 ii = ii + 1
    
    # ---------------------    comms params in __init__    --------------------
 
    if (g_pio != None):
       # simple transfer, not a list of objects 
      mbuf4 = []
      tbuf = "        self.pio = %s" % g_pio.list         ; mbuf4 = mbuf4 + [tbuf]
      #
      # The ini file leads directly to the embedded pystatechart code
      # but apparently not the comms parameters, which need to be transfered
      # piece by piece, the whole point of which is to decouple scb.py to <unique_design>.py
      #
      tbuf = "        self.pco = []"              ; mbuf4 = mbuf4 + [tbuf]
      ii = 0
      while ii < len(g_pco):
        tbuf = "        self.pco=self.pco+\
[PortConfigObject(channel_id=\"%s\",exchange=\"%s\",type=\"%s\",queue=\"%s\",msg_tag=\"%s\")]" % (
                          g_pco[ii].channel_id,
                          g_pco[ii].exchange,
                          g_pco[ii].type,
                          g_pco[ii].queue,
                          g_pco[ii].msg_tag)        ;  mbuf4 = mbuf4 + [tbuf]                       
        ii = ii +1
      tbuf = "        self.pdo = []"              ; mbuf4 = mbuf4 + [tbuf]
      ii = 0
      while ii < len(g_pdo):
        tbuf = "        self.pdo = self.pdo +\
[PortDataObject(name=\"%s\",type=\"%s\",port=\"%s\",event_id=\"%s\")]" % (
                          g_pdo[ii].name,
                          g_pdo[ii].type,
                          g_pdo[ii].port,
                          g_pdo[ii].event_id)      ; mbuf4 = mbuf4 + [tbuf]                       
        ii = ii +1
      
      #    
      # NOTE: host, userid, password all need quotes
      #
      #
      tbuf = "        self.comm = %s.CommObject(host=\'%s\',userid=\'%s\',password=\'%s\')" %  (g_pio.import_name,
                        g_pio.host,  g_pio.userid, g_pio.password)                       ;  mbuf4 = mbuf4 + [tbuf]                                                                       
      tbuf = "        self.comm.ConfigureList(%s)" % (NamedObject.combineLists(g_pco)) ;  mbuf4 = mbuf4 + [tbuf]      
        
    
    # -------------- print and generate code from buffers -----------------
    
  	       
    if (g_iniPrint and (g_pio != None)):  # print python comms code to display
      ii = 0
      while (ii < len(mbuf4)):         
         print mbuf4[ii]
	 ii = ii + 1 	 
             
    if (g_iniGenCode and (g_pio != None)):      # generate python comms code
      ii = 0
      while (ii < len(mbuf4)):         
         wfp.write( mbuf4[ii] + "\n") 
	 ii = ii + 1
         
    if (g_iniGenCode):
      wfp.close()                   # close file holding generated code
     	 	 	    

    # -------------- the interpreter -----------------
     
    if (g_iniInterpret):                                 
      g_handle = None                            
      import_name = re.sub(".py","",g_out_file)		# strip .py off output file name		 
      cmd = "from %s import *" %(import_name)           # create a command to import the file 
      exec(cmd)                                         # execute that command 
      if (g_warning_count >0):                          # if warnings then
        print "\nWarnings=%d" % g_warning_count         # offer option to quit 
	line = raw_input("Continue? (y,q) > ")
	line = line.upper()
	line.strip()
	if (line[0] == 'Y'):             # keep going
	    pass
	else:
	  print "exiting"                # quit
	  quit() 	
      
      help()                             # display help
      
      while 1:                           # loop forever, or until quit()
        line = raw_input(" scb > ")      # get input
        line = line.lstrip()             # strip leading whitespace
	try:                             
          exec(line)                     # execute as python command
	except Exception as eobj1:       # don't exit if command fails
          eobj_bis = MyException(eobj1)  # convert obj to string extractable
          emsg = eobj_bis.__str__()      # get the error string
          #
          # this is a way of bypassing having to name the statechart
          # when using the statechart methods
          #
          if (emsg.find("NameError") >= 0) and \
             (emsg.find("is not defined") >= 0) and \
             (g_handle != None):  
             
            line = "g_handle." + line       # prefix is statechart handle
            
            try:
              exec(line)
            except Exception as eobj2:
              recover(eobj1)         # first error is more signficant
          else:
            recover(eobj1)
          
    
  # -------------------  the end --------------------------------
  
