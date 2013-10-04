#
# MakeRPCServer.py
# rps 7/22/2013
#
# read the statecharts callbacks file, generate a json rpc server and
# generate a "revised" callbacks file for the client
#
"""
  original format of method from callbacks file that is copied into pystatecharts file:
    class resetMon(Action):
      def execute(self,param):
        <code goes here>  

  Format of method that goes into server file:
     def resetMon(self,param):
        <code goes here> 

     server.register_function(resetMon)

  Revised format as proxy call is imported into pystatecharts file:
    class resetMon(Action):
      def execute(self,param):
        proxy.resetMon(self,param)

  The above still does not work on the client side because:
      1. the proxy call blocks.
      2. "param" is the statechart object, is complex => jsonrpc barfs
   Revised-revised format after gevents:
   class resetMon(Action):
      def execute(self,param):
       try:
         self.pool.spawn(self.server.resetMon,param.event)
      except Exception as eobj:
         print "rpc_client: resetMon(): Exception:",eobj

  The server example above also doesn't work:

    Revised format of method that goes into server file:
     def resetMon(event):
        <code goes here>

    Implications:
      1. The server needs to import the statechart to access methods on events
      2. If the event callback needs to create an object then it
         should be globally named, instantiated and reside on the server side
         - New param.<var>'s need to be changed to <var> outside of param
      3. If the callback generates an event, 1.5 seconds should be delayed
         between entering the callback and generating the sendEvent call
         (for allow time for the socket to close as both server and client
          are binding to the same port for sendEvents)
      4. There should be a proxy server with a unique port for every callback
         because the proxy call's are now nested. 
         The callback's ports have to align with the server's ports

         
  This tool creates the proxy server and also the client file that calls it.
  The client file should be imported where it is used.

  contents:
    utility functions:
    getIniKeySet                -      ini processing keys per section
    getIniFile                  -      ini file processing

    class: MakeRPCServer        -      
    functions: 
      __init__			-       accept params, call stages
      cleanup			-       close files
      line_fixup                -       converts call styles from direct to proxy
      stage_one			-       process and write to file prefix
      stage_two			-       process and write to file callback functions
      stage_three		-  	process and write to file postfix

"""
import sys               # argv
import re                # regular expressions
import tempfile          # temporary file
import os                # for removing temp file
import ConfigParser      # ini files

ARGPARSE = True          # python version transition issues
if ARGPARSE == True:
  try:
    import argparse       # argparse needs python 2.7, if 2.6 use optparse
  except Exception as eobj:
    print eobj
    print "Please update your python version to 2.7+. Importing optparse" 
    ARGPARSE = False

if ARGPARSE == False:
    import optparse

#
#-----------------------------------------------------------------------------
#
#              purpose: simplifies getting data from ini file
#
def getIniKeySet(filename,        # ini file name
                config_handle,    # ini handle
                section,          # ini section
                keylist,          # list of keys in section
                lfp=None):        # logger

  ii = 0              # key iterator
  err_f = False       # error flag
  valuelist = []      # return values
  while (ii < len(keylist)):                    # for length of key list
    key = keylist[ii]                           #   get key
    if config_handle.has_option(section,key):   #   if section and key exist in ini file
        value = config_handle.get(section,key)  #     get value
        valuelist = valuelist + [ value ]       #     accumulate value into value list
    else:
        msg= "*** Error: %s, missing key \"%s\" in [%s] section ***" % (filename, key, section)
        if (lfp == None):
          print msg
        else:
          lfp.log.error(msg)
        err_f = True
        break
	
    ii = ii +1  # next key
  #end while
   
  return err_f, valuelist  # return error flag and key list

