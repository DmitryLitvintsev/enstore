#!/usr/bin/env python
###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import os
import sys
import string
import time
import errno
import pprint
import socket
import select
import fcntl, FCNTL

# enstore imports
import callback
import interface
import hostaddr
import socket_ext
import generic_client
import backup_client
import udp_client
import Trace
import e_errors
import configuration_client
import enstore_constants
import enstore_functions
import log_client

MY_NAME = "MNTR_CLI"
MY_SERVER = "monitor"

SEND_TO_SERVER = "send_to_server"
SEND_FROM_SERVER = "send_from_server"

SERVER_CONNECTION_ERROR = "Server connection error"
CLIENT_CONNECTION_ERROR = "Client connection error"

class MonitorServerClient(generic_client.GenericClient):

    def __init__( self, csc,
                  monitor_server_addr,
                  html_server_addr,
                  html_dir,
                  refresh,
                  timeout,
                  block_size,
                  block_count,
                  summary ):
        self.u = udp_client.UDPClient()
        self.monitor_server_addr = monitor_server_addr
        self.html_server_addr = html_server_addr
        self.html_dir = html_dir
        self.refresh = refresh
        self.timeout = 10#timeout
        self.block_size = block_size
        self.block_count = block_count
        self.summary = summary

        #Get the addr to tell the client to call back to and get the listening
        # socket to listen with.
        localhost, localport, self.listen_sock = \
                   callback.get_callback(verbose=0)
        #Instead of using an actual mover, this is the addr that this server
        # must tell the client it will be listening (via listen_sock) on.
        self.localaddr = (localhost, localport)
        self.listen_sock.listen(1)
        
        #If socket.MSG_DONTWAIT isn't there add it, because it should be.
        if not hasattr(socket, "MSG_DONTWAIT"): #Python 1.5 test
            socket.MSG_DONTWAIT = None
            host_type = os.uname()[0]
            if host_type == 'Linux':
                socket.MSG_DONTWAIT = 64
            elif host_type[:4]=='IRIX':
                socket.MSG_DONTWAIT = 128

        
        generic_client.GenericClient.__init__(self, csc, MY_NAME)

    # send Active Monitor probe request
    def _send_probe (self, ticket):
        x = self.u.send( ticket, self.monitor_server_addr, self.timeout, 10 )
        return x

    # send measurement to the html server
    def _send_measurement (self, ticket):
        try:
            x = self.u.send( ticket, self.html_server_addr, self.timeout, 10 )
        except errno.errorcode[errno.ETIMEDOUT]:
            x = {'status' : (e_errors.TIMEDOUT, None)}
        return x

    #This function should only be called from simulate_encp_transfer.
    #data_sock: already connected tcp socket.
    #block_size and block_count: the size of the buffer to attempt to move
    # at a time and the number of them to move.
    #function: a string with one of two possible values "send" or "recv".
    # These are for accessing the socket.send() and socket.recv() functions.
    def _test_encp_transfer(self, data_sock, block_size, block_count,function):
        bytes_transfered = 0
        sendstr = "S"*block_size
        bytes_to_transfer = block_size * block_count
        t0=time.time() #Grab the current time.
        t1=time.time() #Reset counter to current time (aka zero).

        #Set args outside of the loop for performance reasons.
        if function == "send":
            args = (sendstr, socket.MSG_DONTWAIT)
            sock_read_list = []
            sock_write_list = [data_sock]
        else:  #if read
            args = (block_size,)
            sock_read_list = [data_sock]
            sock_write_list = []
    
        while bytes_transfered < bytes_to_transfer:
            r,w,ex = select.select(sock_read_list, sock_write_list,
                                   [data_sock], self.timeout)
            
            if w or r or ex:
                #if necessary make the send string the correct (smaller) size.
                bytes_left = bytes_to_transfer - bytes_transfered
                if w and bytes_left < block_size:
                    sendstr = "S"*bytes_left
                    args = (sendstr, socket.MSG_DONTWAIT)

                try:
                    #By handling the similarities of sends and recieves the
                    # same way, a lot of duplicate code is removed.  
                    transfer_function = getattr(data_sock, function)
                    return_value = apply(transfer_function, args)
                    
                    #For reads, we only care about the length sent...
                    if r:
                        return_value = len(return_value)
                    #Get the new number of bytes sent.
                    bytes_transfered = bytes_transfered + return_value

                    t1 = time.time() #t1 is now current time

                except socket.error, detail:
                    data_sock.close()
                    raise SERVER_CONNECTION_ERROR, detail[1]

            elif time.time() - t1 > self.timeout:
                data_sock.close()
                raise SERVER_CONNECTION_ERROR, os.strerror(errno.ETIMEDOUT)

        return time.time() - t0


    #Return the socket to use for the encp rate tests.
    #mon_serv_addr: A 2-tuple containing the host and port to connect to.
    def _open_data_socket(self, mon_serv_addr):
        #Create the TCP socket, remeber the current settings (to reset them
        # back later) and set the new file control flags.
        sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        flags = fcntl.fcntl(sock.fileno(), FCNTL.F_GETFL)
        fcntl.fcntl(sock.fileno(), FCNTL.F_SETFL,flags|FCNTL.O_NONBLOCK)

        for retry in xrange(self.timeout):
            try:
                sock.connect(mon_serv_addr)
                break #Success, so get out of the loop.
            except socket.error, detail:
                #We have seen that on IRIX, when the connection succeds, we
                # get an ISCONN error.
                if hasattr(errno, 'ISCONN') and detail[0] == errno.ISCONN:
                    break
                elif detail[0] == errno.EINPROGRESS:
                    pass #Keep trying.
                #A real or fatal error has occured.  Handle accordingly.
                else:
                    raise CLIENT_CONNECTION_ERROR, detail[1]

                time.sleep(1) #Wait a sec, so each pass is a second of timeout.
                
        else: #If we did not break out of the for loop, flag the error.
            raise SERVER_CONNECTION_ERROR, os.srterror(errno.ETIMEDOUT)

        #Success on the connection!  Restore flag values.
        fcntl.fcntl(sock.fileno(), FCNTL.F_SETFL, flags)

        return sock

    #Open up the client side of the control socket.
    #monitor_server_ip: The remote ip to connect to.  On this end of the
    # connection, it is needed for only one purpose, to chose an appropriate
    # interface for the connection.
    def _open_cntl_socket(self, monitor_server_ip):
        #wait for a responce
        r,w,ex = select.select([self.listen_sock], [], [self.listen_sock],
                               self.timeout)

        if not r:
            raise CLIENT_CONNECTION_ERROR, os.strerror(errno.ETIMEDOUT)

        #Wait for the client to connect creating the control socket.
        cntl_sock, address = self.listen_sock.accept()

        #For machines with multiple network interfaces, pick the best one.
        interface=hostaddr.interface_name(monitor_server_ip)
        if interface:
            status=socket_ext.bindtodev(cntl_sock.fileno(),interface)
            if status:
                Trace.log(e_errors.ERROR, "bindtodev(%s): %s" %
                          (interface,os.strerror(status)))
        
        monitor_server_callback_addr = callback.read_tcp_obj(cntl_sock)
        cntl_sock.close()

        #In a real encp connection the library manager tells encp what mover
        # to connect to.  This is why it is labeled as 'mover' even though
        # it will be connected to a monitor server for the rate tests.
        return monitor_server_callback_addr['mover']['callback_addr']


    #Ping a server like ENCP would.
    #See monitor_one_interface for info the argument ticket.
    def _simulate_encp_transfer(self, ticket):
        reply = {'status'     : (None, None),
                 'block_size' : ticket['block_size'],
                 'block_count': ticket['block_count']}

        #A little easier to read now.
        mon_serv_ip = ticket['server_addr'][0]
        localaddr = ticket['client_addr']

        #Simulate the opening and initial handshake of the control socket.
        try:
            mon_serv_callback_addr = self._open_cntl_socket(mon_serv_ip)
            data_sock = self._open_data_socket(mon_serv_callback_addr)

            if not data_sock:
                raise CLIENT_CONNECTION_ERROR, "no connection established"
            
        except CLIENT_CONNECTION_ERROR, detail:
            raise CLIENT_CONNECTION_ERROR, detail
        except SERVER_CONNECTION_ERROR, detail:
            raise CLIENT_CONNECTION_ERROR, detail

        #Now that all of the socket connections have been opened, let the
        # transfers begin.
        try:
            if ticket['transfer'] == SEND_TO_SERVER:
                self._test_encp_transfer(data_sock, ticket['block_size'],
                                         ticket['block_count'], "send")

                reply['elapsed'] = -1

            elif ticket['transfer'] == SEND_FROM_SERVER:
                reply['elapsed'] = self._test_encp_transfer(
                    data_sock,ticket['block_size'], ticket['block_count'],
                    "recv")
        except CLIENT_CONNECTION_ERROR, detail:
            raise CLIENT_CONNECTION_ERROR, detail
        except SERVER_CONNECTION_ERROR, detail:
            raise SERVER_CONNECTION_ERROR, detail

        #If we get here, the status is ok.
        reply['status'] = ('ok', None)
        #Return the reply.
        return reply

    
    #Ping a server like ENCP would.
    #server_address: 2-tuple container the monitor servers host and port
    #transfer: this is a string with one of two values: SEND_TO_SERVER or
    # SEND_FROM_SERVER.
    def monitor_one_interface(self, server_address, transfer):
        #Create the ticket that will be send to the monitor server to start
        # the rate test process.
        ticket= { 'work'             : 'simulate_encp_transfer',
                  'transfer'         : transfer,
                  'client_addr'      : self.localaddr,
                  'server_addr'      : server_address,
                  'block_count'      : self.block_count,
                  'block_size'       : self.block_size,
                  }

        try:
            #Send the request to the server.
            send_id = self.u.send_deferred(ticket, server_address)

            #Execute the rate test with the server.
            read_measurment = self._simulate_encp_transfer(ticket)

            #Get the rate measurement back from the server.
            write_measurement = self.u.recv_deferred(send_id, timeout = 30)

            #Since the direction data is being sent influences which rate
            # we care about, pick the correct one. (The other is bogus anyway.)
            if transfer == SEND_TO_SERVER:
                reply = write_measurement
            elif transfer == SEND_FROM_SERVER:
                reply = read_measurment
            else:
                reply['status'] = ('INVALIDACTION', "failed to simulate encp")

        except CLIENT_CONNECTION_ERROR, detail:
            reply = {}
            reply['status'] = (CLIENT_CONNECTION_ERROR, detail)
            reply['elapsed'] = self.timeout*10
            reply['block_count'] = 0

        except SERVER_CONNECTION_ERROR, detail:
            reply = {}
            reply['status'] = (SERVER_CONNECTION_ERROR, detail)
            reply['elapsed'] = self.timeout*10
            reply['block_count'] = 0
        
        return reply

    #Take the elapsed time and the amount of data sent/recieved and calculate
    # the rate.
    #See _simulate_encp_transfer for more info on measurement_dict.
    def calculate_rate(self, measurement_dict):
        if measurement_dict['status'] != ('ok', None):
            measurement = { 'elapsed':0.0, 'rate':0.0}
            return measurement
        
        block_count = measurement_dict['block_count']
        block_size = measurement_dict['block_size']
        elapsed = measurement_dict['elapsed']
        
        rate = (block_count * block_size) / elapsed / (1024*1024)
        measurement = { 'elapsed':elapsed, 'rate':rate,
                        'status':measurement_dict['status'] }
        return measurement

    #Send the rate results to the monitor server that is configured to handle
    # the creation of the html output.
    #See calculate_rate for more info on the arguments.
    def send_measurement(self, read_measurement, write_measurement):
        try:
            #Try to acquire the host name from the host ip.
            client_addr = socket.gethostbyaddr(self.localaddr[0])[0]
            server_addr = socket.gethostbyaddr(self.monitor_server_addr[0])[0]
        except:
            client_addr = self.localaddr[0]
            server_addr = self.monitor_server_addr

        #pack the info.
        ticket = {
            'work' : 'recieve_measurement',
            'refresh' : self.refresh,
            'measurement': (
            enstore_functions.format_time(time.time()),
            enstore_functions.strip_node(client_addr),
            enstore_functions.strip_node(server_addr),
            "%.4g" % (read_measurement['rate'],),
            "%.4g" % (write_measurement['rate'],)
            )}

        #Send the information to the web server node.
        self._send_measurement(ticket)
            
    def flush_measurements(self):
        reply = self._send_measurement (
            {
            'work'   : 'flush_measurements',
            'dir'    : self.html_dir,
            'refresh': self.refresh
            }
            )

    #Either prints out message to screen, stores info. in a dictionary or both.
    #hostname: The current node that had its rate checked.
    #summary_d: The dictionary to add info to.
    #summary: Command line toggle, off don't print rates, on do print rates.
    #read_rate, write_rate: dictionaries with three keys: rate, elapsed and
    
    def update_summary(self, hostname, summary_d, summary,
                       read_rate, write_rate):

        if read_rate['status'] == ('ok', None) and \
           write_rate['status'] == ('ok', None):
            if not summary:
                print "Network rate measured at %.4g MB/S recieving " \
                      "and %.4g MB/S sending." % \
                      (read_rate['rate'], write_rate['rate'])
            else:
                summary_d[hostname] = enstore_constants.UP

        else:
            if not summary:
                print "  Error.    Status is (%s,%s)"%(read_rate['status'],
                                                       write_rate['status'])
            summary_d[hostname] = enstore_constants.WARNING
            summary_d[enstore_constants.NETWORK] = enstore_constants.WARNING

    #Check on alive status.
    #Override alive definition inside generic_client.
    def alive(self, server, rcv_timeout=0, tries=0):
        if self.monitor_server_addr:
            ip = self.monitor_server_addr[0]
        else:
            ip = self.localaddr[0]

        try:
            x = self.u.send({'work':'alive'},
                            (ip, enstore_constants.MONITOR_PORT),
                            rcv_timeout, tries)
            x['address'] = (ip, x['address'][1])
        except errno.errorcode[errno.ETIMEDOUT]:
            Trace.trace(14,"alive - ERROR, alive timed out")
            x = {'status' : (e_errors.TIMEDOUT, None)}
            print x
        except socket.error, message:
            Trace.trace(14,"alive - ERROR, connection failed")
            x = {'status' : (message.args[0], ip)}
            print x
        return x

