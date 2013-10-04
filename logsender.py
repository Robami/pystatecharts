#
# MIT Haystack Obs.
# rps 5/23/2013
#
# testing logger and socket logger 
# server is in logserver.py
#
# 0. generate header
# 1. output to terminal
# 2. output to file
# 3. output to socket
#
# Logging priority weight:
# (from http://docs.python.org/2.4/lib/module-logging.html)
# CRITICAL 50
# ERROR    40
# WARNING  30
# INFO     20
# DEBUG    10
# NOTSET    0
#
"""
  myLogger instantiates a logger object that logs to a directory path you define
           and also sends log data out a socket to a log socket server.
  The filename will have the "tag" appended to the UTC time.
  If an "interval" is set, the log file will automatically close on interval expiration
  and reopen with the latest UTC time appended to the tag.
 
  After instantiation call:
   <obj>.log.critical("<log information>") and the keyword "CRITICAL" will be placed into the log file
   <obj>.log.warning("<log information>")
   <obj>.log.info("<log information>")
   <obj>.log.debug("<log information>")

  methods and classes:
    sigHandler               - allows ^C detection inside thread 
    ExceptionString          - allows extraction of string from exception

    myLogger                 - class wrapper on logger methods with thread
      __init__               - init
      startupHeader          - first header on log
      getFileHandle          - creates file, builds directory structure 
      shutdown               - thread shutdown
      run                    - the thread

"""
import logging           # logging module
import KThread           # killable thread
import logging.handlers  # socket handler
import time              # time
import sys               # exit
import inspect           # look at invocation
import socket            # get host name
import os.path           # absolute path
import signal            # os signals - control C detection

from gevent import monkey,sleep
monkey.patch_all()

CONTROL_C = False        # global user break detection
#
# ---------------------------------------------------------------------------
#
def sigHandler(signum, frame):   # control C detector used for killing object with thread
    global CONTROL_C 
    if signum == signal.SIGINT:
      print "^C detected (logsender)"
      CONTROL_C = True
      sys.exit(0)       # Doesn't quit for python2.7 KThread? Push event to global space
#
#-------------------------------------------------------------------------
#
class ExceptionString(Exception):
  def __str__(self):
      return repr(self.args[0])  # caller must use str(ExceptionString(<exception>))
#
# ---------------------------------------------------------------------------
#
class UTCFormatter(logging.Formatter):  # uses UTC instead of local time for timestamp
    converter = time.gmtime