# end getIniKeySet
#
#-----------------------------------------------------------
#
def getIniFile(ini_file,params,lfp=None):

    err_f = False    # error flab
    vlist = []       # accumulate value list of value sets
    #
    # The ConfigParser will successfully "read" an ini file that 
    # doesn't exist and not generate errors or exceptions. 
    # For this not unusual condition, the first error will occur
    # when a test for a mandatory tag does not succeed - so...
    #
    # Test for existence of mandatory ini file:
    #
    if (not os.path.isfile(ini_file)):
       print "File not found:",ini_file
       err_f = True
      
    if (not err_f):
      cfg = ConfigParser.ConfigParser()
      try: 
        cfg.read(ini_file)               
      except Exception as eobj:
        print sys.argv[0]+": ","*** Error:", eobj, " ***"
        err_f = True

    ii = 0
    while (ii < len(params)) and not err_f:
      keyset = params[ii]
      section = keyset[0]
      usekeys = keyset[1:len(keyset)]
      
      if (not cfg.has_section(section)):
        emsg = sys.argv[0]+": "+"*** Error: %s, missing [%s] section ***" % (ini_file,section)
        if (lfp != None):
          lfp.log.error(emsg)
        else:
          print emsg
        err_f = True
        break  
   
      if (not err_f):  
         vset = []        # value set               
         err_f, vset = getIniKeySet(ini_file,cfg,section,usekeys,None)
                            
         if (not err_f):
            vlist = vlist + [vset]
         else:
            break
      ii = ii + 1   # next keylist
    # end while  
    
    return err_f, vlist   