class MonitorServerClientInterface(generic_client.GenericClientInterface):

    def __init__(self, flag=1, opts=[]):
        self.do_parse = flag
        self.restricted_opts = opts
        self.summary = 0
        self.html_gen_host = None
        self.name = MY_SERVER
        self.alive_rcv_timeout = 10
        self.alive_retries = 3
        self.hostip = ""
        generic_client.GenericClientInterface.__init__(self)

    # define the command line options that are valid
    def options(self):
        if self.restricted_opts:
            return self.restricted_opts
        else:
            return self.help_options() +  self.alive_options() +\
                   ["summary", "html-gen-host=", "hostip="]

class Vetos:
    """
    A small class to manage the veto dictionary that is provided
    by the configuration server. The administator does not
    want us to probe these nodes.
    """
    def __init__(self, vetos):
        # vetos is a list in confg file format
        # this is a dictionary with keys as
        # possibly (non canonical) IP addresses. Ip or DNS names
        # and the value field being a reason why it is in the veto list

        # don't send to yourself
        vetos[socket.gethostname()] = 'thishost'

        self.veto_item_dict = {}
        for v in vetos.keys():
            try: #If DNS fails, move to the next
                canon = self._canonicalize(v)
                self.veto_item_dict[canon] = (v, vetos[v])
            except socket.error:
                continue

    def is_vetoed_item(self, ip):
        ip_as_canon = self._canonicalize(ip)
        return self.veto_item_dict.has_key(ip_as_canon)

    def veto_info(self, ip):
        ip_as_canon = self._canonicalize(ip)
        #return (ip_text, reason_text)
        return self.veto_item_dict[ip_as_canon]

    def _canonicalize(self, some_ip) :
        return socket.gethostbyname(some_ip)
    
        
