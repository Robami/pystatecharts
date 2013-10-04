
"""
 rps 4/13/2011
 MIT Haystack Observatory
 
 Design:
 
 The purpose of this file is that every object which can be imported
 into the scb code generator doesn't have to be copied into the 
 generated code if it can be imported into the generated code.
  - This is the subset that is needed

 ---------------------------------------------
                                 	  
 class NamedObject:
  functions:
    indexListMatch                      - uses key to return index and list from list_of_lists
    namedListMatch          		- uses key to return list from list_of_lists     
    combineLists            		- debug utility  
    
 class EventObject(NamedObject):
   functions:
     idToEvent                          - converts event id to event name
     EventToId                          - converts name to id
     updateList                         - updates values returned by combineLists
 
 class XitionsObject(NamedObject)       - statechart transition object
 
 class StatesObject(NamedObject)        - statechart state object

 class CommonPortObject(NamedObject)    - object utilities common to rabbitmq and zeromq
 
"""

from scbUtilities import *   # isInlist

#---------------------------------------------  
#---------------------------------------------
#
# data structure as a class used to convert global data into an object
# as named objects are easier to extend/maintain than ordered lists 
# - all objects of this type have common operators and operators act on common objects
#

class NamedObject():

  #---------------------------------------------
  @staticmethod  
  def indexListMatch(list_of_lists, name, value, name2=None, value2=None, unique_f=False):
       #
       # for each list's <element> attribute compare with value
       # if match, return  True plus list
       # else return  False plus empty list
       # 
       # search needs to be named part of class for object else .<value> is unrecognized
       #
       # unique_f finds non-uniqueness
    
  
       index = []                       # return empty indices
       list_data = []                   # return empty list
       ii = 0
       for theList in list_of_lists:
      
         cmd0 = "theList.%s == value" % (name)
         cmd1 = "isInlist(theList.%s,value)" % name
                                   # if name is valid then 
                                   # match name against value
                                   # match name (as list) against value                          
         if (eval(cmd0) or eval(cmd1)):                            
           if (name2 != None):
              cmd2 = "theList.%s == value2" % name2
              cmd3 = "isInlist(theList.%s,value2)" % name2
              if (eval(cmd2) or eval(cmd3)):
                 if (unique_f):
                   index = index + [ii]
                   list_data = list_data + [theList]   # save list of lists if non-unique
                                                       # don't exit on match, may be non-unique
                 else:
                   list_data = theList                 # save the list
                   index = [ii]
                   break 
           else:
             if (unique_f): 
               index = index + [ii]
               list_data = list_data +  [theList]      # list of lists if non-unique
             else:
               list_data = theList 
               index = [ii]
               break                                   # exit on match   
         #endif  
         ii = ii + 1             
       #end for
      
       return index, list_data      # return indices of matches and list (or list of lists)
    
  #end indexListMatch

  #---------------------------------------------
  @staticmethod  
  def namedListMatch(list_of_lists, name, value, name2=None, value2=None, unique_f=None):
       #
       # for each list's <element> attribute compare with value
       # if match, return  True plus list
       # else return  False plus empty list
       # 
       # search needs to be named part of class for object else .<value> is unrecognized
       #
       # unique_f finds non-uniqueness ('None' is same as False)
 
       match_f = False
       list_data = []                   # initialize
    
       for theList in list_of_lists:
      
         cmd0 = "theList.%s == value" % (name)
         cmd1 = "isInlist(theList.%s,value)" % name
                                   # if name is valid then 
                                   # match name against value
                                   # match name (as list) against value                          
         if (eval(cmd0) or eval(cmd1)):                            
           if (name2 != None):
              cmd2 = "theList.%s == value2" % name2
              cmd3 = "isInlist(theList.%s,value2)" % name2
              if (eval(cmd2) or eval(cmd3)):
                 match_f = True
                 if (unique_f):
                   list_data = list_data + [theList]   # save list of lists if non-unique
                                                       # don't exit on match, may be non-unique
                 else:
                   list_data = theList                 # save the list
                   break 
           else:
             match_f = True 
             if (unique_f): 
               list_data = list_data +  [theList]      # list of lists if non-unique
             else:
               list_data = theList 
               break                                   # exit on match   
         #endif               
       #end for
      
       return match_f, list_data      # return match, and list (or list of lists)
    
  #end namedListMatch
  
  #---------------------------------------------
  @staticmethod  
  def combineLists(object):
       #
       # used for dumping elements in list of lists for debugging
       #
       ret_list =[]
       ii = 0
       while ii < len(object):
         ret_list = ret_list + [object[ii].list] # not a real list, so can't use built-in list iterator
         ii = ii + 1
       return ret_list
    
  # end combineLists 

#---------------------------------------------   
#---------------------------------------------  