# end getIniFile
#
# -------------------------------------------------------------------------------
#
class MakeRPCServer:
    #
    # Design:
    # stage 1. open output file,generate prefix (imports, ^C handler, server instantiation)
    # stage 2. open input file, generate client calls, generate and register server calls 
    # stage 3. generate postfix (attach ^C handler, call server)
    #
  def __init__(self,infile,    # statechart callbacks file
               statechart,     # the statechart name (taken from the design file)
               serverfile,     # created server, copies from callbacks. invoke as python <serverfile>
               clientfile,     # client file, import then imbed instead of callbacks' bodies
               address,        # client finds server via this address
               port,           # server port, IP address is "self"
               serverlog,      # server log file
               clientlog,      # client log file  
               servertmo,      # server timeout
               clienttmo):     # client timeout
               
     self.infile = infile
     self.statechart = statechart
     self.inp = None                # infile file handle
     self.serverfile = serverfile   # name of server program
     self.clientfile = clientfile   # name of client program
     self.servp = None              # server file handle
     self.cliep = None              # client file handle
     self.address = address         # client finds server @ ip address
     self.port = port               #    and port
     self.serverlog = serverlog     # name of log file, input to server program
     self.clientlog = clientlog     # name of log file, input to client proxy
     self.servertmo = servertmo     # timeouts are empiric - sensitive to duration of proxy execution
     self.clienttmo = clienttmo     #
     #
     # declaring one long string blows up at ~324 chars but   
     # building an array of strings line by line works
     #
     mbuf = []     
     if (self.statechart != ""):
       tbuf = "from %s import *"%(self.statechart)             ; mbuf += [tbuf]
     tbuf = "import jsonrpc"                                   ; mbuf += [tbuf]
     tbuf = "import signal"                                    ; mbuf += [tbuf]
     tbuf = "import sys"                                       ; mbuf += [tbuf]
     tbuf = "import time"                                      ; mbuf += [tbuf]
     tbuf = "from gevent import spawn,sleep"                   ; mbuf += [tbuf]
     tbuf = "sobj=%s()"%(self.statechart)                      ; mbuf += [tbuf]
     tbuf = "CONTROL_C = False"                                ; mbuf += [tbuf]
     tbuf = "def sigHandler(signum, frame):"                   ; mbuf += [tbuf]
     tbuf = "    global CONTROL_C"                             ; mbuf += [tbuf]
     tbuf = "    if signum == signal.SIGINT:"                  ; mbuf += [tbuf]
     tbuf = "      print \"^C detected (json rpc server)\""    ; mbuf += [tbuf]
     tbuf = "      CONTROL_C = True"                           ; mbuf += [tbuf]
     tbuf = "      stop_time = time.time()"                    ; mbuf += [tbuf]
     tbuf = "      print \"RPC server (%s UT): deactivated.\"%time.asctime(time.gmtime(stop_time))"; mbuf += [tbuf]
     tbuf = "      sys.exit(0)"                                ; mbuf += [tbuf]
     tbuf = "signal.signal(signal.SIGINT,sigHandler)"          ; mbuf += [tbuf]
     self.server_prefix = mbuf

     client_prefix1 = "import jsonrpc\n"
     client_prefix2 = "from gevent import spawn\n"
     #
     # convert <rpc_client>.py to <rpc_client>
     #
     rpc_client = self.clientfile[0:self.clientfile.find(".")]
     client_prefix3 = "class %s:\n"%(rpc_client)
     client_prefix4 = "  def __init__(self):\n"
     self.client_prefix = client_prefix1 + client_prefix2 + client_prefix3 + client_prefix4
 

     err_f = self.stage_one()                 # stuff that go to the top of file
     if not err_f:
       err_f,server_count,funcList,portList = self.stage_two()  # server and client details
     if not err_f:
       err_f = self.stage_three(server_count,funcList,portList) # stuff that goes to the bottom of the file

  # end __init__
  #
  # -------------------------------------------------------------------------------
  # 
  def cleanup(self):
    if (self.inp != None):     # close callbacks file
      self.inp.close()
    if (self.servp !=None):    # close server file
      self.servp.close()
    if (self.cliep !=None):    # close client file
      self.cliep.close()
  #
  # -------------------------------------------------------------------------------
  # 
  # open output file,generate prefix (imports, ^C handler, server instantiation)
  #
  def stage_one(self,debug1_f=False,debug2_f=False):
    err_f = False

    try:
      self.inp = open(self.infile)
    except Exception as eobj:
      print "File:",self.infile,"Exception:", eobj
      err_f = True

    if (not err_f and (self.serverfile != None)):   
      try:
        self.servp = open(self.serverfile,"w")
      except Exception as eobj:
        print "File:",self.serverfile,"Exception:", eobj
        err_f = True

    if (not err_f):   
      try:
        self.cliep = open(self.clientfile,"w")
      except Exception as eobj:
        print "File:",self.clientfile,"Exception:", eobj
        err_f = True

    if (not err_f and (self.serverfile != None)):
      ii = 0                             # server prefix is array of strings
      while ii < len(self.server_prefix):
        self.servp.write(self.server_prefix[ii]+"\n")
        if (debug1_f):                   # debug print to display
          print server_prefix[ii]
        ii = ii + 1
      # end while

    if (not err_f):
      self.cliep.write(self.client_prefix)
      if (debug2_f):                     # debug print to display
         print self.client_prefix,       # terminating '\n' embedded in prefix

    if (err_f):
      self.cleanup()
    return err_f
  # end stage_one
  #
  # -------------------------------------------------------------------------------
  #
  def line_fixup(self,inStr,match,replacement):
    outStr = inStr
    find_idx = inStr.find(match)
    if (find_idx >= 0):                    # found
       comment_idx = inStr.find("#")
       if ((comment_idx >= 0) and (comment_idx < find_idx)):
          pass                             # found, but in comment
       else:
          outStr = inStr.replace(match,replacement)
    return outStr
  # end line_fixup
  #
  # -------------------------------------------------------------------------------
  #
  # open input file, generate client calls, generate and register server calls
  #
  # The debug flags let you see what's going on without having to open output files 
  #
  def stage_two(self,debug1_f=False,   # print server proxy-calls
                     debug2_f=False,   # print client proxy-calls
                     debug3_f=False):  # print client server initializations
    err_f = False      # error flag
    tf1 = None         # temporary file, proxy info learned late, should be printed to file early
    tf2 = None         # temporary file, prints to file the actual call to the proxy 
    funcList = []      # each server only handles one function, this is the list
    portList = []      # each server has one port, this is the list
    #
    # Solution appears to be in the domain of regular expressions 
    # Pattern 2 searches for the "def execute" keyphrase to throw away
    #

    classPat= re.compile('^class(\s+)(\w+)\W')       # (\s+) is group(1), (\w+) is group(2)
    defPat  = re.compile('^(\s*?)def(\s+?)execute')  # throw this line away

    # find "class" in column[0]
    # extract class name, print as "def <class_name>"
    # test and throw away next N lines of M-spaces followed by "#" or "def <P-spaces> execute"
    # throw away lines that start with Q-spaces "#"
    # copy line to write file until next "class" in column[0] or end-of-file

    #
    # The situation: each client call needs its own server because a proxy
    #                can call a proxy (leading to socket reuse and bind failure)
    #
    # The problem: the proxy servers are defined in __init__ but not known until now,
    #              where the code is past __init__
    #
    # The solution: Put the __init__ methon into a temp file, building as you go, 
    #               put proxy calls in a different temp file (again building as you go), 
    #               when done, merge the two temporary files into the client file.
    
    tf1 = tempfile.NamedTemporaryFile(delete=False) # named: tf1.name
    tf2 = tempfile.NamedTemporaryFile(delete=False) # named: tf1.name

    eof_f = False                           # end of file
    line = self.inp.readline()              # line = first line
    cincr = 0                               # client increment (one server per proxy call on client side)
    sincr = 0                               # server increment (server side matches client side)
    while (not eof_f):                      # while not end of file
      class_f = False                       #   flags new class found after class
      if (len(line) == 0):                  #   if empty line
        eof_f = True                        #     then end of file
        break                               #     exit while loop
      matchObj = re.match(classPat,line)    # attempt to match "class"
      if (matchObj != None):                # match found
        funcName = matchObj.group(2)        # function name taken from classname 
        funcList = funcList + [funcName]    # build list of function names (for later use)
        #----------------------------------------------------------------
        # server conversion pre "def"
        #----------------------------------------------------------------
        mbuf = []
        port = self.port + sincr
        portList = portList + [port]
        tbuf = "xport"+str(sincr)+"=jsonrpc.TransportTcpIp(addr=(\"127.0.0.1\","+str(port)+\
