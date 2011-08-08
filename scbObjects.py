
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
    namedListMatch          		- search utility    
    combineLists            		- debug utility  
    
 class EventObject(NamedObject):
   functions:
     idToEvent                          - converts event id to event name
     EventToId                          - converts name to id
     updateList                         - updates values returned by combineLists
 
 class XitionsObject(NamedObject)
 
 class StatesObject(NamedObject)
 
 class PortObject(NamedObject): 
  functions:
    getPortOutParams	       		- sends a message through a port 
    getPortInParams             	- gets a message from a port 
    getMsgSendEvent			- convert a rabbitmq message into a statechart event
 
 class PortInitObject(PortObject):    	- parameters that go to the rabbitmq init call
 derived from: PortObject
  functions:
    
 class PortDataObject(PortObject):     	- params that go to the rabbitmq port datad deffn
 derived from: PortObject
  functions:
    
 class PortConfigObject(PortObject):   	- params that go to rabbitmq port config deffn          
 derived from: PortObject
  functions:
  
 class CallbackObject(NamedObject):          - used for generating communication callbacks
 			 
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
  def namedListMatch(list_of_lists, name, value, name2=None, value2=None, unique_f=None):
       #
       # for each list's <element> attribute compare with value
       # if match, return  True plus list
       # else return  False plus empty list
       # 
       # search needs to be named part of class for object else .<value> is unrecognized
       #
       # unique_f finds non-uniqueness
    
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
#---------------------------------------------     

class StartStateObject(NamedObject):   
    def __init__(self, startState=None, parentState=None):
       self.startState   = startState         # name of start object
       self.parentState  = parentState        # parent
       self.list = [self.startState, self.parentState ] 
#end class StartStateObject          
#---------------------------------------------   
#---------------------------------------------  

