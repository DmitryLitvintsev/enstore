#!/usr/bin/env python

# src/$RCSfile$   $Revision$
#
#########################################################################
#                                                                       #
# Media Changer server.                                                 #
# Media Changer is an abstract object representing a physical device or #
# operator who performs mounts / dismounts of tapes on tape drives.     #
# At startup the media changer process takes its argument from the      #
# command line and cofigures based on the dictionary entry in the       #
# Configuration Server for this type of Media Changer.                  #
# It accepts then requests from its clients and performs tape mounts    #
# and dismounts                                                         #
#                                                                       #
#########################################################################

# system imports
import os
import sys
import types
import time
import popen2
import string
import socket
import time
import hostaddr
import struct, fcntl, FCNTL

# enstore imports
import configuration_client
import dispatching_worker
import generic_server
import interface
import Trace
import e_errors
import volume_clerk_client


def _lock(f, op):
        dummy = fcntl.fcntl(f.fileno(), FCNTL.F_SETLKW,
                            struct.pack('2h8l', op,
                                        0, 0, 0, 0, 0, 0, 0, 0, 0))
        Trace.trace(21,'_lock '+repr(dummy))
        
def writelock(f):
        _lock(f, FCNTL.F_WRLCK)

def readlock(f):
        _lock(f, FCNTL.F_RDLCK)

def unlock(f):
        _lock(f, FCNTL.F_UNLCK)



