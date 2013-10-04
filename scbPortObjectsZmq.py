
"""
 rps 5/30/2012
 MIT Haystack Observatory
 
 Design:
 
 The purpose of this file is that every object which can be imported
 into the scb code generator doesn't have to be copied into the 
 generated code if it can be imported into the generated code.
  - This is the subset that is needed.

 ZeroMQ port definition as objects

 ---------------------------------------------
                                 	  
 
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
  
 class CallbackObject(NamedObject):          - used for generating communication callbacks
 			 
"""

from scbUtilities import *   # isInlist
from scbObjects   import *
from pyzeromq import CommObject as cmo  # valid socket types

#---------------------------------------------  
#---------------------------------------------
#
# data structure as a class used to convert global data into an object
# as named objects are easier to extend/maintain than ordered lists 
# - all objects of this type have common operators and operators act on common objects
# - object methods that don't use "self" can be used BEFORE objects are instantiated
#
 

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
    config_list = []  # zeromq has no configuration list
    exchange = None
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
      try:
        cmo.outputSocketTypes().index(port_list.type)
      except ValueError:
        print "Output socket type error.",port_list.type,
        "found, one of:",cmo.outputSocketTypes(),"expected"
        err_f = True  
    #
    # Note: Rabbitmq communication is via one comm object containing all
    #       exchanges, queues, and channels 
    #       - identifying info is held in the configuration list.
    #
    #       Zeromq creates one object per comms channel.
    #       - identifying information is in the comm object (not config) as a list.
    #         the config list here is used as the index into the comm object list
    #         (this is just a teeny bit of hackery to make the two (rabbit and zero)
    #          compatible without having to rewrite all the code)

    #
    # indexListMatch() returns index of comms object 
    # conditions were pre-tested by namedListMatch (which doesn't return the index)
    #
    if (not err_f):
      indices, port_list = NamedObject.indexListMatch(pdo,"name",port_name,unique_f=True)
      config_list = config_list + indices

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
      # make sure port is an input port 
      #
      try:
        cmo.inputSocketTypes().index(port_list.type)
      except ValueError:
        print "Input socket type error:", port_list.type, 
        "found, one of",cmo.inputSocketTypes(),"expected"
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
    def __init__(self, import_type, import_name):
      self.import_type = import_type
      self.import_name = import_name
    
      self.list = [import_type,import_name]     
      
  # end PortInitObject
#---------------------------------------------
#---------------------------------------------       
class PortDataObject(PortObject):
     
     def __init__(self,host=None,
                       port=None,
                       name=None,
                       type=None,
                       format=None,
                       events=None,
                       disable=None):
       self.host     = host      # tcpip 
       self.port     = port      # port number
       self.name     = name      # label
       self.type     = type      # push,pull,publish,subscribe
       self.format   = format    # how to process
       self.events   = events    # class of events to be sent to port
       self.disable  = disable   # used to disable listen (to prevent multi-listeners)
       self.list = [self.host,self.port,self.name,self.type,self.format,self.events,self.disable] 
     
  # end PortDataObject
#--------------------------------------------- 

#---------------------------------------------

class CallbackObject(NamedObject):
    def __init__(self, index=None,port=None,type=None,format=None,disable=None):
      self.index    = index    # used for reverse lookup
      self.port     = port     # tcp/ip port
      self.type     = type     # message queue connection type
      self.format   = format   # data format - how to process   
      self.disable  = disable  # if disabled then skip   
      self.list = [self.index,self.port,self.format,self.disable]  
      
  # end CallbackObject
  
#--------------------------------------------- 

##############################################################################
if __name__ == "__main__":
  print "scbPortObjects ran"
  
  