class PortObject(NamedObject): 
     
  #---------------------------------------------
  @staticmethod  
  def getPortOutParams(pco,               # port config object
                       pdo,               # port data object 
                       port_name):        # port name                
  
    #
    # check for validity of port 
    #
    err_f = False
    port_list = []
    config_list = []
    exchange = None
    routing_key = None
    match_f = False
    match_f, port_list = NamedObject.namedListMatch(pdo,"name",port_name)
    if (not match_f):
      print "unrecognized port:", port_name, "in port data:"
      print NamedObject.combineLists(pdo)    
      err_f = True
    else:
      #
      # make sure port is an output port 
      #
      if (port_list.type != 'output'):
        print "port is read-only"
        err_f = True
    #
    # get exchange and tag from configuration
    #   
    if (not err_f):
      #
      # search the configuration for matching exchange
      #   
      match_f = False
      exchange = port_list.port
      routing_key = ""
      match_f, config_list = NamedObject.namedListMatch(pco,"exchange",exchange)
      
      if (not match_f):
        print "unrecognized exchange", exchange, "in config data:"
	print NamedObject.combineLists(pco)
        err_f = True
      else:
        routing_key = config_list.msg_tag
      
    # returned elements are combined from pco, pdo lists
    
    return err_f, config_list, port_list
     
  # end getPortOutParams
  #---------------------------------------------
  @staticmethod
  def getPortInParams(pco,           # port config object
                      pdo,           # port data object
                      port_name):    # port name
  
    #
    # check for validity of port 
    #
    err_f = False
    port_list = []
    queue = None
    match_f = False
    match_f, port_list = NamedObject.namedListMatch(pdo,"name",port_name)
    if (not match_f):
      print "unrecognized port:", portname, "in port data:"
      print NamedObject.combineLists(pdo) 
      err_f = True
    else:
      #
      # make sure port is an output port 
      #
      if (port_list.type != 'input'):
        print "port is write-only"
        err_f = True
    #
    # get exchange and tag from configuration
    #   
    if (not err_f):
        #
        # search the configuration for matching exchange
        #   
        match_f = False
        queue = port_list.port
        match_f, config_list = NamedObject.namedListMatch(pco,"queue",queue)
      
        if (not match_f):
          print "unrecognized queue", queue, "in config data:"
          print NamedObject.combineLists(pco)
          err_f = True
  	
    if (not err_f):
      return err_f,  config_list, port_list
        
  # end getPortInParams
  
  #---------------------------------------------
  @staticmethod
  def getMsgSendEvent(handle,      # pass thru - handle to state chart object
		      port_name,   # port name
		      event_set,   # event info for event construction
		      pco,         # port config object
		      pdo):        # port data object		          
    #
    # read message at port
    # if message then convert message to event
    # send event
  
    err_f = False
    msg_f = False
    message = ""
    event_f = False
    config_list = []
    port_list = []
  
    
    err_f, config_list, port_list = PortObject.getPortInParams(pco, pdo, port_name)
  
    if (not err_f):
       err_f, msg_f, message = handle.comm.Get(config_list.queue)
   
    #
    # if message is in port data list, then send event
    #
    
    if (not err_f) and (msg_f):
       if (message == port_list.msg):
         #
         # verify validity of event
         #
	 if (not isInlist(event_set.events,port_list.event_id)):
	   print "unrecognized event: %s, in: %s" % (port_list.event_id, event_set.events)
	   err_f = True
	 else:	   	            
           #
	   # generate and execute event command (not as simple as it seems)
	   #
	   # - the problem is the event type is not known inside this class
	   # - the solution is to import the class
	   # - the problem with the solution is the class is generated code and
	   #   not directly known - what class to import and file to  import from 
	   #
	   # - from the design file, use the [STATECHART] name-tag for the file to import
	   #   (saved inside the event set as file-tag)
	   # - from the event set, use the name-tag for the class to import
	   # - generate and execute the import command
           # - generate and execute the send even command
	   
	   #
	   # import class of event
	   #
	   buf1 = "from %s import %s" % (event_set.file, event_set.name)
	   exec(buf1)
	   
	   #
	   # send event
	   #
           buf2 = "handle.sendEvent(%s.%s,%s)" % (event_set.name,
                                                  port_list.event_id)                  
	   exec(buf2)
           event_f = True   
        
    return err_f, event_f
    
  #end getMsgSendEvent

#end class     
#---------------------------------------------      
#---------------------------------------------

class PortInitObject(NamedObject):
    def __init__(self, import_name=None, host=None, userid=None, password=None):
      self.import_name = import_name
      self.host        = host
      self.userid      = userid
      self.password    = password
    
      self.list = [import_name, host, userid, password]  # access by name or index    
      
  # end PortInitObject
#---------------------------------------------
#---------------------------------------------       
class PortDataObject(PortObject):
     
     def __init__(self, name=None, type=None, port=None, event_id=None):
       self.name     = name
       self.type     = type
       self.port     = port 
       self.event_id = event_id
       self.list = [name, type, port, event_id] # access by name or index   
     
  # end PortDataObject
#--------------------------------------------- 
#---------------------------------------------
  
class PortConfigObject(PortObject):
     def __init__(self, channel_id=None, exchange=None, type=None, queue=None, msg_tag=None):
       self.channel_id = channel_id
       self.exchange = exchange
       self.type     = type
       self.queue    = queue
       self.msg_tag  = msg_tag
   
       self.list = [channel_id, exchange, type, queue, msg_tag] 
   
# end PortConfigObject
#--------------------------------------------- 
#---------------------------------------------

class CallbackObject(NamedObject):
    def __init__(self, queue=None, event_id=None):
      self.queue      = queue       # messasge queue queue
      self.event_id   = event_id    # event id, including class
         
      self.list = [queue,event_id]  # access by name or index 
      
  # end CallbackObject
  
#--------------------------------------------- 

##############################################################################
if __name__ == "__main__":
  print "scbObjects ran ok"
  
  
