#!/usr/bin/env python
import os
import sys
import string
import rexec
import file_clerk_client
import configuration_client
import errno

def readlayer(fullname,layer):
    (dir,fname)=os.path.split(fullname)
    fname = "%s/.(use)(%s)(%s)"%(dir,layer,fname)
    try:
        f = open(fname,'r')
    except:
        exc, msg, tb = sys.exc_info()
        print "exception: %s %s" % (str(exc), str(msg))
        return None
        
    l = f.readlines()
    f.close()
    return l
    
def get_l4(filename):
    l4_raw = readlayer(filename, 4)
    l4 = {}
    try:
        l4['external_label'] = l4_raw[0][:-1]  # volume
        l4['location_cookie'] = l4_raw[1][:-1]  # location cookie
        l4['size'] = long(l4_raw[2][:-1]) # file size
        l4['file_family'] = l4_raw[3][:-1] # file family
        l4['pnfs_name0'] = l4_raw[4][:-1]  # file name
        l4['pnfs_mapname'] = l4_raw[5][:-1]  # volmap name
        l4['pnfsid'] = l4_raw[6][:-1]  # pnfs id
        l4['pnfsvid'] = l4_raw[7][:-1]  # pnfs vid
        l4['bfid'] = l4_raw[8][:-1]  # bfid
        l4['drive'] = l4_raw[9][:-1]  # drive
    except IndexError:
        print "incomplete l4 %s"%(l4,)
    return l4
    
def write_layer(fullname, layer, value):
    (dir,file)=os.path.split(fullname)
    fname = "%s/.(use)(%s)(%s)"%(dir,layer,file)
    f = open(fname,'w')
    if type(value)!=type(''):
        value=str(value)
    f.write(value)
    f.close()
    
def change_file_name(file):
    # replace pnfs with pnfs/fs/usr
    orig = string.split(file, "/")
    new=['/pnfs','fs','usr'] # this is not always true, depends on the name of the mount point
    for i in range(2,len(orig)):
        new.append(orig[i])
    new_fn=string.join(new,'/')
    return new_fn
    
def compare(bfinfo, l4):
    #keys = l4.keys()
    keys=['external_label','location_cookie','size'] 
    for key in keys:
        if bfinfo[key] != l4[key]: break
    else:
        return 1
    return 0

def compare_all(bfinfo, l4):
    keys = l4.keys()
    #keys=['external_label','location_cookie','size'] 
    for key in keys:
        if key != 'file_family':
            if bfinfo[key] != l4[key]: break
            else:
                return 1
    return 0

def fix_pnfs_layers(file, bfid):
    # replace pnfs with pnfs/fs/usr
    #file = change_file_name(file)
    l4 = get_l4(file)
    value = (10*"%s\n")%(l4['external_label'],
                         l4['location_cookie'],
                         l4['size'],
                         l4['file_family'],
                         l4['pnfs_name0'],
                         l4['pnfs_mapname'],
                         l4['pnfsid'],
                         l4['pnfsvid'],
                         bfid,
                         l4['drive'])
    print "NEW REC",value
    #return
    print "fixing L1"
    write_layer(file, 1, bfid)
    write_layer(file, 4,value)

# create a new file or update its times
def touch(fname):
    import time
    t = int(time.time())
    try:
        os.utime(fname,(t,t))
    except os.error, msg:
        if msg.errno == errno.ENOENT:
            f = open(fname,'w')
            f.close()
        else:
            print "problem with pnfsFilename %s"%(fname,)
            raise os.error,msg

# read the value stored in the requested tag
def readtag(fullname, tag):
    (dir,fname)=os.path.split(fullname)
    fname = "%s/.(tag)(%s)"%(dir,tag)
    f = open(fname,'r')
    t = f.readlines()[0]
    f.close()
    return t

def usage():
    print "usage %s bfid"%(sys.argv[0],)


if __name__ == "__main__":    
    if len(sys.argv) != 2:
        usage()
        sys.exit(-1)
    host = os.environ.get('ENSTORE_CONFIG_HOST', 0)
    port = os.environ.get('ENSTORE_CONFIG_PORT', 0)
    port = int(port)
    csc = configuration_client.ConfigurationClient((host,port))

    fcc = file_clerk_client.FileClient(csc)
    bfinfo = fcc.bfid_info(sys.argv[1])
    # check if file exists
    try:
        os.stat(bfinfo['pnfs_name0'])
    except os.error, msg:
        if msg.errno == errno.ENOENT:
            print "file %s does not exist"%(bfinfo['pnfs_name0'],)
            sys.exit(-1)
    l1 = readlayer(bfinfo['pnfs_name0'], 1)[0]
    if bfinfo['bfid'] != l1:
        print "l1 %s bfid %s"%(l1,bfinfo['bfid']) 
        fix_it =  raw_input("fix? [y/n]")
        if fix_it == 'y':
            try:
                write_layer(bfinfo['pnfs_name0'], 1, bfinfo['bfid'])
                print "Layer 1 fixed"        
            except:
                exc, msg, tb = sys.exc_info()
                print "exception: %s %s" % (str(exc), str(msg))
        else:
            sys.exit(0)
    print "Layer 1 OK"        
    l4 = get_l4(bfinfo['pnfs_name0'])
    if not compare_all(bfinfo, l4):
        # find what is a file family
        ff = readtag(bfinfo['pnfs_name0'],'file_family')
        print "l4 %s bfinfo %s"%(l4, bfinfo)
        print "file family",ff
        fix_it =  raw_input("fix? [y/n]")
        if fix_it == 'y':
            try:
                value = (10*"%s\n")%(bfinfo['external_label'],
                                     bfinfo['location_cookie'],
                                     bfinfo['size'],
                                     ff,
                                     bfinfo['pnfs_name0'],
                                     bfinfo['pnfs_mapname'],
                                     bfinfo['pnfsid'],
                                     bfinfo['pnfsvid'],
                                     bfinfo['bfid'],
                                     bfinfo['drive'])
                print "NEW REC",value
                write_layer(bfinfo['pnfs_name0'], 4,value)
            except:
                exc, msg, tb = sys.exc_info()
                print "exception: %s %s" % (str(exc), str(msg))
        else:
            sys.exit(0)
    