# media loader template class
class MediaLoaderMethods(dispatching_worker.DispatchingWorker,
                         generic_server.GenericServer):

    work_list = []
    work_cleaning_list = []

    def __init__(self, medch, max_work, csc):
        self.name = medch
        self.name_ext = "MC"
        generic_server.GenericServer.__init__(self, csc, medch)
        Trace.init(self.log_name)
        self.max_work = max_work
        self.workQueueClosed = 0
        self.insertRA = None
        #   pretend that we are the test system
        #   remember, in a system, there is only one bfs
        #   get our port and host from the name server
        #   exit if the host is not this machine
        self.mc_config = self.csc.get(medch)
        dispatching_worker.DispatchingWorker.__init__(self, \
                         (self.mc_config['hostip'], self.mc_config['port']))
        self.idleTimeLimit = 600  # default idle time in seconds
        self.lastWorkTime = time.time()
        self.robotNotAtHome = 1
        self.timeInsert = time.time()
        
    # retry function call
    def retry_function(self,function,*args):
        return apply(function,args)
    
        
    # wrapper method for client - server communication
    def loadvol(self, ticket):        
        ticket["function"] = "mount"
        return self.DoWork( self.load, ticket)

    # wrapper method for client - server communication
    def unloadvol(self, ticket):
        ticket["function"] = "dismount"
        return self.DoWork( self.unload, ticket)

    # wrapper method for client - server communication
    #def viewvol(self, ticket):
    #    ticket["status"] = self.view(ticket["vol_ticket"]["external_label"], \
    #              ticket["vol_ticket"]["media_type"])
    #    self.reply_to_caller(ticket)
        
    # wrapper method for client - server communication - replaced viewvol above tgj1
    def viewvol(self, ticket):
        ticket["function"] = "getVolState"
        return self.DoWork( self.getVolState, ticket)

    # wrapper method for client - server communication
    def insertvol(self, ticket):
        ticket["function"] = "insert"
        if not ticket.has_key("newlib"):
            ticket["status"] = (e_errors.WRONGPARAMETER, 37, "new library name not specified")
            Trace.log(e_errors.ERROR, "ERROR:insertvol new library name not specified")
            return
        return self.DoWork( self.insert, ticket)

    # wrapper method for client - server communication
    def ejectvol(self, ticket):
        ticket["function"] = "eject"
        return self.DoWork( self.eject, ticket)

    def homeAndRestartRobot(self, ticket):
        ticket["function"] = "homeAndRestart"
        return self.DoWork( self.robotHomeAndRestart, ticket)

    def doCleaningCycle(self, ticket):
        ticket["function"] = "cleanCycle"
        return self.DoWork( self.cleanCycle, ticket)

    def set_max_work(self,ticket):
        self.max_work = ticket["max_work"]
        self.reply_to_caller({'status' : (e_errors.OK, 0, None)})

    def getwork(self,ticket):
        result = []
        for i in self.work_list:
            result.append((i['function'], i['vol_ticket']['external_label'], i['drive_id']))
        self.reply_to_caller({'status' : (e_errors.OK, 0, None),
                              'max_work':self.max_work,
                              'worklist':result})

    # load volume into the drive;  default, overridden for other media changers
    def load(self,
             external_label,    # volume external label
             drive,             # drive id
             media_type):       # media type
        if 'delay' in self.mc_config.keys() and self.mc_config['delay']:
            # YES, THIS BLOCK IS FOR THE DEVELOPMENT ENVIRONMENT AND THE
            # OUTPUT OF THE PRINTS GO TO THE TERMINAL
            print "make sure tape %s in in drive %s"%(external_label,drive)
            time.sleep( self.mc_config['delay'] )
            print 'continuing with reply'
        return (e_errors.OK, 0, None)

    # load volume into the drive;  default, overridden for other media changers
    def load(self,
             external_label,    # volume external label
             drive,             # drive id
             media_type):       # media type
        if 'delay' in self.mc_config.keys() and self.mc_config['delay']:
            # YES, THIS BLOCK IS FOR THE DEVELOPMENT ENVIRONMENT AND THE
            # OUTPUT OF THE PRINTS GO TO THE TERMINAL
            print "make sure tape %s in in drive %s"%(external_label,drive)
            time.sleep( self.mc_config['delay'] )
            print 'continuing with reply'
        return (e_errors.OK, 0, None)

    # unload volume from the drive;  default overridden for other media changers
    def unload(self,
               external_label,  # volume external label
               drive,           # drive id
               media_type):     # media type
        if 'delay' in self.mc_config.keys() and self.mc_config['delay']:
            Trace.log(e_errors.INFO,
                      "remove tape "+external_label+" from drive "+drive)
            time.sleep( self.mc_config['delay'] )
        return (e_errors.OK, 0, None)

    # view volume in the drive;  default overridden for other media changers
    #def view(self,
    #           external_label,  # volume external label
    #       media_type):         # media type
    #    return (e_errors.OK, 0, None, 'O') # return 'O' - occupied aka unmounted

    # getVolState in the drive;  default overridden for other media changers - to replace above tgj1
    def getVolState(self, ticket):
        return (e_errors.OK, 0, None, 'O') # return 'O' - occupied aka unmounted

    # insert volume into the robot;  default overridden for other media changers
    def insert(self,ticket):
        return (e_errors.OK, 0, None, '') # return '' - no inserted volumes

    # eject volume from the robot;  default overridden for other media changers
    def eject(self,ticket):
        return (e_errors.OK, 0, None) 

    def robotHomeAndRestart(self,ticket):
        pass
        return (e_errors.OK, 0, None) 

    def cleanCycle(self,ticket):
        pass
        return (e_errors.OK, 0, None) 

    def waitingCleanCycle(self,ticket):
        pass
        return (e_errors.OK, 0, None) 

    def startTimer(self,ticket):
        pass
        return (e_errors.OK, 0, None) 

    # prepare is overridden by dismount for mount; i.e. for tape drives we always dismount before mount
    def prepare(self,
               external_label,
               drive,
               media_type) :        
        pass

    def doWaitingInserts(self):
        pass
        return (e_errors.OK, 0, None) 

    def doWaitingCleaningCycles(self, ticket):
        ticket["function"] = "waitingCleanCycle"
        return self.DoWork( self.waitingCleanCycle, ticket)

    def getNretry(self):
        numberOfRetries = 3
        return numberOfRetries

    # Do the forking and call the function
    def DoWork(self, function, ticket):
        if ticket['function'] in ("mount", "dismount"):
            Trace.log(e_errors.INFO, 'REQUESTED %s %s %s'%
                      (ticket['function'], ticket['vol_ticket']['external_label'],ticket['drive_id']))
            # if drive is doing a clean cycle, drop request
            for i in self.work_list:
                try:
                    if (i['function'] == "cleanCycle" and i.has_key('drive_id') and
                        i['drive_id'] == ticket['drive_id']):
                        Trace.log(e_errors.INFO,
                                  'REQUESTED %s request of %s in %s  dropped, drive in cleaning cycle.'%
                                  (ticket['function'],ticket['vol_ticket']['external_label'],
                                   ticket['drive_id']))

                        return
                except:
                    e_errors.handle_error()
                    Trace.log(e_errors.ERROR, "ERRROR %s"%(repr(i),))
                    
        else:
            Trace.log(e_errors.INFO, 'REQUESTED  %s'%(ticket['function'],))
        #put cleaningCyles on cleaning list
        if ticket['function'] == "cleanCycle":
            ticket["ra"] = (self.reply_address,self.client_number,self.current_id)
            todo = (ticket,function)
            self.work_cleaning_list.append(todo)
        
        #if we have max number of working children, assume client will resend
        # let work list length exceed max_work for cleaningCycle
        if ticket["function"] != "getVolState":
            if len(self.work_list) >= self.max_work:
                Trace.log(e_errors.INFO,
                          "MC Overflow: "+ repr(self.max_work) + " " +\
                          ticket['function'])
                return
              ##elif work queue is temporarily closed, assume client will resend
            elif  self.workQueueClosed and len(self.work_list)>0:
                Trace.log(e_errors.INFO,
                          "MC Queue Closed: " + ticket['function'] + " " + repr(len(self.work_list)))
                return
            
        # otherwise, we can process work

        #Trace.log(e_errors.INFO, "DOWORK "+repr(ticket))
        # set the reply address - note this could be a general thing in dispatching worker
        ticket["ra"] = (self.reply_address,self.client_number,self.current_id)
        # bump other requests for cleaning
        if len(self.work_cleaning_list) > 0:
            if ticket['function'] != "waitingCleanCycle":
                Trace.log(e_errors.INFO,
                  "MC: "+ ticket['function'] + " bumped for cleaning")
            ticket = self.work_cleaning_list[0][0]
            function = self.work_cleaning_list[0][1]
            self.work_cleaning_list.remove((ticket,function))
            Trace.log(e_errors.INFO, 'REPLACEMENT '+ticket['function'])
        # if this a duplicate request, drop it
        for i in self.work_list:
            if i["ra"] == ticket["ra"]:
                Trace.log(e_errors.INFO,"duplicate request, drop it %s %s"%(repr(i["ra"]),repr(ticket["ra"])))
                return
        # if function is insert and queue not empty, close work queue
        if ticket["function"] == "insert":
            if len(self.work_list)>0:
               self.workQueueClosed = 1
               self.timeInsert = time.time()
               self.insertRA = ticket["ra"]
               Trace.log(e_errors.INFO,"RET1 %s"%( ticket["function"],))
               return 
            else:
               self.workQueueClosed = 0
        # if not duplicate, fork the work
        pipe = os.pipe()
        if self.fork(): #parent
            self.add_select_fd(pipe[0])
            os.close(pipe[1])
            # add entry to outstanding work 
            self.work_list.append(ticket)
            Trace.trace(10, 'mcDoWork< Parent')
            return

        #  in child process
        if ticket['function'] in ("mount", "dismount"):
            msg="%s %s %s" % (ticket['function'],ticket['vol_ticket']['external_label'], ticket['drive_id'])
        else:
            msg="%s" % (ticket['function'],)
        Trace.log(e_errors.INFO, 'mcDoWork> child begin %s '%(msg,))
        os.close(pipe[0])
        # do the work ...
        # ... if this is a mount, dismount first
        if ticket['function'] == "mount":
            Trace.log(e_errors.INFO, 'mcDoWork> child prepare dismount for %s'%(msg,))
            sts=self.prepare(
                ticket['vol_ticket']['external_label'],
                ticket['drive_id'],
                ticket['vol_ticket']['media_type'])
            Trace.log(e_errors.INFO,'mcDoWork> child prepare dismount for %s returned %s'%(msg,sts))
        if ticket['function'] in ('insert','eject','homeAndRestart','cleanCycle','getVolState'):
            Trace.log(e_errors.INFO, 'mcDoWork> child doing %s'%(msg,))
            sts = function(ticket)
            Trace.log(e_errors.INFO,'mcDoWork> child %s returned %s'%(msg,sts))
        else:
            Trace.log(e_errors.INFO, 'mcDoWork> child doing %s'%(msg,))
            sts = function(
                ticket['vol_ticket']['external_label'],
                ticket['drive_id'],
                ticket['vol_ticket']['media_type'])
            Trace.log(e_errors.INFO,'mcDoWork> child %s returned %s'%(msg,sts))

        # send status back to MC parent via pipe then via dispatching_worker and WorkDone ticket
        Trace.trace(10, 'mcDoWork< sts'+repr(sts))
        ticket["work"]="WorkDone"       # so dispatching_worker calls WorkDone
        ticket["status"]=sts
        msg = repr(('0','0',ticket))
        bytecount = "%08d" % (len(msg),)
        os.write(pipe[1], bytecount)
        os.write(pipe[1], msg)
        os.close(pipe[1])
        os._exit(0)

    
    def WorkDone(self, ticket):
        # dispatching_worker sends "WorkDone" ticket here and we reply_to_caller
        # remove work from outstanding work list
        for i in self.work_list:
           if i["ra"] == ticket["ra"]:
              self.work_list.remove(i)
              break
        # report back to original client - probably a mover
        fstat = ticket.get('status', None)
        if fstat[0]=="ok":
            level = e_errors.INFO
        else:
            level = e_errors.ERROR
        if ticket['function'] in ("mount","dismount"):
            Trace.log(level, 'FINISHED %s %s %s  returned %s' %
                      (ticket['function'], ticket['vol_ticket']['external_label'],ticket['drive_id'],fstat))
        else:
            Trace.log(level, 'FINISHED %s returned %s'%(ticket['function'],fstat))
        # reply_with_address uses the "ra" entry in the ticket
        self.reply_with_address(ticket)
        self.robotNotAtHome = 1
        self.lastWorkTime = time.time()
        # check for cleaning jobs
        if len(self.work_list) < self.max_work and len(self.work_cleaning_list) > 0:
            sts = self.doWaitingCleaningCycles(ticket)
        # if work queue is closed and work_list is empty, do insert
        sts = self.doWaitingInserts()