#
# ---------------------------------------------------------------------------
#
class myLogger(KThread.KThread):
  DEFAULT_UTC_F      = False
  DEFAULT_PATH       = "./"
  DEFAULT_INSTRUMENT = 'Millstone'
  DEFAULT_SUBSYSTEM  = 'subsystem'
  DEFAULT_SERVICE    = 'service'
  DEFAULT_TAG        = 'log'
  DEFAULT_SERVER     = 'localhost'
  DEFAULT_PORT       = logging.handlers.DEFAULT_TCP_LOGGING_PORT
  DEFAULT_INTERVAL   = None
  DEFAULT_CONSOLE_F  = True
  DEFAULT_LEVEL      = "INFO"
  #
  # ---------------------------------------------------------------------------
  #
  def __init__(self,utc_f      = DEFAULT_UTC_F,        # use utc time
                    path       = DEFAULT_PATH,         # base directory path
                    instrument = DEFAULT_INSTRUMENT,   # instrument e.g Millstone
                    subsystem  = DEFAULT_SUBSYSTEM,    # subsystem e.g. patternGenerator
                    service    = DEFAULT_SERVICE,      # service e.g. patternGeneratorService
                    log_tag    = DEFAULT_TAG,          # becomes part of local file name
                    interval   = DEFAULT_INTERVAL,     # on interval closes / reopens w/timestamp in name
                    level      = DEFAULT_LEVEL,        # does not log lower level info
                    server     = None,                 # central log server
                    port       = None,                 # default logging port
                    console_f  = DEFAULT_CONSOLE_F):   # also write to console                       
    
    KThread.KThread.__init__(self)    # initialize thread
    # 
    # if not caught here, bad value is passed to a thread 
    # in another package that raises unhandled exception 
    #

    socket_err_f = False
    if (server!=None):
      try:
        val = int(port)
      except Exception as eobj:
        socket_err_f = True                           # set flag
        socket_err_msg = "bad port - logging server disabled"  # also logged, but later
        print socket_err_msg
        server=None                                   # prevent processing
    level_err_f = False
    level_err_f,level=self.convertLevel(level)
    if (level_err_f):
      level_err_msg = "bad level - setting level to INFO"
      print level_err_msg

    #
    # NOTE: All __init__ params need self. for "inspect" 
    #
    self.utc_f      = utc_f        # global storage for object instantiation 
    self.path       = path           
    self.instrument = instrument
    self.subsystem  = subsystem
    self.service    = service
    self.log_tag    = log_tag
    self.interval   = interval
    self.level      = level
    self.server     = server
    self.port       = port
    self.console_f  = console_f

    self.log        = None       # the logger, first time in
    self.flh        = None       # the file handler, first time in
    self.fname      = ""         # the file hanlder filename is a composite
    self.file_create_time = None # used to determine interval expiration, first time in

    #
    # Note: 
    #       Test of logginglogAdapter fails
    #       Can't use loggerAdapter with addHander - raises exception
    #
    extraInfo = {
           'hostname' : socket.gethostname(),
           'ip'       : socket.gethostbyname(socket.gethostname()),
           'utctime'  : str(time.time())
         } 
    format = '[%(asctime)s] %(name)s %(levelname)s %(message)s'
   
    if (self.utc_f):
      self.formatter = UTCFormatter(format)
    else:
      self.formatter = logging.Formatter(format) 

    if (self.server !=None):
      slh = logging.handlers.SocketHandler(server,port)  # socket log handler
    #
    # server-side based on: http://docs.python.org/2.4/lib/network-logging.html
    #
    # Don't bother with a formatter on socket, socket handler sends the internal
    # python log "record" as an unformatted pickle
    #
    # If logging server isn't running, local logging is not impeded
    #
    
                                # disable if you don't want echo to terminal
    tlh = logging.StreamHandler(sys.stdout)  # sent to terminal, terminal log handler
    tlh.setFormatter(self.formatter)         # apply format (what is used from log "record")
    
    #
    # provide structure for multiple local logs
    # provide info useful for localizing distributed log
    #
    host = socket.gethostname()                  # useful if distributed log
    log_path = os.path.abspath(path) 
    log_path = log_path + "/"+instrument+"/"+subsystem+"/"+service
    
    self.log_path = log_path
    print "logging dir=",log_path

    distribTag = host+":"+log_path+"/"+log_tag

             
    myLog = logging.getLogger(distribTag) # tag attached to "Name" field in log "record"
    myLog.setLevel(self.level)      # self.level higher priority passed through, lower suppressed

    #
    # Note:
    #   Commented out line will lead to exception at call to addHandler
    #
    #myLog = logging.LoggerAdapter(myLog,extraInfo)
    #
                                    # one logging action can be sent to multiple receivers
                                    # These are the logging receivers:
    if (self.server!=None):
      myLog.addHandler(slh)         # 1. socket sends whole record
    if (self.console_f):            # permit quieting of local console
      myLog.addHandler(tlh)         # 2. local console
    #
    # update self.flh based on time, self.interval, and self.log_tag
    # 
    self.getFileHandle()    
    myLog.addHandler(self.flh)      # 3. local file

 
    self.log = myLog                  # store handle to class object
    self.startupHeader()              # put header into file
    if (socket_err_f):                # cleanup earlier errors
      self.log.error(socket_err_msg)
    if (level_err_f):
      self.log.error(level_err_msg)
    if (self.interval != None):       # is there an interval?
      self.start()                    # start interval thread, vectors to .run()
      signal.signal(signal.SIGINT,sigHandler) # catch ^C
  #
  # ---------------------------------------------------------------------------
  #
  def convertLevel(self,level): 
    err_f = False
    level = level.upper()              # translate string to value
    if (level=="DEBUG"):
       print "logging level=",level
       level = logging.DEBUG           # Note: logging.debug is accepted but fails, use logging.DEBUG
    elif (level=="INFO"):
       level = logging.INFO
    elif (level=="WARNING"):
       level = logging.WARNING
    elif (level=="ERROR"):
       level = logging.ERROR
    elif (level =="CRITICAL"):
       level = logging.CRITICAL
    else:
      level = DEFAULT_LEVEL
      err_f,level = convertLevel(level) # should never occur
      if (err_f):
         level = level = logging.INFO   # force to good value
      err_f = True                      # flag error
    return err_f, level
  #
  # ---------------------------------------------------------------------------
  #

  def startupHeader(self):                            # put startup info into log 
    self.log.info("Logger startup")                   # announce logger has started
    args = inspect.getargspec(self.__init__)[0]       # get instantiation params
    argStrs = ['%s=%s' % (str(arg),str(eval("self."+arg))) for arg in args[1:]]
    argStr = ', '.join(argStrs)
    self.log.info('myLogger called with args <%s>' % (str(argStr)) )   # log instantiation params

  #
  # ---------------------------------------------------------------------------
  #
  # build file directory structure based on:
  #    a. object instantiation params (instrument,subsystem,service)
  #    b. day-date
  # if interval expires close file, reopen
  #  the log file has UTC as part of its name
  #self.file_create_time
  def getFileHandle(self):           

    timeNow = time.time()
        
    if (self.interval != None) and (self.file_create_time != None):  # if interval and not first time
      if ((timeNow - self.file_create_time) >= self.interval):           # if interval has expired
        if self.flh != None:                                         # safety check
           self.log.info("Interval expired. Closing log file file %s" %(self.fname))
           self.flh.close()                  # flush and close
           self.log.removeHandler(self.flh)
           self.flh = None                   # signal new handler needed
        
    if self.flh == None:      # first time in, or new file after interval
       #
       # if new file logger then create directories,
       #   create filename based on time
       #                
       gmt_time = time.gmtime(timeNow)
            
       resolved_path = self.log_path + '/%04d-%02d-%02d' % (gmt_time[0],gmt_time[1],gmt_time[2]) 
     
       try:
         os.makedirs(resolved_path)
       except Exception as eobj:
         emsg =  ExceptionString(eobj) 
	 if (str(emsg).find("File exists") <0): 
           print "Exception:",eobj
           print "Error: os.mkdirs:",resolved_path
           raise
         else:
           pass  # directory structure already exists
            
       self.fname = "%s/%s@%s.log" % (resolved_path, self.log_tag, int(timeNow))

       #print "resolved logging path=",resolved_path
           
       self.flh = logging.FileHandler(self.fname,delay=True)   # log handler for local file

       self.flh.setFormatter(self.formatter)              # apply format  

       self.file_create_time = time.time()                # used to calc interval expiration
  #
  # ---------------------------------------------------------------------------
  #
  def shutdown(self):       
      self.running = False 
      self.kill() 
      try:                       # in try block - possibility of shutdown twice
        self.flh.close()
      except Exception as eobj:
        pass
  #
  # ---------------------------------------------------------------------------
  #
  def run(self):             # invoke by .start()
      global CONTROL_C
      self.running = True
      
      #
      # once per X seconds check to see if log needs to
      # be closed and reopened with new name based on UTC time
      #
      while self.running:

        sleep(0.1)                # gevent sleep, duration is a tradeoff 
       
        if (self.interval != None): 
          self.getFileHandle()       # possibly close and reopen file

        if CONTROL_C:
          self.shutdown()

      # end while
  
  #
  # ---------------------------------------------------------------------------
  #
#
# end class
#    

if __name__ == "__main__":
   interval = 30
   utc_f = True
   print "utc=",utc_f
   server = myLogger.DEFAULT_SERVER
   port   = myLogger.DEFAULT_PORT
   #server = "bad value"
   #port   = "another bad value"
   #print "\n*** testing No server ***\n"
   #server = None
   #port   = None
   ltObj = myLogger(utc_f=utc_f,
                    server=server,
                    port=port,
                    subsystem="test",service="logging",interval=interval,console_f=True)
  
   for ii in xrange(5):
     msg ="Log message %i"%ii
     #print "logging=",msg
     ltObj.log.critical(msg) 
     time.sleep(1)

   if (interval !=None):
     print "sleeping 120 sec"
     time.sleep(120)
     tObj.log.info("*** this should be in new file ***",ii) 
     ltObj.shutdown()

   print "myLogger ran"