def get_all_ips(config_host, config_port, csc):
    """
    inquire the configuration server, return a list
    of every  IP address involved in Enstore  
    """

    ## What if we cannot get to config server
    x = csc.u.send({"work":"reply_serverlist"},
                   (config_host, config_port))
    if x['status'][0] != 'ok': raise "error from config server"
    server_dict = x['server_list']
    ip_dict = {}
    for k in server_dict.keys():
        #assume we can get to config server since we could above
        details = csc.get(k)
        if details.has_key('data_ip'):
            ip = details['data_ip']     #check first if a mover
        elif details.has_key('hostip'):
            ip = details['hostip']      #other server
        else:
            continue
        ip = socket.gethostbyname(ip)  #canonicalize int dot notation
        ip_dict[ip] = 1                #dictionary will strike duplicates
    return ip_dict.keys()              #keys of the dict is a tuple of IPs


#Return a list of valid hosts and a class representing nodes to avoid.
#intf: instance of interface class
#config: return val from a configuration_client.get() function
#csc: configuration client instance.
def get_host_list(csc, config_host, config_port, hostip=None):
    config = csc.get('monitor')
    
    vetos = Vetos(config.get('veto_nodes', {}))

    #If they specified one specific machines, return a list of one item.
    if hostip:
        
        host_list = (socket.gethostbyaddr(hostip)[0],
                     socket.gethostbyname(hostip))

        return [host_list], vetos

    #Compile the list of servers to test.
    if config['status'] == (e_errors.OK, None):
        logc=log_client.LoggerClient(csc, MY_NAME, 'log_server')

        ip_list = get_all_ips(config_host, config_port, csc)

        host_list = []
        for ip in ip_list:
            host_list.append((socket.gethostbyaddr(ip)[0], ip))
        host_list.sort()

    return host_list, vetos
    