# aml2 robot loader server
class AML2_MediaLoader(MediaLoaderMethods):

    def __init__(self, medch, max_work=7, csc=None):
        MediaLoaderMethods.__init__(self, medch, max_work, csc)

        # robot choices are 'R1', 'R2' or 'Both'
        if self.mc_config.has_key('RobotArm'):   # error if robot not in config
            self.robotArm = string.strip(self.mc_config['RobotArm'])
        else:
            Trace.log(e_errors.ERROR, "ERROR:mc:aml2 no robot arm key in configuration")
            self.robotArm = string.strip(self.mc_config['RobotArm']) # force the exception          
            return

        if self.mc_config.has_key('IOBoxMedia'):   # error if IO box media assignments not in config
            self.mediaIOassign = self.mc_config['IOBoxMedia']
        else:
            Trace.log(e_errors.ERROR, "ERROR:mc:aml2 no IO box media assignments in configuration")
            self.mediaIOassign = self.mc_config['IOBoxMedia'] # force the exception
            return

        if self.mc_config.has_key('DriveCleanTime'):   # error if DriveCleanTime assignments not in config
            self.driveCleanTime = self.mc_config['DriveCleanTime']
        else:
            Trace.log(e_errors.ERROR, "ERROR:mc:aml2 no DriveCleanTime assignments in configuration")
            self.driveCleanTime = self.mc_config['DriveCleanTime'] # force the exception
            return

        if self.mc_config.has_key('CleanTapeVolumeFamily'):   # error if DriveCleanTime assignments not in config
            try:
		    self.cleanTapeVolumeFamily = self.mc_config['CleanTapeVolumeFamily'] # expected format is "externalfamilyname.wrapper"
		    fields = string.split(self.cleanTapeVolumeFamily, '.')
		    self.cleanTapeWrapper = fields[-1]
            except IndexError:
                Trace.log(e_errors.ERROR, "ERROR:mc:aml2 bad CleanTapeVolumeFamily in configuration file")

        if self.mc_config.has_key('IdleTimeHome'):
            if (type(self.mc_config['IdleTimeHome']) == types.IntType and
                self.mc_config['IdleTimeHome'] > 20):
                self.idleTimeLimit = self.mc_config['IdleTimeHome']
            else:
                Trace.log(e_errors.INFO, "mc:aml2 IdleHomeTime is not defined or too small, default used")

        
        self.prepare=self.unload

        
        

    # retry function call
    def retry_function(self,function,*args):
        count = self.getNretry()
        rpcErrors = 0
        sts=("",0,"")
        while count > 0 and sts[0] != e_errors.OK:
            try:
                sts=apply(function,args)
                if sts[1] != 0:
                   Trace.log(e_errors.ERROR, 'function %s error %s'%(repr(function),sts[2])) 
                if sts[1] == 1 and rpcErrors < 2:  # RPC failure
                    time.sleep(10)
                    rpcErrors = rpcErrors + 1
                elif (sts[1] == 5 or         # requested drive in use
                      sts[1] == 8 or         # DAS was unable to communicate with AMU
                      sts[1] == 10 or        # AMU was unable to communicate with robot
                      #sts[1] == 34 or        # The aci request timed out
                      sts[1] == 24):         # requested volume in use
                    count = count - 1
                    time.sleep(20)
                else:
                    break
            except:
                exc,val,tb = e_errors.handle_error()
                return "ERROR", 37, str(val)   #XXX very ad-hoc!
                                 ## this is "command error" in aml2.py
        return sts
    
    # load volume into the drive;
    def load(self,
             external_label,    # volume external label
             drive,             # drive id
             media_type):       # media type
        import aml2
        return self.retry_function(aml2.mount,external_label, drive,media_type)
    
    # unload volume from the drive
    def unload(self,
               external_label,  # volume external label
               drive,           # drive id
               media_type):     # media type
        import aml2
        return self.retry_function(aml2.dismount,external_label, drive,media_type)

    def robotHome(self, arm):
        import aml2
        return self.retry_function(aml2.robotHome,arm)
    
    def robotStatus(self):
        import aml2
        return self.retry_function(aml2.robotStatus)

    def robotStart(self, arm):
        import aml2
        return self.retry_function(aml2.robotStart, arm)
    
    def insert(self, ticket):
        import aml2
        self.insertRA = None
        classTicket = { 'mcSelf' : self }
        ticket['timeOfCmd'] = time.time()
        ticket['medIOassign'] = self.mediaIOassign
        return self.retry_function(aml2.insert,ticket, classTicket)
        
    def eject(self, ticket):
        import aml2
        classTicket = { 'mcSelf' : self }
        ticket['medIOassign'] = self.mediaIOassign
        return self.retry_function(aml2.eject,ticket, classTicket)

    def robotHomeAndRestart(self, ticket):
        import aml2
        classTicket = { 'mcSelf' : self }
        ticket['robotArm'] = self.robotArm
        return self.retry_function(aml2.robotHomeAndRestart,ticket, classTicket)
    
    def getVolState(self, ticket):
        import aml2
        "get current state of the tape"
        external_label = ticket['external_label']
        media_type = ticket['media_type']
        rt = self.retry_function(aml2.view,external_label, media_type)
        Trace.trace( 11, "getVolState returned %s"%(rt,))
        if rt[5] == '\000':
            Trace.trace( 11, "RT5 is 0")
            state=''
        else :
            Trace.trace( 11, "RT5 is %s"%(rt[5],))
            state = rt[5]
        if not state and rt[2]:  # volumes not in the robot
            state = rt[2]
        return (rt[0], rt[1], rt[2], state)
        
    def cleanCycle(self, inTicket):
        import aml2
        #do drive cleaning cycle
        Trace.log(e_errors.INFO, 'mc:aml2 ticket='+repr(inTicket))
        classTicket = { 'mcSelf' : self }
        try:
            drive = inTicket['moverConfig']['mc_device']
        except KeyError:
            Trace.log(e_errors.ERROR, 'mc:aml2 no device field found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no device field found in ticket"
        
        driveType = drive[:2]  # ... need device type, not actual device
        cleanTime = self.driveCleanTime[driveType][0]  # clean time in seconds  
        driveCleanCycles = self.driveCleanTime[driveType][1]  # number of cleaning cycles
        vcc = volume_clerk_client.VolumeClerkClient(self.csc)
        min_remaining_bytes = 1
        vol_veto_list = []
        first_found = 0
        libraryManagers = inTicket['moverConfig']['library']
        if type(libraryManagers) == types.StringType:
            library = string.split(libraryManagers,".")
        elif type(libraryManagers) == types.ListType:
            library = string.split(libraryManagers[0],".")[0]
        else:
            Trace.log(e_errors.ERROR, 'mc:aml2 library_manager field not found in ticket.')
            status = 37
            return e_errors.DOESNOTEXIST, status, "no library_manager field found in ticket"
        v = vcc.next_write_volume(library,
                                  min_remaining_bytes, self.cleanTapeVolumeFamily, 
                                  vol_veto_list, first_found, exact_match=1)  # get which volume to use
        if v["status"][0] != e_errors.OK:
            Trace.log(e_errors.ERROR,"error getting cleaning volume:%s %s"%\
                      (v["status"][0],v["status"][1]))
            status = 37
            return v["status"][0], 0, v["status"][1]

        for i in range(driveCleanCycles):
            Trace.log(e_errors.INFO, "AML2 clean drive %s, vol. %s"%(drive,v['external_label']))
            rt = self.load(v['external_label'], drive, v['media_type']) 
            status = rt[1]
            if status != 0:      # mount returned error
                s1,s2,s3 = self.retry_function(aml2.convert_status,status)
                return s1, s2, s3
            
            time.sleep(cleanTime)  # wait cleanTime seconds
            rt = self.unload(v['external_label'], drive, v['media_type'])
            status = rt[1]
            if status != 0:      # dismount returned error
                s1,s2,s3 = self.retry_function(aml2.convert_status,status)
                return s1, s2, s3
            Trace.log(e_errors.INFO,"AML2 Clean returned %s"%(rt,))
 
        retTicket = vcc.get_remaining_bytes(v['external_label'])
        remaining_bytes = retTicket['remaining_bytes']-1
        vcc.set_remaining_bytes(v['external_label'],remaining_bytes,'\0', None)
        return (e_errors.OK, 0, None)

    def doWaitingInserts(self):
        #do delayed insertvols
        if self.workQueueClosed and len(self.work_list)==0:
            self.workQueueClosed = 0
            ticket = { 'function'  : 'insert',
                       'timeOfCmd' : self.timeInsert,
                       'ra'        : self.insertRA }
            self.DoWork( self.insert, ticket)
        return (e_errors.OK, 0, None) 

    def checkMyself(self):
        # do regularily scheduled internal checks
        if self.robotNotAtHome and (time.time()-self.lastWorkTime) > self.idleTimeLimit:
            self.robotNotAtHome = 0
            ticket = { 'function' : 'homeAndRestart', 'robotArm' : self.robotArm }
            sts = self.robotHomeAndRestart(ticket)
            self.lastWorkTime = time.time()

# STK robot loader server
class STK_MediaLoader(MediaLoaderMethods):

    def __init__(self, medch, max_work=1, csc=None):
        import STK
        ###max_work=1 # VERY BAD, BUT THIS IS ALL THAT CAN BE HANDLED CORRECTLY FOR NOW. JAB 2/16/00
        MediaLoaderMethods.__init__(self,medch,max_work,csc)
        self.prepare = self.unload
        self.SEQ_LOCK_DIR = "/tmp/enstore"
        self.SEQ_LOCK_FILE="stk_seq_lock"
        self.SEQ_LOCK=os.path.join(self.SEQ_LOCK_DIR, self.SEQ_LOCK_FILE)
        if not os.access(self.SEQ_LOCK_DIR,os.W_OK):
            os.mkdir(self.SEQ_LOCK_DIR)
        lockf = open (self.SEQ_LOCK, "w")
        writelock(lockf)  #holding write lock = right to bump sequence
        lockf.write("0")
        unlock(lockf)
        lockf.close()
        
        print "STK MediaLoader initialized"

    def next_seq(self):

        # First acquire the seq lock.  Once we have it, we have the exclusive right
        # to bump the sequence.  Lock will (I hope) properly serlialze the
        # waiters so that they will be services in the order of arrival.
        # Because we use file locks instead of semaphores, the system will
        # properly clean up, even on kill -9s.
        lockf = open (self.SEQ_LOCK, "r+")
        writelock(lockf)  #holding write lock = right to bump sequence
        sequence = lockf.readline()
        try:
            seq=string.atoi(sequence)
        except:
            exc,val,tb = e_errors.handle_error()
            seq=0
        seq = seq + 1
        if seq > 0xFFFE:
            seq = 1
        lockf.seek(0)
        lockf.write("%5.5d\n"%(seq,))
        unlock(lockf)
        lockf.close()
        return seq
    
    # retry function call
    def retry_function(self,function,*args):
        count = self.getNretry()
        sts=("",0,"")
        while count > 0 and sts[0] != e_errors.OK:
            try:
                sts=apply(function,args)
                if sts[1] != 0:
                   Trace.log(e_errors.ERROR, 'function %s  sts[1] %s  sts[2] %s  count %s'%(repr(function),sts[1],sts[2],count)) 
                if (sts[1] == 54 or          #IPC error
                    sts[1] == 68 or          #IPC error (usually)
                    sts[1] == 91):           #STATUS_VOLUME_IN_DRIVE (indicates failed communication between mc and fntt)
                    time.sleep(60)
                    count = count - 1
                else:
                    break
            except:
                exc,val,tb = e_errors.handle_error()
                return exc,0,""
        return sts
    
    # load volume into the drive;
    def load(self,
             external_label,    # volume external label
             drive,             # drive id
             media_type):       # media type
        import STK
        seq=self.next_seq()
        return self.retry_function(STK.mount,external_label,drive,media_type,seq)
    
    # unload volume from the drive
    def unload(self,
               external_label,  # volume external label
               drive,           # drive id
               media_type):     # media type
        import STK
        seq=self.next_seq()
        return self.retry_function(STK.dismount,external_label,drive,media_type,seq)

    def getVolState(self, ticket):
        import STK
        external_label = ticket['external_label']
        media_type = ticket['media_type']
        seq=self.next_seq()
        rt = self.retry_function(STK.query_volume,external_label,media_type,seq)
        Trace.trace( 11, "getVolState returned %s"%(rt,))
        if rt[3] == '\000':
            state=''
        else :
            state = rt[3]
            if not state and rt[2]:  # volumes not in the robot
                state = rt[2]
        return (rt[0], rt[1], rt[2], state)
        

# manual media changer
class Manual_MediaLoader(MediaLoaderMethods):
    def __init__(self, medch, max_work=10, csc=None):
        MediaLoaderMethods.__init__(self,medch,max_work,csc)
    def loadvol(self, ticket):
        if ticket['vol_ticket']['external_label']:
            os.system("mc_popup 'Please load %s'"%(ticket['vol_ticket']['external_label'],))
        return MediaLoaderMethods.loadvol(self,ticket)
    def unloadvol(self, ticket):
        if ticket['vol_ticket']['external_label']:
            os.system("mc_popup 'Please unload %s'"%(ticket['vol_ticket']['external_label']),)
        return MediaLoaderMethods.unloadvol(self,ticket)

    
# Raw Disk and stand alone tape media server
class RDD_MediaLoader(MediaLoaderMethods):
    def __init__(self, medch, max_work=1, csc=None):
        MediaLoaderMethods.__init__(self,medch,max_work,csc)


# "Shelf" manual media server - interfaces with OCS
class Shelf_MediaLoader(MediaLoaderMethods):
    """
      Reserving tape drives for the exclusive use of the Enstore-media_changer
      can be done by establishing an OCS Authorization Group inwhich the sole
      user is the enstore_userid and tape drive list consists soley of the
      enstore reserved drives. These drives and the enstore_userid must not be
      listed in any other Authorization Group as well. Section 7.3.2 of the
      OCS Installation/Administration Guide, Version 3.1, details this 
      mechanism.
    """
    status_message_dict = {
      'OK':        (e_errors.OK, "request successful"),
      'ERRCfgHst': (e_errors.NOACCESS, "mc:Shlf config OCShost incorrect"),
      'ERRNoLoHN': (e_errors.NOACCESS, "mc:Shlf local hostname not accessable"),
      'ERRPipe':   (e_errors.NOACCESS, "mc:Shlf no pipeObj"),
      'ERRHoNoRe': (e_errors.NOACCESS, "mc:Shlf remote host not responding"),
      'ERRHoCmd':  (e_errors.NOACCESS, "mc:Shlf remote host command unsuccessful"),
      'ERROCSCmd': (e_errors.NOACCESS, "mc:Shlf OCS not responding"),
      'ERRHoNamM': (e_errors.NOACCESS, "mc:Shlf remote host name match"),
      'ERRAloPip': (e_errors.MOUNTFAILED, "mc:Shlf allocate no pipeObj"),
      'ERRAloCmd': (e_errors.MOUNTFAILED, "mc:Shlf allocate failed"),
      'ERRAloDrv': (e_errors.MOUNTFAILED, "mc:Shlf allocate drive not available"),
      'ERRAloRsh': (e_errors.MOUNTFAILED, "mc:Shlf allocate rsh error"),
      'ERRReqPip': (e_errors.MOUNTFAILED, "mc:Shlf request no pipeObj"),
      'ERRReqCmd': (e_errors.MOUNTFAILED, "mc:Shlf request failed"),
      'ERRReqRsh': (e_errors.MOUNTFAILED, "mc:Shlf request rsh error"),
      'ERRDeaPip': (e_errors.DISMOUNTFAILED, "mc:Shlf deallocate no pipeObj"),
      'ERRDeaCmd': (e_errors.DISMOUNTFAILED, "mc:Shlf deallocate failed"),
      'ERRDeaRsh': (e_errors.DISMOUNTFAILED, "mc:Shlf deallocate rsh error"),
      'ERRDsmPip': (e_errors.DISMOUNTFAILED, "mc:Shlf dismount no pipeObj"),
      'ERRDsmCmd': (e_errors.DISMOUNTFAILED, "mc:Shlf dismount failed"),
      'ERRDsmRsh': (e_errors.DISMOUNTFAILED, "mc:Shlf dismount rsh error")
      }

    def status_message(self, s):
        if s in self.status_message_dict.keys():
            return self.status_message_dict[s][1]
        else:
            return s

    def status_code(self, s):
        if s in self.status_message_dict.keys():
            return self.status_message_dict[s][0]
        else:
            return e_errors.ERROR

        
    def __init__(self, medch, max_work=1, csc=None): #Note: max_work may need to be changed, tgj
        MediaLoaderMethods.__init__(self,medch,max_work,csc)
        self.prepare=self.unload #override prepare with dismount and deallocate
        
        fnstatusO = self.getOCSHost()
        fnstatus = self.getLocalHost()
        Trace.trace(e_errors.INFO,"Shelf init localHost=%s OCSHost=%s" % (self.localHost, self.ocsHost))
        if fnstatus == 'OK' and fnstatusO == 'OK' :
            index = string.find(self.localHost,self.ocsHost)
            if index > -1 :
                self.cmdPrefix = ""
                self.cmdSuffix = ""
            else :
                self.cmdPrefix = "rsh " + self.ocsHost + " '"
                self.cmdSuffix = "'"
                fnstatus = self.checkRemoteConnection()
                if fnstatus != 'OK' :
                    Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
                              (fnstatus, self.status_message(fnstatus)))
                    return
        else :
            ## XXX fnstatusR not defined at this point...
            #Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
            # (fnstatusR, self.status_message(fnstatusR))
            Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
                      (fnstatus, self.status_message(fnstatus)))
            return
        fnstatus = self.checkOCSalive()
        if fnstatus != 'OK' :
             Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
                       (fnstatus, self.status_message(fnstatus)))
             return
        #fnstatus = self.deallocateOCSdrive("AllTheTapeDrives")
        #if fnstatus != 'OK' :
        #     Trace.log(e_errors.ERROR, "ERROR:Shelf init %s %s" %
        #                   (fnstatus, self.status_message(fnstatus)))
        #     return
        Trace.log(e_errors.INFO, "Shelf init %s %s" % (fnstatus, self.status_message(fnstatus)))
        return

    def getOCSHost(self):
        "get the hostname of the OCS machine from the config server"
        fnstatus = 'OK'
        self.ocsHost = string.strip(self.mc_config['OCSclient'])
        index = string.find(self.ocsHost,".")
        if index == 0 :
            fnstatus = 'ERRCfgHst'
        return fnstatus
        
    def getLocalHost(self):
        "get the hostname of the local machine"
        fnstatus = 'OK'
        result = hostaddr.gethostinfo()
        self.localHost = result[0]
        return fnstatus
        
    def checkRemoteConnection(self):
        "check to see if remote host is there"
        fnstatus = 'OK'
        command = self.cmdPrefix + "echo $(hostname) ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf cRC Cmd=%s" % (command, ))
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRPipe'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf cRC rsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERRHoCmd'
                return fnstatus
        else :
            fnstatus = 'ERRHoNoRe'
            return fnstatus
        return fnstatus

    def checkOCSalive(self):
        "check to see if OCS is alive"
        fnstatus = 'OK'
        command = self.cmdPrefix + "ocs_left_allocated -l 0 ; echo $?"  + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf cOa Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRPipe'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf cOa rsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERROCSCmd'
                return fnstatus
        else :
            fnstatus = 'ERRHoNoRe'
            return fnstatus
        return fnstatus
        
    def allocateOCSdrive(self, drive):
        "allocate an OCS managed drive"
        fnstatus = 'OK'
        command = self.cmdPrefix + "ocs_allocate -T " + drive + " ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf aOd Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRAloPip'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf aOd rsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERRAloCmd'
                return fnstatus
            else :   # check if OCS allocated a different drive
                retstring = result[0]
                pos=string.find(retstring," "+drive)
                if pos == -1 :  # different drive was allocated 
                    fnstatus = 'ERRAloDrv'
                    pos=string.find(retstring," ")
                    if pos != -1 :
                        wrongdrive=string.strip(retstring[pos+1:])
                        Trace.log(e_errors.ERROR, "ERROR:Shelf aOd rsh wrongdrive=%s" % (wrongdrive,) )
                    fnstatusR = self.deallocateOCSdrive(drive)
                    return fnstatus
        else :
            fnstatus = 'ERRAloRsh'
            return fnstatus
        return fnstatus
        
    def mountOCSdrive(self, external_label, drive):
        "request an OCS managed tape"
        fnstatus = 'OK'
        command = self.cmdPrefix + "ocs_request -t " + drive + \
                  " -v " + external_label + " ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf mOd Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRReqPip'
            fnstatusR = self.deallocateOCSdrive(drive)
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf mOd rsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERRReqCmd'
                fnstatusR = self.deallocateOCSdrive(drive)
                return fnstatus
        else :
            fnstatus = 'ERRReqRsh'
            fnstatusR = self.deallocateOCSdrive(drive)
            return fnstatus
        return fnstatus

    def deallocateOCSdrive(self, drive):
        "deallocate an OCS managed drive"
        fnstatus = 'OK'
        if "AllTheTapeDrives" == drive :
            command = self.cmdPrefix + "ocs_deallocate -a " + \
                      " ; echo $?" + self.cmdSuffix
        else :
            command = self.cmdPrefix + "ocs_deallocate -t " + drive + \
                      " ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf dOd Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstatus = 'ERRDeaPip'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf dOd rsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0': #check if drive already deallocated (not an error)
                retstring = result[0]
                pos=string.find(retstring,"drive is already deallocated")
                if pos == -1 :  # really an error
                    fnstatus = 'ERRDeaCmd'
                    return fnstatus
        else :
            fnstatus = 'ERRDeaRsh'
            return fnstatus
        return fnstatus

    def unmountOCSdrive(self, drive):
        "dismount an OCS managed tape"
        fnstatus = 'OK'
        command = self.cmdPrefix + "ocs_dismount -t " + drive + \
                  " ; echo $?" + self.cmdSuffix
        Trace.log(e_errors.INFO, "Shelf uOd Cmd=%s" % (command,) )
        pipeObj = popen2.Popen3(command, 0, 0)
        if pipeObj is None:
            fnstat = 'ERRDsmPip'
            return fnstatus
        stat = pipeObj.wait()
        result = pipeObj.fromchild.readlines()  # result has returned string
        Trace.log(e_errors.INFO, "Shelf uOd rsh return strings=%s stat=%s" % (result, stat))
        if stat == 0:
            retval = result[len(result)-1][0]
            if retval != '0':
                fnstatus = 'ERRDsmCmd'
                return fnstatus
        else :
            fnstatus = 'ERRDsmRsh'
            return fnstatus
        return fnstatus

    def load(self, external_label, drive, media_type):
        "load a tape"
        fnstatus = self.allocateOCSdrive(drive)
        if fnstatus == 'OK' :
            fnstatus = self.mountOCSdrive(external_label, drive)
        if fnstatus == 'OK' :
            status = 0
        else :
            status = 1
            Trace.log(e_errors.ERROR, "ERROR:Shelf load exit fnst=%s %s %s" %
                      (status, fnstatus, self.status_message(fnstatus)))
        return self.status_code(fnstatus), status, self.status_message(fnstatus)

    def unload(self, external_label, drive, media_type):
        "unload a tape"
        fnstatusTmp = self.unmountOCSdrive(drive)
        fnstatus = self.deallocateOCSdrive(drive)
        Trace.log(e_errors.INFO, "Shelf unload deallocate exit fnstatus=%s" % (fnstatus,))
        if fnstatusTmp != 'OK' :
            Trace.log(e_errors.ERROR, "ERROR:Shelf unload deall exit fnst= %s %s" %
                      (fnstatus, self.status_message(fnstatus)))
            fnstatus = fnstatusTmp
        if fnstatus == 'OK' :
            status = 0
        else :
            status = 1
            Trace.log(e_errors.ERROR, "ERROR:Shelf unload exit fnst= %s %s" %
                      (fnstatus, self.status_message(fnstatus)))
        return self.status_code(fnstatus), status, self.status_message(fnstatus)

    def getNretry(self):
        numberOfRetries = 1
        return numberOfRetries

        
