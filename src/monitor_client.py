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

# enstore imports
import callback
import interface
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
MY_SERVER = "monitor_server"

class MonitorServerClient:

    def __init__( self, probe_server_addr,
                  html_server_addr,
                  timeout,
                  block_size,
                  block_count,
		  summary):
        self.u = udp_client.UDPClient()
	self.probe_server_addr = probe_server_addr
	self.html_server_addr = html_server_addr
        self.timeout = timeout
        self.block_size = block_size
        self.block_count = block_count
	self.summary = summary

    # send Active Monitor probe request
    def _send_probe (self, ticket):
        x = self.u.send( ticket, self.probe_server_addr, self.timeout, 10 )
        return x

    # send measurement to the html server
    def _send_measurement (self, ticket):
	try:
	    x = self.u.send( ticket, self.html_server_addr, self.timeout, 10 )
	except errno.errorcode[errno.ETIMEDOUT]:
	    x = {'status' : (e_errors.TIMEDOUT, None)}
        return x

    # ping a server like ENCP would
    def monitor_one_interface(self, remote_interface):

        c_hostip, c_port, c_socket = callback.get_callback(
            use_multiple=0,verbose=0)
        
        ticket= { 'work'           : 'simulate_encp_transfer',
                  'callback_addr' :    (c_hostip, c_port),
                  'remote_interface' : remote_interface,
                  'block_count' : self.block_count,
                  'block_size' : self.block_size
                  }

        try:
            ticket = self._simulate_encp_transfer(ticket, c_socket)
        except errno.errorcode[errno.ETIMEDOUT]:
            ticket['status'] = ('ETIMEDOUT', "failed to simulate encp")
            ticket['elapsed'] = self.timeout*10
            ticket['block_count'] = 0

        return ticket

    # ping a server like ENCP would
    def _simulate_encp_transfer(self, ticket, c_socket):

        reply=self._send_probe(ticket) #raises exeption on timeout
        #simulate the control socket between encp and the mover

        #when bad routing takes place an accept should take about 12 minutes to
        # retry given the number of tries and the exponential backoff.
        # we will use a select and the configurebale timeout instead
        # since no one will wait 12 minutes in practice
        
        r,w,ex = select.select([c_socket], [c_socket], [c_socket],
                               self.timeout)
        if not r :
	    if not self.summary:
		print "passive open did not hear back from monitor server via TCP"
            raise  errno.errorcode[errno.ETIMEDOUT]
        
        ms_socket, address = c_socket.accept()
        c_socket.close()
        returned_ticket = callback.read_tcp_obj(ms_socket)
        ms_socket.close()
        data_socket=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_socket.connect(returned_ticket['mover']['callback_addr'])
        data=data_socket.recv(1)
        if not data:
            raise "Server closed connection"
        bytes_received=len(data)
        t0=time.time()
        while bytes_received<self.block_size*self.block_count:
            data = data_socket.recv(self.block_size)
            if not data: #socket is closed
                raise "Server closed connection"
            bytes_received=bytes_received+len(data)
        ticket['elapsed']=time.time()-t0
        return ticket

    def send_measurement(self, measurement_dict):
        block_count = measurement_dict['block_count']
        block_size = measurement_dict['block_size']
        elapsed = measurement_dict['elapsed']
        callback_addr = measurement_dict['callback_addr'][0]
        remote_addr = measurement_dict['remote_interface']
        #be paranoid abou the address translation. not spending the time
        #to research it.
        try:
            callback_addr = socket.gethostbyaddr(callback_addr)[0]
            remote_addr = socket.gethostbyaddr(remote_addr)[0]
        except:
            pass
        
        rate = "%.4g" % ((block_count * block_size) / elapsed / (1024*1024))
        reply = self._send_measurement (
            {
            'work' : 'recieve_measurement',
            
            'measurement' : (
	    enstore_functions.format_time(time.time()),
	    enstore_functions.strip_node(callback_addr),
	    enstore_functions.strip_node(remote_addr),
            block_count,
            block_size,
            "%.4g" % (elapsed,),
            rate
            )
            }
            )
        return rate

    def flush_measurements(self):
        reply = self._send_measurement (
            {
            'work' : 'flush_measurements'
            }
            )
    