"),logfunc=jsonrpc.log_filedate(\""+self.serverlog +"\"),timeout=" +self.servertmo+")"              ; mbuf += [tbuf]
        tbuf = "server"+str(sincr)+"=jsonrpc.Server(jsonrpc.JsonRpc20(),xport"+str(sincr)+")\n"     ; mbuf += [tbuf]
        #
        # server side looks like:
        #
        # xport1=jsonrpc.TransportTcpIp(addr=("127.0.0.1",31415),logfunc=jsonrpc.log_filedate(logFile),timeout=TIMEOUT)
        # server1 = jsonrpc.Server(jsonrpc.JsonRpc20(),xport1,logFile)
        # def <proxy>
        #   ...
        # server1.register(<proxy>
        #
        # xport2=jsonrpc.TransportTcpIp(addr=("127.0.0.1",31416),logfunc=jsonrpc.log_filedate(logFile),timeout=TIMEOUT)
        # server2 = jsonrpc.Server(jsonrpc.JsonRpc20(),xport2,logFile)
        # ...
        #
        if (self.serverfile != None):
          ii = 0
          while (ii < len(mbuf)):         
             self.servp.write(mbuf[ii] + "\n") 
             ii = ii + 1

          if (debug1_f):
            ii = 0
            while (ii < len(mbuf)):         
              print mbuf[ii]
              ii = ii + 1

        #
        # was def <func>(self,param):, now is def <func>(event):
        # because:
        #    1. proxy call exists outside class definition
        #    2. jsonrpc barfs on "param" object - the entire statechart object
        # implications"
        #    1. statechart is imported into server
        #    2. all "param."'s in call have to be subsituted away
        #
        
        #----------------------------------------------------------------
        # server proxy definition (step 1 of 2)
        #----------------------------------------------------------------
        if (self.serverfile != None):
          buf = "def %s(event):\n"%funcName    
          self.servp.write(buf)
          if (debug1_f):
            print buf,    # "," because linefeed already present

        #----------------------------------------------------------------
        # client conversion
        #----------------------------------------------------------------
        mbuf = [] 
        tbuf = "  def %s(self,param):"%funcName                             ; mbuf += [tbuf]
        tbuf = "    try:"                                                   ; mbuf += [tbuf]
        tbuf = "      spawn(self.server%s.%s,param.event)"%(cincr,funcName) ; mbuf += [tbuf]
        tbuf = "    except Exception as eobj:"                              ; mbuf += [tbuf]
        tbuf = "      print \"Exception:\",eobj"                            ; mbuf += [tbuf]
        tbuf = "      print \"  in %s: %s():\""% (self.clientfile,funcName) ; mbuf += [tbuf]

        #
        # the next string is different because its one very long line 
        # with "\n"s placed after commas to make it easier to read
        #
        ubuf = "    self.server"+str(cincr)
        vbuf = "=jsonrpc.ServerProxy(jsonrpc.JsonRpc20(),\njsonrpc.TransportTcpIp(addr=(\"%s\","%(self.address)
        wbuf = str(self.port+cincr)
        xbuf = "),\nlogfunc=jsonrpc.log_filedate(\"%s\"),\ntimeout=%s))\n"%(self.clientlog,self.clienttmo)
        zbuf = ubuf + vbuf + wbuf + xbuf
        #
        # client side looks like:
        #
        # def __init__(self):
        #   self.server1=jsonrpc.ServerProxy(jsonrpc.JsonRpc20(),
        #                            jsonrpc.TransportTcpIp(addr=("127.0.0.1",31415),
        #                            logfunc=jsonrpc.log_filedate(logFile),
        #                            timeout=TIMEOUT))
        #
        #   self.server2=jsonrpc.ServerProxy(jsonrpc.JsonRpc20(),
        #                            jsonrpc.TransportTcpIp(addr=("127.0.0.1",31416),
        #                            logfunc=jsonrpc.log_filedate(logFile),
        #                            timeout=TIMEOUT))
        # ...
        #
        tf1.write(zbuf)
        cincr = cincr + 1  # for next iteration in loop
        if (debug3_f):
          print zbuf,

        ii = 0
        while (ii < len(mbuf)):         
           tf2.write(mbuf[ii] + "\n") # write to temporary file
           ii = ii + 1
        
        if (debug2_f):
          ii = 0
          while (ii < len(mbuf)):         
            print mbuf[ii]
            ii = ii + 1

        # throw away "def execute"        
        while (True):
          line = self.inp.readline()
          if (len(line) == 0):
             eof_f = True
             err_f = True             # end of file during search
             print "MakeRPCServer.stage_two: end of file during search"
             break
          matchObj = re.match(defPat,line)
          if (matchObj != None):
            break
        # end while search for "def execute"
        #
        if (not err_f):
          while (True):
            line = self.inp.readline()    # copy input to output
            if (len(line) == 0):
              eof_f = True
              break

            matchObj = re.match(classPat,line)
            if (matchObj != None):        # next class
              class_f = True              # set flag to skip readline
              break
            #
            # Q: If the "param." that correponds to the statchart is no longer 
            #    part of the proxy call then where does the statechart context come from?           
            # 
            # A: Import the statchart directly onto the server side with "from <statechart> import *"
            #
            # Q: What are the implications?
            #
            # A: The "state" of the statechart is absent on the server side.
            #    The callback is limited to event handling w/o pre-knowledge of the state.
            #    param.event => event, param.sendEvent => <statechart>.sendEvent
            # 
            # Q: Are there more fixups besides event and sendEvent?
            #
            # A1: Globals declared in the statechart but used in the callbacks will 
            #    need to be identified and instantiated. 
            #    Note that statechart state cannot depend on these globals.
            # A2: A1 is wrong. Importing the statechart also imports the globals.
            #

            #----------------------------------------------------------------
            # server proxy execution (step 2 of 2)
            #----------------------------------------------------------------
            
            #
            # substitute param.event and param.sendEvent
            # 
            line = self.line_fixup(line,"param.event","event")
            line = self.line_fixup(line,"param.sendEvent","sobj.sendEvent")
            if (self.serverfile != None):
              self.servp.write(line)
              if (debug1_f):
                 print line,     # "," because linefeed already present
        # end while
      if (err_f):
         break
      if (not class_f):             # skip read to process current line 
        line = self.inp.readline()  
      else:                         # definition done, add register
         if (self.serverfile != None):
           buf = "server"+str(sincr)+".register_function(%s)\n\n"%(funcName)
           self.servp.write(buf)
           if (debug1_f):
              print buf,     # "," because linefeed already present
         sincr = sincr + 1  # increment for next go 'round
    # end while 
    #
    # copy temp file to client file, delete temp file
    # 
    tf1.seek(0)   # rewind
    tf2.seek(0)
    self.cliep.write(tf1.read()) # copy proxy server initializion to client file
    self.cliep.write(tf2.read()) # copy proxy calls to client file
    
    tf1.close()
    os.unlink(tf1.name)          # delete
    
    tf2.close()
    os.unlink(tf2.name)          # delete

    if (err_f): 
       self.cleanup()
    return err_f,sincr,funcList,portList
  # end stage_two
  #
  # -------------------------------------------------------------------------------
  #
  # generate postfix (attach ^C handler, call server)
  #
  # all servers except for last last are non-blocking -> spawn
  # last server is blocking
  #
  def stage_three(self,scount,funcList,portList,debug_f=False):
     err_f = False
    
     mbuf = []
     if (self.serverfile != None):
       ii = 0 
       while (ii <scount):
         tbuf = "start_time = time.time()"            ; mbuf += [tbuf]
         #
         # embedding a formatted string within a formatted string causes compiler heartburn
         #
         partial = "print \"RPC server%d for %s on port %d"%(ii,funcList[ii],portList[ii])
         tbuf = partial+" activated. (%s UT) \"%time.asctime(time.gmtime(start_time))"; mbuf += [tbuf]
         if ((ii + 1) < scount):
           tbuf = "spawn(server%d.serve)"%(ii)         ; mbuf += [tbuf]
         else:
           tbuf = "server%d.serve()"%(ii)              ; mbuf += [tbuf]
         ii = ii + 1
       # end while

       ii = 0
       while (ii < len(mbuf)):         
         self.servp.write(mbuf[ii] + "\n") 
         ii = ii + 1 

       if (debug_f):
         ii = 0
         while (ii < len(mbuf)):         
           print mbuf[ii]
           ii = ii + 1
         # end inner while

       # end outer while
     # endif yes server
     self.cleanup()
     return err_f
  # end stage_three