class MediaLoaderInterface(generic_server.GenericServerInterface):

    def __init__(self):
        # fill in the defaults for possible options
        self.max_work=7
        generic_server.GenericServerInterface.__init__(self)

    # define the command line options that are valid
    def options(self):
        return generic_server.GenericServerInterface.options(self)+\
               ["log=","max_work="]

    #  define our specific help
    def parameters(self):
        return "media_changer"

    # parse the options like normal but make sure we have a media changer
    def parse_options(self):
        interface.Interface.parse_options(self)
        # bomb out if we don't have a media_changer
        if len(self.args) < 1 :
            self.missing_parameter(self.parameters())
            self.print_help(),
            sys.exit(1)
        else:
            self.name = self.args[0]


if __name__ == "__main__" :
    Trace.init("MEDCHANGER")
    Trace.trace( 6, "media changer called with args: %s"%(sys.argv,) )

    # get an interface
    intf = MediaLoaderInterface()

    csc  = configuration_client.ConfigurationClient((intf.config_host, 
                                                     intf.config_port) )
    keys = csc.get(intf.name)
    try:
        mc_type = keys['type']
    except:
        exc,msg,tb=sys.exc_info()
        Trace.log(e_errors.ERROR, "MC Error %s %s"%(exc,msg))
        sys.exit(1)

    constructor=eval(mc_type)
    mc = constructor(intf.name, intf.max_work, (intf.config_host, intf.config_port))

    mc.handle_generic_commands(intf)
    
    while 1:
        try:
            #Trace.init(intf.name[0:5]+'.medc')
            Trace.log(e_errors.INFO, "Media Changer %s (re) starting"%
                      (intf.name,))
            mc.serve_forever()
        except SystemExit, exit_code:
            sys.exit(exit_code)
        except:
            mc.serve_forever_error("media changer")
            continue
    Trace.trace(6,"Media Changer finished (impossible)")