class MonitorServerClientInterface(generic_client.GenericClientInterface):

    def __init__(self, flag=1, opts=[]):
        self.do_parse = flag
        self.restricted_opts = opts
	self.summary = 0
	self.html_gen_host = None
	generic_client.GenericClientInterface.__init__(self)

    # define the command line options that are valid
    def options(self):
        if self.restricted_opts:
            return self.restricted_opts
        else:
            return self.help_options() + ["summary", "html_gen_host="]

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
        self.veto_item_dict = {}
        for v in vetos.keys():
            canon = self._canonicalize(v)
            self.veto_item_dict[canon] = (v, vetos[v])

    def is_vetoed_item(self, ip):
        ip_as_canon = self._canonicalize(ip)
        return self.veto_item_dict.has_key(ip_as_canon)

    def veto_info(self, ip):
        ip_as_canon = self._canonicalize(ip)
        #return (ip_text, reason_text)
        return self.veto_item_dict[ip_as_canon]

    def _canonicalize(self, some_ip) :
        return socket.gethostbyname(some_ip)
    
        
# this is called by the enstore saag interface
def do_real_work(summary, config_host, config_port, html_gen_host):
    csc = configuration_client.ConfigurationClient((config_host, config_port))
    config = csc.get('active_monitor')
    if config['status'] == (e_errors.OK, None):
        logc=log_client.LoggerClient(csc, MY_NAME, 'log_server')


        ip_list = get_all_ips(config_host, config_port, csc)
        vetos = Vetos(config.get('veto_nodes', {}))


        if html_gen_host:
            config['html_gen_host'] = html_gen_host

        summary_d = {enstore_constants.TIME: enstore_functions.format_time(time.time())}
        summary_d[enstore_constants.BASENODE] = enstore_functions.strip_node(os.uname()[1])
        summary_d[enstore_constants.NETWORK] = enstore_constants.UP  # assumption

        for ip in ip_list:
            host = socket.gethostbyaddr(ip)
            hostname = enstore_functions.strip_node(host[0])
            if vetos.is_vetoed_item(ip):
                if not summary:
                    print "Skipping %s" % (vetos.veto_info(ip),)
                break
            if not summary:
                print "Trying", host, 
            msc = MonitorServerClient(
                (ip,                      config['server_port']),
                (config['html_gen_host'], config['server_port']),
                config['default_timeout'],
                config['block_size'],
                config['block_count'],
                summary
                )
            measurement=msc.monitor_one_interface(ip)
            rate = msc.send_measurement(measurement)
            if measurement.has_key('status') and \
               not measurement['status'] == (e_errors.OK, None) :
                # we had a problem
                if not summary:
                    print "  Error.    Status is %s"%(measurement['status'],)
                summary_d[hostname] = enstore_constants.DOWN
                summary_d[enstore_constants.NETWORK] = enstore_constants.DOWN
            else:
                if not summary:
                    #pprint.pprint(measurement)
                    print "  Success.  Network rate measured at ",rate," MB/S"
                if rate == 0.0:
                    summary_d[hostname] = enstore_constants.DOWN
                    summary_d[enstore_constants.NETWORK] = enstore_constants.DOWN
                else:
                    summary_d[hostname] = enstore_constants.UP
        msc.flush_measurements()

        # add the name of the html file that will be created
        summary_d[enstore_constants.URL] = "%s"%(enstore_constants.NETWORKFILE,)
    else:
        # there was nothing about the monitor server in the config file
        summary_d = {}
    
    return summary_d

# we need this in order to be called by the enstore.py code
def do_work(intf):
    do_real_work(intf.summary, intf.config_host, intf.config_port, intf.html_gen_host)

if __name__ == "__main__":
    

    intf = MonitorServerClientInterface()
    
    Trace.init(MY_NAME)
    Trace.trace( 6, 'msc called with args: %s'%(sys.argv,) )

    do_work(intf)