# end class MakeRPCServer
#
# -------------------------------------------------------------------------------
#
if __name__ == '__main__':
  #
  # Transitioning from optparse to argparse
  # Note: -h help is built-in for both
  # Note: argparse requires python 2.7+ 
  #
  err_f = False
  #
  # defaults
  #
  DEFAULT_SERVER   = "rpc_server.py"
  DEFAULT_CLIENT   = "rpc_client.py"
  DEFAULT_ADDRESS  = "127.0.0.1"
  DEFAULT_PORT     = 31415
  DEFAULT_SERVERLOG = "./rpc_server.log"
  DEFAULT_CLIENTLOG = "./rpc_client.log"
  DEFAULT_SERVERTMO = "3.0"                # value is a string because code is built
  DEFAULT_CLIENTTMO = "5.0"                # needs to be tunable - a proxy might call a proxy
  NULL_STRING = ""
  design_file = NULL_STRING
  input_file  = NULL_STRING
  statechart  = NULL_STRING
  client_only_f = False
  if ARGPARSE:
    parser = argparse.ArgumentParser()
    parser.add_argument('-i','--input_file', help='-i <input_file>: input callbacks file')
    parser.add_argument('-I','--statechart', help='-I <statechart>: import statechart file')
    parser.add_argument('-d','--design_file', help='-d <design_file>: input design file')
    parser.add_argument('-s','--server_file', help='-s <server_file>: output server file')
    parser.add_argument('-c','--client_file', help='-s <client_file>: output client file')
    parser.add_argument('-C','--client_only', help='-c: do not build server',action="store_true") # default false
    parser.add_argument('-a','--address', help='-a <IP_address>: input IP address')
    parser.add_argument('-p','--port', help='-p <port>: IP port',type=int)
    parser.add_argument('-L','--serverlog', help='-L <log_file>: server log file')
    parser.add_argument('-l','--clientlog', help='-l <log_file>: client log file')
    parser.add_argument('-T','--servertmo', help='-t <float>: server timeout')
    parser.add_argument('-t','--clienttmo', help='-T <float>: client timeout')
    #
    # initialize object with instantiation parameters
    #
    args = parser.parse_args()        # get params

    #
    # This program can generate proxies with either design (ini) file or input file 
    # but error if both are missing.
    # The design file takes precedence if both are present. 
    #

    if args.design_file != None:
         design_file = args.design_file
         if args.input_file != None:
           print "*** Warning: both callback and design files selected, design file takes precedence ***"
    else:
      if args.input_file != None:
         input_file = args.input_file
         if args.statechart != None:
            statechart = args.statechart
      else:
         print "missing input or design file, try -h option"
         err_f = True
                                  # The input or design file names are mandatory.
                                  # The remainder are options and will be overridden 
                                  # by the values in the design (ini) file, if present
                                  # else default values will be used
    if (not err_f):                 
      server_file = DEFAULT_SERVER
      if args.server_file != None:
         server_file = args.server_file

      client_file = DEFAULT_CLIENT
      if args.client_file != None:
         client_file = args.client_file
    
      address = DEFAULT_ADDRESS          
      if args.address != None:
         address = args.address

      port = DEFAULT_PORT          
      if args.port != None:
         port = args.port

      serverlog = DEFAULT_SERVERLOG          
      if args.serverlog != None:
         serverlog = args.serverlog

      clientlog = DEFAULT_CLIENTLOG          
      if args.clientlog != None:
         clientlog = args.clientlog 

      servertmo = DEFAULT_SERVERTMO         
      if args.servertmo != None:
         servertmo = args.servertmo 

      clienttmo = DEFAULT_CLIENTTMO          
      if args.clienttmo != None:
         clienttmo = args.clienttmo  

      if args.client_only != None:
        client_only_f = args.client_only
 
  else: 
    opin = optparse.OptionParser()
    
    opin.add_option("-i", action="store", type="string", dest="input_file")
    opin.add_option("-I", action="store", type="string", dest="statechart")
    opin.add_option("-d", action="store", type="string", dest="design_file")
    opin.add_option("-s", action="store", type="string", dest="server_file")
    opin.add_option("-c", action="store", type="string", dest="client_file")
    opin.add_option('-C', action="store_true",dest="client_only")            # default false
    opin.add_option("-a", action="store", type="int",    dest="address")
    opin.add_option("-p", action="store", type="int",    dest="port")
    opin.add_option("-L", action="store", type="string", dest="serverlog")
    opin.add_option("-l", action="store", type="string", dest="clientlog")
    opin.add_option("-T", action="store", type="string", dest="servertmo")
    opin.add_option("-t", action="store", type="string", dest="clienttmo")
    opin.set_defaults(input_file="")
    

    # The input or design file names are mandatory.
    # The remainder are options and will be overridden 
    # by the values in the design (ini) file, if present
    # else default values will be used

    opin.set_defaults(design_file=NULL_STRING)
    opin.set_defaults(input_file=NULL_STRING)
    opin.set_defaults(statechart=NULL_STRING)
    opin.set_defaults(server_file=DEFAULT_SERVER)
    opin.set_defaults(client_file=DEFAULT_CLIENT)
    opin.set_defaults(port=DEFAULT_PORT)
    opin.set_defaults(serverlog=DEFAULT_SERVERLOG)
    opin.set_defaults(clientlog=DEFAULT_CLIENTLOG)
    opin.set_defaults(servertmo=DEFAULT_SERVERTMO)
    opin.set_defaults(clienttmo=DEFAULT_CLIENTTMO)
    opin.set_defaults(client_only=False)
    opt, args    = opin.parse_args()
    input_file   = opt.input_file
    statechart   = opt.statechart
    design_file  = opt.design_file
    server_file  = opt.server_file
    client_file  = opt.client_file
    address      = opt.address
    port         = opt.port
    serverlog    = opt.serverlog
    clientlog    = opt.clientlog
    servertmo    = opt.servertmo
    clienttmo    = opt.clienttmo
    client_only_f= opt.client_only

  if (design_file == "") and (input_file == ""):
    print "missing input and missing design file, try -h option"
    err_f = True
  else:
    if (design_file != "") and (input_file !=""):
      print "*** Warning: design file takes precedence for all parameters ***"
  
  if not err_f:
    #
    # process the ini file if provided and override the commandline parameters
    #
    if (design_file != ""):
      keyset = [["STATECHART","name"],   # statechart name
                ["OPTIONS","InsertCB"],  # callbacks file
                ["RPC","server","client","ip","port","servertmo","clienttmo","serverlog","clientlog"]]
      err_f, values = getIniFile(design_file,keyset)
      if err_f:
        print "Error in design file: %s"%(design_file)
      else:                              # pick off parameters
         statechart = values[0][0]       # statechart names
         input_file = values[1][0]       # InsertCB
         serverfile = values[2][0]
         clientfile = values[2][1]
         address    = values[2][2]
         port_str   = values[2][3]
         try:
           port       = int(port_str)    # the one integer treated as an int 
         except Exception as eobj:         
           print design_file,"[RPC],port:",port_str,"- integer expected"
           err_f = True
         else:
           servertmo  = values[2][4]         # these are copied as is
           clienttmo  = values[2][5]
           serverlog  = values[2][6]
           clientlog  = values[2][7]
    
  if not err_f:
    
    if (client_only_f):          
       serverfile = None
       #
       # Q: Why would you ever not want to make the server?
       # A: In the case of a distributed statechart, only one server should be built
       #    this param prevents multiple server builds when "system" building
       #
    MakeRPCServer(infile     = input_file,
                  statechart = statechart,
                  serverfile = server_file,
                  clientfile = client_file,
                  address    = address,
                  port       = port,
                  serverlog  = serverlog,
                  clientlog  = clientlog,
                  servertmo  = servertmo,
                  clienttmo  = clienttmo)

    
    print "client file:",client_file
    if (not client_only_f):
      print "server file:",server_file
