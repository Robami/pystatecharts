#! /usr/local/bin/python
#
#
# pyrabbitmq.py
#
import sys    			# input/output
import string 			# atoi
import signal 			# os signals
import time   			# sleep, time
import os     			# pid
from KThread import *  		# killable thread
import re     			# regular expressions
import uuid   			# for unique users
import readline     		# command line editing
from threading import Lock 	# thread Lock
from threading import Event 	# thread Event

import amqplib.client_0_8 as amqp

#------------------------------------------------------
#
#
#
# classes/functions:
#  class ExceptionString
#  class CommObject
#   __init__
#   SimpleConfigure
#   _getChannelObject
#   Configure
#   ConfigureList
#   SimplePut
#   Put
#   SimpleGet
#   _queue2chobj
#   Get
#   _mycallback
#   _SimpleSubscribeThread
#   _SubscribeThread
#   SimpleSubscribe
#   SimpleUnsubscribe
#   SimpleClose
# ConnectPutGetClose
#


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
  
#-----------------------------------------------------------

class CommObject():
  def __init__(self, host='localhost', userid='guest', password='guest'): 
    self.error = False
    self.debug = False
    self.host = host
    self.userid = userid
    self.password = password        
    self.configList = []            # scalable config for rabbitmq
    self.chanList = []              # [id,obj] ordered pairs
    self.lockObj = Lock()           # used for thread safety
    self.thread_params = list()     # used for passing params into thread
       
    self.exchange = 'myexchange'
    self.uuid = str(uuid.uuid1())  # make each queue unique
    self.myqueue = 'myqueue' + self.uuid
    self.mykey = 'myq.myx'
    self.running = False
    self.subscribe = None # self.subscribe.start() to start thread for listening on exchange
 
    try:     
      self.connection = amqp.Connection(userid=self.userid, 
                           password=self.password, host=self.host,
                           virtualhost='/', ssl=False)
    except Exception as eobj:
      print eobj
      print "Is the server running? (sh rabbitmq-server-2.1.1/scripts/rabbitmq-server)"
      self.error = True
      #
      # an object is returned, not None
      #
      
  # end __init__ 
  #-----------------------------------------------------------   
  def SimpleConfigure(self):  
    try:
      self.channel = self.connection.channel()
    except Exception as eobj:
      print eobj
      self.connection.close()
      return -1
      
    print 'channel = ', self.channel.channel_id
    
    try:
      self.channel.access_request('/data', active=True, write=True, read=True)
    except Exception as eobj:
      print eobj
      self.channel.close()
      return -1
      
    #
    # Note: When configuring/reconfiguring the server may not like changes
    #       to existing exchanges. Closing channel on exception clears server.
    
    #
    # with mulitiple listeners 'direct' ping-pongs 1:1 across n listeners
    #
    
    #
    # defaults on exchange_declare:are same as queue_declare:
    # passive=False, durable=False,
    # auto_delete=True, internal=False, nowait=False
    #
    # if you mix defaults between the two, then you will raise an exception
    # 
    # auto_delete -> queue is deleted when last consumer closes
    # durable -> survives server reboot
    # passive -> when set tests presence of queue, if not present then "access refused" returned
    # internal -> special purpose, keep false
    # nowait -> server doesn't reply, keep false
    #
    queue_type = 'fanout' # 'direct' # 
    try:
      self.channel.exchange_declare(self.exchange,type=queue_type,durable=False, auto_delete=True)
    except Exception as eobj:
      print eobj
      print "The server is unhappy."
      print "You re-declared an exchange and changed a parameter."
      print "Kill and restart the server."
      self.channel.close()
      return -1
      
    try:  
      self.channel.queue_declare(self.myqueue,durable=False, auto_delete=True)
    except Exception as eobj:
      print eobj
      self.channel.close()
      return -1
    
    try:    
      self.channel.queue_bind(self.myqueue,self.exchange,routing_key=self.mykey)  
    except Exception as eobj:
      print eobj
      self.channel.close()
      return -1
      
  # end SimpleConfigure
  #-----------------------------------------------------------
  #
  # private
  #
  def _getChannelObject(self,channelList,chid):
    # channelList format:
    #   [ [<channel-id>, <channelObject>] ]
    ii = 0
    while (ii<len(channelList)):
      chpair = channelList[ii]
      if (chid == chpair[0]):
        return chpair[1]
      
      ii = ii+1
      
      #end while 
      
    return None
  #end _getChannelObject
  #-----------------------------------------------------------
 
  def Configure(self, config=[1, 'myexchange', 'direct', 'myqueue', 'myq.myx']):
    #
    # in: config format:
    #   [<channel>, <exchange>, <type>, <optional_queue>, <optional_routing_key>] 
    #        0          1         2            3                4
    #
    # queue is not necessary for writes, only for reads
    # routing_key is used for filtering reads
    #
    # out: self.configList, self.chanList
    #   chanlList format:
    #   [ [<channel-id>, <channelObject>] ]
    #          0            1
    #
    #
    # entity-relationship for channels:
    #
    # 1 configuration : multiple channels
    # 1 channel : multiple exchanges
    # 1 exchange : 0,1 queue
    # 1 queue : 0,1 message tag
    #
    err_f = False
    channelList = self.chanList
   
    #
    # if channel does not exist then create channel
    # else skip create, use pre-existing channel in channelList
    #     
    chobj = self._getChannelObject(channelList,config[0])
    if (chobj == None):
      try:
         chobj = self.connection.channel()
      except Exception as eobj:
         print eobj
	 err_f = True
	 
    if (not err_f):  
      try:
        chobj.access_request('/data',active=True,write=True,read=True)
      except Exception as eobj:
         print eobj
         err_f = True
         channel.close()
       
    if (not err_f):	 
      try:
        chobj.exchange_declare(exchange=config[1],type=config[2],durable=False, auto_delete=True)
      except Exception as eobj:
        print eobj
        print "The server is unhappy."
        print "You re-used an exchange: %s and changed the type parameter: %s." % (config[1], config[2])
        print "Closing the channel. Rename the exchange or kill and restart the server (server has memory)."
        chobj.close()
	err_f = True
    #
    # (type, queue, publish) = ('direct', routing key, match routing key)             -> yes delivery
    # (type, queue, publish) = ('direct', routing key, no or mismatched routing key) -> no 
    # (type, queue, publish) = ('fanout', routing key, no or mismatched routing key) -> yes
    #	
    if (not err_f):
      if (config[3] != None): 	   # queues are for reading from exchange
        try:  
          chobj.queue_declare(queue=config[3],durable=False,auto_delete=True)
        except Exception as eobj:
          print eobj
          err_f = True
        
        if (not err_f):	   
          try:	
            chobj.queue_bind(queue=config[3],exchange=config[1],routing_key=config[4])  
          except Exception as eobj:
            print eobj
            err_f = True            
      
    newElement = []
    
    #
    # build object's channel list out of channel id from configuration list plus channel object
    # build objects's configuration list out of input list
    #
    if (not err_f):
      newElement = [config[0]] + [chobj]
      self.chanList = self.chanList + [ newElement ] # building list of lists
      
      self.configList = self.configList + [ config ] # building list of lists
      
    return err_f
    
  #end Configure
 
  #-----------------------------------------------------------
     
  def ConfigureList(self, configSet):
    #
    # config format:
    #   [[<channel>, <exchange>, <type>, <optional_queue>, <optional_routing_key>], ...]
    # 
    # channelList format:
    #   [ <channel-id>, <channelObject> ]
    #
    
    err_f = False
    
    ii=0                      # channelList is poplulated as channels are created
    while (ii<len(configSet) and (not err_f)):
      err_f = self.Configure(configSet[ii])
      if (err_f):
        break
	
      ii = ii +1
    #end while
    
    return err_f
    
  #end ConfigureList
  #-----------------------------------------------------------     
  def SimplePut(self,msg_in):
    
    #
    # routing key is used for 'direct' exchanges
    #
    base_time = time.time();
    self.channel.basic_publish(amqp.Message(msg_in),self.exchange,self.mykey)
    #
    # (type, queue, publish) = ('direct', routing key, routing key)                  -> yes delivery
    # (type, queue, publish) = ('direct', routing key, no or mismatched routing key) -> no 
    # (type, queue, publish) = ('fanout', routing key, no or mismatched routing key) -> yes
    #
    
    print "sec:", time.time() - base_time
  # end SimplePut
  #-----------------------------------------------------------
  def _searchListOfLists(self,listOfLists,  # form: [ [...], [...],...]
                              index,        # index into unwrapped list
			      key):         # what to match
    match_f = False
    ii =0
    
    while(ii<len(listOfLists)):
      theList = listOfLists[ii]
      if (theList[index] == key):
        match_f = True
	break
      ii = ii + 1	
    #end while
    
    return match_f, ii
  #end _searchListOfLists
  
  #-----------------------------------------------------------     
  def Put(self,msg_in,exchange=None, routing_key=None):
    #
    # the purpose with the defaults is to allow the creation of simple communication links
    # with the minimal amount of programmatic effort (for testing), in parallel with
    # complex links that scale for large networks
    #
    err_f = False
    if (exchange == None):
      exchange = self.exchange
      routing_key = self.mykey    # routing key is used for 'direct' exchanges
      ch_obj = self.channel
    else:
       # search the configure list for exchange, match index yields channel id and routing_key
       # search the channel list for channel id, match yields channel object
       
       # there are many ways for this function to fail by
       # passing in bad parameters
       try:
         match_f, e_index = self._searchListOfLists(self.configList,1,exchange)
       except Exception as eobj:
          print eobj
	  err_f = True
	  return err_f
	  	 
       if (not match_f):
         print "Put(), exchange: %s not found in %s" % (exchange,self.configList)
	 err_f = True
	 return err_f
	 
       chan_id = self.configList[e_index][0]
       routing_key = self.configList[e_index][4]
	 
       # there are many ways for this function to fail by
       # passing in bad parameters
       try:
         match_f, c_index = self._searchListOfLists(self.chanList,0,chan_id)
       except Exception as eobj:
          print eobj
	  err_f = True
	  return err_f
	  
       if (not match_f):
         print "Put(), channel %d not found in: %s" % (chan_id,self.chanList)
	 err_f = True
	 return err_f
       
       ch_obj = self.chanList[c_index][1]
   
    ch_obj.basic_publish(amqp.Message(msg_in),exchange,routing_key)
      
    return err_f
  # end Put
  
  #-----------------------------------------------------------  
  def SimpleGet(self):
    try:
      response = self.channel.basic_get(self.myqueue,no_ack=False)
    except Exception as eobj:
      print self.myqueue, eobj
      response = None
      
    if response is not None:
      print "ch: %d, body = \"%s\"" %(self.channel.channel_id, response.body) 
      self.channel.basic_ack(response.delivery_tag)
    else:
      print "no message" 
       
  # end SimpleGet
  #-----------------------------------------------------------
  def _queue2chobj(self,queue):
    ch_obj = None
    err_f = False
    #
    # given queue, search for channel id
    #
    try:
         match_f, q_index = self._searchListOfLists(self.configList,3,queue)
    except Exception as eobj:
          print eobj
	  err_f = True
      	  
    if (not err_f):  	 
        if (not match_f):
          print "_queue2chobj(), queue %s not found in: %s" % (queue,self.configList)
	  err_f = True
	  
    if (not err_f): 
        chan_id = self.configList[q_index][0]
	 
        # there are many ways for this function to fail by
        # passing in bad parameters
        try:
          match_f, c_index = self._searchListOfLists(self.chanList,0,chan_id)
        except Exception as eobj:
          print eobj
	  err_f = True
	  
    if (not err_f):  
        if (not match_f):
          print "_queue2chobj(), channel %d not found in: %s" % (chan_id,self.chanList)
	  err_f = True
	  
    if (not err_f):         
        ch_obj = self.chanList[c_index][1]
	
    return err_f, ch_obj
  # end _queue2chobj
  #-----------------------------------------------------------  
  def Get(self, queue=None):
    err_f = False
    msg_f = False
    msg = None
    if (queue == None):   # for simple configuration case
      queue = self.myqueue
      ch_obj = self.channel
    else:
      #
      # given queue, search for channel id
      #
      err_f, ch_obj = self._queue2chobj(queue)
	  
      if (not err_f):         
	response = None  
        try:
          response = ch_obj.basic_get(queue,no_ack=False)
        except amqp.Timeout:
	  pass                 # not an error
	except: 
         print "queue=", queue
	 print eobj
         err_f = True
     
      if (not err_f): 
        if response is not None:
	  msg_f = True
          msg = response.body
          ch_obj.basic_ack(response.delivery_tag)
        else:
          print "no data" 
      
    return err_f, msg_f, msg
  # end Get  
  #-----------------------------------------------------------     
  #
  # private
  #  
  def _mycallback(self,msg):
    print
    for key,val in msg.properties.items():
      print '%s: %s' % (key,str(val))
    for key,val in msg.delivery_info.items():
      print '> %s: %s' % (key, str(val))
    print 'received <', msg.body, '> from channel #', msg.channel.channel_id
    msg.channel.basic_ack(msg.delivery_tag)
  # end __mycallback
  #----------------------------------------------------------- 
  #
  # private
  #    
  def _SimpleSubscribeThread(self):
     self.channel.basic_consume(queue=self.myqueue, callback=self._mycallback, no_ack=False)
     #
     # init loop
     #
     self.running = True
     #
     # loop - need a shared object (event) to determine external stop
     # 
     while self.running:
        try:
           self.channel.wait(timeout = 5)   
        except amqp.Timeout:
           print "timeout"
      
  # end _SimpleSubscribeThread
  #----------------------------------------------------------- 
  #
  # private
  #    
  def _SubscribeThread(self):
    #
    # do once: get loop invarients 
    #      
    self.lockObj.acquire()
    if len(self.thread_params):
       #
       # note: it is very easy to mess up order when
       #       adding/changing parameters
       #
       evobj = self.thread_params.pop()     # 3
       callback = self.thread_params.pop()  # 2
       queue = self.thread_params.pop()     # 1
       
    self.lockObj.release()
    
    #
    # given queue, return channel 
    #
    err_f, ch_obj = self._queue2chobj(queue)
    if (err_f):
      print "Subscribe failed"
    else:
      ch_obj.basic_consume(queue=queue, callback=callback, no_ack=False)
      #
      # init loop
      #
      self.running = True
      #
      # loop - need a shared object (event) to determine external stop
      # 
      while not self.ev_obj.is_set():    # while not signaled halt
        try:
           ch_obj.wait(timeout = 5)   
        except amqp.Timeout:
	   if (self.debug):
             print "timeout"
      
  # end _SubscribeThread
  #----------------------------------------------------------- 
  #    
  def SimpleSubscribe(self):
  
     self.subscribe = KThread(target = self._SimpleSubscribeThread)
     self.subscribe.start() 
     
  # end SimpleSubscribe
  
  #----------------------------------------------------------- 
  #    
  def Subscribe(self,queue=None,callback=None):
     #
     # the queue and callback being subscribed to is not passed in here
     # but passed in through via "self"
     # the question is how to make this scale?
     #
     #
     #
     
     self.lockObj.acquire()     
     if (queue == None):    # done for compatibility with "simple" version
       queue = self.myqueue
     if (callback == None):
       callback = self._mycallback
       
     #
     # communication parameters within thread
     #
     self.thread_params.append(queue)       # 1
     self.thread_params.append(callback)    # 2
     #
     # control param for thread
     #
     self.ev_obj = Event()
     self.thread_params.append(self.ev_obj)      # 3 - top of stack
      
     subscribe = KThread(target = self._SubscribeThread)
     subscribe.start() 
     self.lockObj.release()    
     #
     # return thread and its control object
     #
     return subscribe, self.ev_obj
     
  # end Subscribe
  #----------------------------------------------------------- 
  #
  def Unsubscribe(self,thread_object, event_object):
     #
     # object may no longer exists, so bound by "try"
     # also, belts and suspenders, i.e. signal before kill
     #
     try: 
       event_object.set()    # signals to stop running
     except:
       print "attempting to signal a non-existent event"
     try:
       thread_object.kill()    
     except Exception as eobj:
       print "attempting to signal a non-existent thread"   
  # end SimpleUnsubscribe
  #----------------------------------------------------------- 
  #
  def SimpleUnsubscribe(self): 
     self.running = False
     try:
       self.subscribe.kill()    # might not have ever subscribed
     except Exception as eobj:
       pass   
  # end SimpleUnsubscribe
  #----------------------------------------------------------- 
  #   
  def SimpleClose(self):
    self.SimpleUnsubscribe()           
    #self.channel.close()     # sometimes hangs at sock.recv
    self.connection.close()   # connection close kills socket
  # end SimpleClose
  #----------------------------------------------------------- 
  #   
  def CloseChannel(self, chobj):
    #self.Unsubscribe(chobj)           
    self.chobj.close()   # connection close kills socket
  # end Close
  #----------------------------------------------------------- 
  #   
  def CloseAll(self):
    ii =0
    while (ii < len(self.chanList)):          
      self.Close(self.chanList[ii][1])   # connection close kills socket
      ii = ii + 1
    # end while
    self.connection.close() 
  # end CloseChannelSet
  #----------------------------------------------------------- 
  #  

