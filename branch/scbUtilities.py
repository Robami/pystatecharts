"""
 rps 5/6/2011
 MIT Haystack Observatory
 
 Design:
 
 The purpose of this file is to hold common utilities

 ---------------------------------------------
 
 functions:                     
   isInlist				- searches for match in list w/o exception
                                	  
 class funcFromFile                      
     __init__
     getFuncFromFile			- returns the function from a file
     findMissing                        - returns functions present but not replaced
 
 class MyException(Exception)           - returns string from exception
			 
"""

import re                   # regular expressions
#
#------------------------------------------------------------------------------
# MyException
#          purpose: to get access to the string message inside the
#                   exception object
#
class MyException(Exception):

    def __str__(self):
        return repr(self.args[0])
    # end __str__
#end class MyException        
#------------------------------------------------------------------------------
# isInlist
#         purpose: to determine if an item is in a list without
#                  raising an exception
def isInlist(inlist,    # the list
             value):    # the item to look for
  try:
    inlist.index(value)
  except Exception:         # any exception is invalid comparison, return false
    return False
  return True

# end isInlist

#-----------------------------------------------------------------
#-----------------------------------------------------------------
# funcFromFile
#              purpose: to substitute one function for another in a file
#                       this allows design separation of state and transition
#                       declarations from what-to-do actions 
#
class funcFromFile:

  def __init__(self,fileName):
    self.fileName = fileName
    self.funcList = []
  #end __init__
  #-----------------------------------------------------------------

  #
  # returns function text from file
  #
  def getFuncFromFile (self,method):
    fp = None
    buf = ""
    done_f = False
    match_f = False
  
    try:
       fp = open(self.fileName,'r')
    except Exception as eobj:
      print eobj
 
    if (fp !=None):
      #
      # all lines are terminated by \n
      # eof is indicated by zero length line
         
      # method name is method with parens removed
      #
      method_name = re.sub("\(\)","",method)   
      
      while (not done_f):
        line = fp.readline()
        if (len(line) == 0):
          done_f = True
          break
        
        #
        # match has to be exact
        #  	
        kidx = line.find(method_name)
        if (kidx != -1):
           
           # check for false positives:
           #   not # comment
           #   yes class
           #   yes (Guard) or (Action)
           #   only ' ' or '(' at end of match
           
           coidx = line.find('#')
           if ((coidx != -1) and (coidx < kidx)):
             continue
           
           clidx = line.find("class")
           if (clidx != 0):
             continue
             
           gidx = line.find('(Guard)')
           aidx = line.find('(Action)')
           if ((gidx == -1) and (aidx == -1)):
             continue
             
           testchar = line[kidx+len(method_name):kidx+len(method_name)+1]       
           if (testchar ==  ' ') or (testchar == '('):  # ok
             pass
           else:
             continue
             
           #
           # still here? then
           # copy lines to buffer 
           # to line where there is a non-comment in first column
           # and previous line last column (before \n) is not backslash
           # then break
           
           buf = buf + line
           prev_line = line         
           while (not done_f):
             line = fp.readline()
             if (len(line) == 0):
                match_f = True
                done_f = True
                break
             
             if (line[0] == ' ') or (line[0] == '#'): # simple line
               buf = buf + line
               prev_line = line
             else:                                    # more complex
                if (prev_line[len(prev_line)-2] != '\\'):  # not continuation
                  done_f = True
                  match_f = True
                  break
                else:               # line continuation
                  buf = buf + line  # keep going
                  prev_line = line
               
             #end if simple line
           
           # while lines in function
           
        #end if no match      
        
      # end while lines in file
    # end if not None
    
    if (fp !=None):
      fp.close()
      
    if (match_f):
      self.funcList = self.funcList + [method_name]
      
    return match_f, buf
    
  #end getFuncText
  #-----------------------------------------------------------------
  #
  # Purpose: to provide a list of un-matched functions
  # which will provide a clue if functions are miss-spelled
  # which could result in the functions you think you are calling, 
  # you are not.
  #
  # Design:
  # Given a list of functions, read file and match what is found
  # against this list, return a list of functions in the file that
  # are not in the list
  #
  def findMissing(self):
  
    missingList = []
    done_f = False
    err_f = False
    
    try:
       fp = open(self.fileName,'r')
    except Exception as eobj:
      print eobj
      fp = None
      err_f = True
 
    if (fp !=None):
      while (not done_f):
        line = fp.readline()
        if (len(line) == 0):
          done_f = True
          break
          
        cidx = line.find('class')   # 'class' must be in column 0
        if (cidx == -1):
           continue
        if (cidx !=0):
          continue
           
        pidx = line.find('(')      # end
        if (pidx == -1):
           continue
           
        xline = line[cidx+len('class'):pidx]  # extract
        xline = xline.lstrip()
        method = xline.rstrip()                # cleanup
                
        if (not isInlist(self.funcList,method)):
           missingList = missingList + [method]
      #end while
      
      fp.close()
      
    #end if not None
    
    return err_f, missingList
  
  #end findMissing
#end funcFromFile
#-----------------------------------------------------------------
#-----------------------------------------------------------------