class EventObject(NamedObject):   
    def __init__(self, file=None, base=None, name=None, events=[], ids =[]):
       self.file    = file             # statechart file (needed for recognizing event object)
       self.base    = base             # event value = base + index in event list
       self.name    = name             # class name
       self.events  = events           # list of events
       self.ids     = ids              # event.id = base plus index 
       self.list = [self.file, self.base, self.name, self.events, self.ids] 
    #
    # next method can't be static - it acts on self
    # event ids are generated after ini file is read, and after init
    # and after tests are made to prevent id collisions
    #  
    def updateList(self):
       self.list = [self.file, self.base, self.name, self.events, self.ids]
    
    #
    # given a list of list of events, search for the event id, 
    # if found, then return the event class and event name
    #
    @staticmethod   
    def idToEvent(list_of_lists,id): 
       idx = -1
       match_f = False
       event_class = ""
       event_name = ""
       event_full = ""
       match_f, event_list = NamedObject.namedListMatch(list_of_lists,"ids",id)
       if(match_f):
         idx = event_list.ids.index(id)  # list index, not string index
         if (idx <0):
           match_f =False
         else: 
           event_class = event_list.name
           event_name = event_list.events[idx]
           event_full = event_class + "." + event_name
         
       return match_f, event_full
    # end idToEvent
    
    @staticmethod   
    def EventToId(list_of_lists,event_name): 
       ridx = -1       
       #
       # separate into class and event, ex. <class>.<event>
       #
       event_name = event_name.strip()
       pieces = event_name.rsplit('.')
       ec = pieces[0]
       en = pieces[1]
       match_f = False
       #
       # find list defining event class
       #
       match_f, event_list = NamedObject.namedListMatch(list_of_lists,"name",ec)
       #
       # find index of event from name then find event value from index
       # 
       if (match_f):
         try:
           nidx = event_list.events.index(en)  # list index, not string index
         except Exception as eobj:
           match_f = False
           print "EventToId: ", eobj
       if (match_f):
          try:
             ridx = event_list.ids[nidx]
          except Exception as eobj:
             match_f = False
             print "EventToId: ", eobj
       return ridx
# end class EventObject  

#---------------------------------------------  
#---------------------------------------------     

class XitionsObject(NamedObject):   
    def __init__(self, name=None,
                        startState=None, 
                        endState=None, 
                        event=None, 
                        guard=None,
                        action=None,
                        disable=None):
       self.name        = name            # ini section, param 1, index 0
       self.startState  = startState      # parameter 2, index [1]
       self.endState    = endState        # parameter 3
       self.event       = event           # parameter 4
       self.guard       = guard           # parameter 5
       self.action      = action          # param 6, index 5
       self.disable     = disable         # param 7, index 6
       self.list = [self.name,  self.startState, self.endState, 
                    self.event, self.guard,      self.action, self.disable ]  
#end class XitionsObject 

#---------------------------------------------  
#---------------------------------------------

class StateListObject(NamedObject):   
    def __init__(self, concurrent=None, hierarchical=None, history=None, state=None):
       self.concurrent    = concurrent        
       self.hierarchical = hierarchical     
       self.history      = history
       self.state        = state
       self.list = [self.concurrent, self.hierarchical, self.history, self.state  ] 
#end class StateListObject   

#---------------------------------------------     

class StatesObject(NamedObject):   
    def __init__(self, name=None, 
                       parent=None, 
                       type=None, 
                       entry=None, 
                       do=None, 
                       exit=None,
                       disable=None):
       self.name   = name      # statechart call parameter 1, index [0]
       self.parent = parent    # parameter 2
       self.type   = type      # parameter 3
       self.entry  = entry     #           4
       self.do     = do        #           5
       self.exit   = exit      #           6, index [5]
       self.disable = disable  # param     7, index [6]
       self.list = [self.name, self.parent, self.type, self.entry, self.do, 
                    self.exit, self.disable ]  
#end class StatesObject 
        
#---------------------------------------------     

class StartStateObject(NamedObject):   
    def __init__(self, startState=None, parentState=None):
       self.startState   = startState         # name of start object
       self.parentState  = parentState        # parent
       self.list = [self.startState, self.parentState ] 
#end class StartStateObject          

#--------------------------------------------- 
#--------------------------------------------- 

class CommonPortObject(NamedObject):
  #---------------------------------------------
  @staticmethod  
  def getPortEventValidIDs():
    return ['AnyEvent','JsonData','YamlData']    # these params tell how to pack/unpack data for socket

  #---------------------------------------------
  @staticmethod
  def isPortEventValid(event_id):
     return isInlist(CommonPortObject.getPortEventValidIDs(),event_id)

#---------------------------------------------     

class IniRpcObject(NamedObject):   
    def __init__(self, enable=False,
                       ip=None,
                       port=None,
                       server=None,
                       client=None,
                       skiplist=[]):
       self.enable = enable     # enable rpc processing
       self.ip     = ip         # ip address
       self.port   = port       # ip port
       self.server = server     # server, python file
       self.client = client     # client, client classes
       self.skiplist = skiplist # don't process as rpc's
       self.list = [self.enable, self.ip, self.port, self.server, self.client, self.skiplist ] 
#end class IniRpcObject

##############################################################################
if __name__ == "__main__":
  print "scbObjects ran ok"
  
  