# end CommObj    
 
#-------------------------------

def ConnectPutGetClose():
 
  comm = CommObject()
  if (comm.error == True):
    return -1
    
  comm.SimpleConfigure()
  
  comm.SimplePut('hello world!')
    
  comm.SimpleGet()
    
  comm.SimpleClose()
  
  return 0
# end ConnectPutGetClose   
   

#-------------------------------


#-------------------------------

#   *** main ***

if __name__ == "__main__":
  block_f =0
  connect_f =0
  msg_cnt =0
  comm = None
  
  while 1:
    print 
    print "*** welcome to the menu ***"
    print "\t1: Simple Connect,Send,Get,Close"
    print "\t2: Simple Connect + Configure"
    print "\t3: Simple Send"
    print "\t4: Simple Get"
    print "\t5: Simple Close"
    print "\t6: Simple Subscribe"
    print "\t7: "
    print "\t8: Simple Unsubscribe"
    print "\t9: Simple Send Large Message"
    print
    print "\t10: Connect, no configure"
    print "\t11: Complex Configure"
    print "\t12: Complex Put"
    print "\t13: Complex Get"
    print "\t14: Complex Subscribe"
    print "\t15: Complex Unsubscribe"
    print "\t16: Complex CloseAll"
    print "\t99: exit"

  
    line = raw_input("enter selection --> ")
  
    if (line=='\n'): # skip empty lines
      print "<no value entered>"
      continue
  
    try:
      ival = string.atoi(line)
    except ValueError, emsg:
      print "ValueError: ", emsg
      ival = 0

    #print "the value selected is " + str(ival)

    if ival == 1:
      ConnectPutGetClose()
    elif ival == 2:
      comm = CommObject()
      if (comm.error == False):
        comm.SimpleConfigure()
    elif ival == 3:
      msg_string ='%d: hello world!' % msg_cnt
      print "sending:", msg_string 
      msg_cnt = msg_cnt + 1  
      try: 
        comm.SimplePut(msg_string)
      except Exception as eobj:
        print eobj
    elif ival == 4:
      try:
        comm.SimpleGet()
      except Exception as eobj:
        print eobj
    elif ival == 5:
      try:
        comm.SimpleClose()   
      except Exception as eobj:
        print eobj
    elif ival == 6:   # subscribe 
      try:
        comm.SimpleSubscribe()
      except Exception as eobj:
        print eobj
    elif (ival == 7):  # send quit
      print "not implemented"
    elif (ival ==8):   # unsubscribe
      try:
        comm.SimpleUnsubscribe()
      except Exception as eobj:
        print eobj
    elif (ival ==9):
      msg_string1 ='%d: ' % msg_cnt 
      msg_string2 = "1"*(1048576*100)
      msg_cnt = msg_cnt + 1  
      try: 
        comm.SimplePut(msg_string1 + msg_string2)
      except Exception as eobj:
        print eobj
    elif (ival == 10):
      comm = CommObject()
    elif (ival == 11):
      eflg = comm.Configure([1,'myexchange','fanout','myqueue','myq.myx'])
      if (eflg):
        print "configure error"
    elif (ival == 12):	
      msg_string ='%d: hello world!' % msg_cnt
      print "sending:", msg_string 
      msg_cnt = msg_cnt + 1  
      try: 
        comm.Put(msg_string, exchange='myexchange')
      except Exception as eobj:
        print eobj
    elif (ival == 13):
      except_f = False
      try:
        e_flg, msg_f, msg = comm.Get(queue='myqueue')
      except Exception as eobj:
        print eobj
	except_f = True
      if (not except_f):
         if (not e_flg):
	   if (msg != None):
	     print "msg received:", msg
	   else:
	     print "no data in queue:", "myqueue"
	 else:
	     print "error in Get"
    elif ival == 14:   # subscribe 
      try:
        thr_obj, ev_obj = comm.Subscribe(queue='myqueue')
      except Exception as eobj:
        print eobj  
    elif ival == 15:   # subscribe 
      try:
        comm.Unsubscribe(thread_object=thr_obj,event_object=ev_obj)
      except Exception as eobj:
        print eobj 	 
    elif ival == 16:
      try:
        comm.CloseAll()   
      except Exception as eobj:
        print eobj
    elif ival == 99:
      print "exiting menu"
      if comm != None:
        try:
          comm.SimpleClose()
        except Exception as eobj:
          print eobj
      quit()
    else:
      print "invalid entry"
  
    #end while


