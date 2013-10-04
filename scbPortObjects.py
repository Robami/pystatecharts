
"""
 rps 4/13/2011
 MIT Haystack Observatory
 
 Design:
 
 The purpose of this file is that every object which can be imported
 into the scb code generator doesn't have to be copied into the 
 generated code if it can be imported into the generated code.
  - This is the subset that is needed

 rabbitmq port definition as objects

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
    
 class PortConfigObject(PortObject):   	- params that go to rabbitmq port config deffn          
 derived from: PortObject
  functions:
  
 class CallbackObject(NamedObject):          - used for generating communication callbacks
 			 
"""

from scbUtilities import *   # isInlist
from scbObjects   import *

#---------------------------------------------  
#---------------------------------------------
#
# data structure as a class used to convert global data into an object
# as named objects are easier to extend/maintain than ordered lists 
# - all objects of this type have common operators and operators act on common objects
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
    config_list = []
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
      match_f, config_list = NamedObject.namedListMatch(pco,"exchange",exchange)
      
      if (not match_f):
        print "unrecognized exchange", exchange, "in config data:"
	print NamedObject.combineLists(pco)
        err_f = True
      
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
  print "scbPortObjects ran"
  
  