# this is called by the enstore saag interface
def do_real_work(summary, config_host, config_port, html_gen_host,
                 hostip=None):
    
    csc = configuration_client.ConfigurationClient((config_host, config_port))
    config = csc.get('monitor')

    if not config:
        summary_d = {'monitor' : " not found in config dictionary."}
        if summary:
            return summary_d
        else:
            return

    #Get a list of hosts, and a class instance of host to avoid.
    host_list, vetos = get_host_list(csc, config_host, config_port, hostip)
    
    if html_gen_host:
        config['html_gen_host'] = html_gen_host

    summary_d = {enstore_constants.TIME:
                 enstore_functions.format_time(time.time())}
    summary_d[enstore_constants.BASENODE] = enstore_functions.strip_node(
        os.uname()[1])
    summary_d[enstore_constants.NETWORK] = enstore_constants.UP  # assumption
    summary_d[enstore_constants.URL] = "%s"%(enstore_constants.NETWORKFILE,)
    
    for host, ip in host_list:
        hostname = enstore_functions.strip_node(host)
        if vetos.is_vetoed_item(ip):
            if not summary:
                print "Skipping %s" % (vetos.veto_info(ip),)
            continue
        if not summary:
            print "Trying", host
        msc = MonitorServerClient(
            (config_host, config_port),
            (ip,                      enstore_constants.MONITOR_PORT),
            (config['html_gen_host'], enstore_constants.MONITOR_PORT),
            config['html_dir'],
            config['refresh'],
            config['default_timeout'],
            config['block_size'],
            config['block_count'],
            summary
            )
        
        
        #Test rate sending from the server.  The rate info for read time
        # information is stored in msc.measurement.
        read_measurement = msc.monitor_one_interface(
            (ip, enstore_constants.MONITOR_PORT), SEND_FROM_SERVER)
        if read_measurement['status'] == ('ok', None):
            read_rate = msc.calculate_rate(read_measurement)
        else:
            read_rate = {'elapsed':0, 'rate':0,
                         'status':('READ_ERROR',
                                   read_measurement['status'][1])} #errno msg

        #Test rate sending to the server.  Since, the time is recorded on
        # the other end use the value returned, and not the one stored
        # in msc.measurement (which is for read info).
        write_measurement = msc.monitor_one_interface(
            (ip, enstore_constants.MONITOR_PORT), SEND_TO_SERVER)
        if write_measurement['status'] == ('ok', None):
            write_rate = msc.calculate_rate(write_measurement)
        else:
            write_rate = {'elapsed':0, 'rate':0,
                         'status':('WRITE_ERROR',
                                   write_measurement['status'][1])} #errno msg

        #Send the information to the html server node.
        msc.send_measurement(read_rate, write_rate)

        #Does some summary stuff.
        msc.update_summary(hostname, summary_d, summary, read_rate,
                           write_rate)

        #Cleanup stuff..
        if msc:
            msc.flush_measurements()
            msc.listen_sock.close()
            
    if summary:
        print summary_d

    return summary_d

def do_work(intf):
    if hasattr(intf, "help") and intf.help:
        intf.print_help()
        return
    elif hasattr(intf, "usage_line") and intf.usage_line:
        intf.print_usage_line()
        return

    if hasattr(intf, "alive") and intf.alive:
        msc = MonitorServerClient(
            (intf.config_host, intf.config_port),
            (intf.hostip, enstore_constants.MONITOR_PORT),
            None, None, None, None, None, None, None)
        msc.handle_generic_commands(intf.name, intf)
    
    else:
        do_real_work(intf.summary, intf.config_host, intf.config_port,
                     intf.html_gen_host, hostip=intf.hostip)

if __name__ == "__main__":
    

    intf = MonitorServerClientInterface()
    
    Trace.init(MY_NAME)
    Trace.trace( 6, 'msc called with args: %s'%(sys.argv,) )

    do_work(intf)
