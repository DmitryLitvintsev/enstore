###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import time
import sys, os
import string
import random
import select
import errno
import socket

# enstore imports
import Trace
import e_errors
import checksum
import hostaddr
import socket_ext

def hex8(x):
    s=hex(x)[2:]  #kill the 0x
    if type(x)==type(1L): s=s[:-1]  # kill the L
    l = len(s)
    if l>8:
        raise OverflowError, x
    return '0'*(8-l)+s

# get an unused tcp port for control communication
def get_callback(use_multiple=0,fixed_ip=None,verbose=0):
    if use_multiple:
        msg = "Multiple interface not currently supported"
        Trace.log(e_errors.ERROR, msg)
        print msg

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if fixed_ip:
        s.bind((fixed_ip, 0))
        interface=hostaddr.interface_name(fixed_ip)
        if interface:
            status=socket_ext.bindtodev(sock.fileno(),interface)
            if status:
                Trace.log(e_errors.ERROR, "bindtodev(%s): %s"%(interface,os.strerror(status)))
    else:
        hostname, junk, ips = hostaddr.gethostinfo()
        s.bind(ips[0], 0)
    host, port = s.getsockname()
    return host, port, s
                

#send a message, with bytecount and rudimentary security
def write_tcp_raw(sock,msg):
    max_pkt_size=16384
    try:
        l = len(msg)
        ptr=0
        sock.send("%08d"%(len(msg),))
        salt=random.randint(11,99)
        sock.send("ENSTOR%s"%(salt,))
        while ptr<l:
            nwritten=sock.send(msg[ptr:ptr+max_pkt_size])
            if nwritten<=0:
                break
            ptr = ptr+nwritten
        sock.send(hex8(checksum.adler32(salt,msg,l)))
    except socket.error, detail:
        Trace.trace(6,"write_tcp_raw: socket.error %s"%(detail,))
        ##XXX Further sends will fail, our peer will notice incomplete message


# send a message which is a Python object
def write_tcp_obj(sock,obj):
    return write_tcp_raw(sock,repr(obj))

#recv with a timeout
def timeout_recv(sock,nbytes,timeout=15*60):
    fds,junk,junk = select.select([sock],[],[],timeout)
    if sock not in fds:
        return ""
    return sock.recv(nbytes)
    

# read a complete message
def read_tcp_raw(sock):
    tmp = timeout_recv(sock,8) 
    try:
        bytecount = string.atoi(tmp)
    except:
        bytecount = None
    if len(tmp)!=8 or bytecount is None:
        Trace.trace(6,"read_tcp_raw: bad bytecount %s"%(tmp,))
        return ""
    tmp = timeout_recv(sock,8) # the 'signature'
    if len(tmp)!=8 or tmp[:6] != "ENSTOR":
        Trace.trace(6,"read_tcp_raw: invalid signature %s"%(tmp,))
        return ""
    salt=string.atoi(tmp[6:])
    msg = ""
    while len(msg) < bytecount:
        tmp = timeout_recv(sock,bytecount - len(msg))
        if not tmp:
            break
        msg = msg+tmp
    if len(msg)!=bytecount:
        Trace.trace(6,"read_tcp_raw: bytecount mismatch %s != %s"%(len(msg),bytecount))
        return ""
    tmp = timeout_recv(sock,8)
    crc = string.atol(tmp, 16)  #XXX 
    mycrc = checksum.adler32(salt,msg,len(msg))
    if crc != mycrc:
        Trace.trace(6,"read_tcp_raw: checksum mismatch %s != %s"%(mycrc, crc))
        return ""
    return msg



def read_tcp_obj(sock) :
    s=read_tcp_raw(sock)
    if not s:
        raise "TCP connection closed"  #XXX This is not caught anywhere!!! cgw
    return eval(s)


if __name__ == "__main__" :
    import sys
    Trace.init("CALLBACK")
    Trace.trace(6,"callback called with args "+repr(sys.argv))

    c = get_callback()
    Trace.log(e_errors.INFO,"callback exit ok callback="+repr(c))





