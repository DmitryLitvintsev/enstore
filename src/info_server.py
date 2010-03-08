#!/usr/bin/env python

##############################################################################
#
# $Id$
#
##############################################################################

'''
Readonly access to file and volume database
'''

# system import
import os
import sys
import string
# import pprint

# enstore import
import dispatching_worker
import generic_server
import Trace
import e_errors
import enstore_constants
#import monitored_server
import event_relay_messages
import time
import hostaddr
import callback
import socket
import select
import edb
import esgdb
import enstore_functions2
import enstore_functions3
import volume_clerk
import file_clerk

MY_NAME = enstore_constants.INFO_SERVER   #"info_server"
MAX_CONNECTION_FAILURE = 5

# err_msg(fucntion, ticket, exc, value) -- format error message from
# exceptions

def err_msg(function, ticket, exc, value, tb=None):
	return function+' '+`ticket`+' '+str(exc)+' '+str(value)+' '+str(tb)

class Interface(generic_server.GenericServerInterface):
	def __init__(self):
		generic_server.GenericServerInterface.__init__(self)

	def valid_dictionary(self):
		return (self.help_options)

class Server(file_clerk.FileClerkInfoMethods,
	     volume_clerk.VolumeClerkInfoMethods,
	     generic_server.GenericServer):

	def __init__(self, csc):
		self.debug = 0
		generic_server.GenericServer.__init__(self, csc, MY_NAME,
						function = self.handle_er_msg)
		Trace.init(self.log_name)
		self.connection_failure = 0
		## We no longer need to call __init__() from dispatching
		## worker since it is called from the file and volume clerk
		## inits below.
		#   att = self.csc.get(MY_NAME)
		#   dispatching_worker.DispatchingWorker.__init__(self,
		#	   (att['hostip'], att['port']))
		file_clerk.MY_NAME = MY_NAME
		volume_clerk.MY_NAME = MY_NAME
		file_clerk.FileClerkInfoMethods.__init__(self, csc)
		volume_clerk.VolumeClerkInfoMethods.__init__(self, csc)

		# get database connection
		dbInfo = self.csc.get("database")
		try:
			self.file = edb.FileDB(host=dbInfo['db_host'],
					       port=dbInfo['db_port'],
					       user=dbInfo['dbuser'],
					       auto_journal=0)
		except:
			exc_type, exc_value = sys.exc_info()[:2]
			msg = "%s %s %s" % (str(exc_type), str(exc_value),
					    "IS POSTMASTER RUNNING?")
			Trace.log(e_errors.ERROR,msg)
			Trace.alarm(e_errors.ERROR,msg, {})
			Trace.log(e_errors.ERROR,
			     "CAN NOT ESTABLISH DATABASE CONNECTION ... QUIT!")
			sys.exit(1)

		self.db = self.file.db
		self.volume = edb.VolumeDB(host=dbInfo['db_host'],
					   port=dbInfo['db_port'],
					   user=dbInfo['dbuser'],
					   auto_journal=0, rdb=self.db)
		self.sgdb = esgdb.SGDb(self.db)


		# setup the communications with the event relay task
		self.event_relay_subscribe([event_relay_messages.NEWCONFIGFILE])

		self.set_error_handler(self.info_error_handler)
		return

	def reinit(self):
		Trace.log(e_errors.INFO, "(Re)initializing server")

		# stop the communications with the event relay task
		self.event_relay_unsubscribe()

		#Close the connections with the database.
		self.close()

		self.__init__(self.csc.server_address)

	def info_error_handler(self, exc, msg, tb):
		__pychecker__ = "unusednames=tb"
		# is it PostgreSQL connection error?
		#
		# This is indeed a OR condition implemented in if-elif-elif-...
		# so that each one can be specified individually
		if exc == edb.pg.ProgrammingError and str(msg)[:13] == 'server closed':
			self.reconnect(msg)
		elif exc == ValueError and str(msg)[:13] == 'server closed':
			self.reconnect(msg)
		elif exc == TypeError and str(msg)[:10] == 'Connection':
			self.reconnect(msg)
		elif exc == ValueError and str(msg)[:13] == 'no connection':
			self.reconnect(msg)
		self.reply_to_caller({'status':(str(exc),str(msg), 'error'),
			'exc_type':str(exc), 'exc_value':str(msg)} )

	# reconnect() -- re-establish connection to database
	def reconnect(self, msg="unknown reason"):
		try:
			self.file.reconnect()
			Trace.alarm(e_errors.WARNING, "RECONNECT", "reconnect to database due to "+str(msg))
			self.connection_failure = 0
			self.db = self.file.db
			self.volume.db = self.db
			self.sgdb.db = self.db
		except:
			Trace.alarm(e_errors.ERROR, "RECONNECTION FAILURE",
				"Is database server running on %s:%d?"%(self.file.host,
				self.file.port))
			self.connection_failure = self.connection_failure + 1
			if self.connection_failure > MAX_CONNECTION_FAILURE:
				pass	# place holder for future RED BALL

	# The following are local methods
	# get a port for the data transfer
	# tell the user I'm your info clerk and here's your ticket
	def get_user_sockets(self, ticket):
		try:
			addr = ticket['callback_addr']
			if not hostaddr.allow(addr):
				return 0
			info_clerk_host, info_clerk_port, listen_socket = callback.get_callback()
			listen_socket.listen(4)
			ticket["info_clerk_callback_addr"] = (info_clerk_host, info_clerk_port)
			self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.control_socket.connect(addr)
			callback.write_tcp_obj(self.control_socket, ticket)

			r,w,x = select.select([listen_socket], [], [], 15)
			if not r:
				listen_socket.close()
				return 0
			data_socket, address = listen_socket.accept()
			if not hostaddr.allow(address):
				data_socket.close()
				listen_socket.close()
				return 0
			self.data_socket = data_socket
			listen_socket.close()
		# catch any error and keep going. server needs to be robust
		except:
			exc, msg = sys.exc_info()[:2]
			Trace.handle_error(exc,msg)
			return 0
		return 1

	# close the database connection
	def close(self):
		self.db.close()
		return

	####################################################################

	# turn on/off the debugging
	def debugging(self, ticket):
		self.debug = ticket.get('level', 0)
		print 'debug =', self.debug

	# These need confirmation
	def quit(self, ticket):
		self.db.close()
		dispatching_worker.DispatchingWorker.quit(self, ticket)
		# can't go this far
		# self.reply_to_caller({'status':(e_errors.OK, None)})
		# sys.exit(0)

	def file_info(self, ticket):

		bfid, record = self.extract_bfid_from_ticket(ticket)
		if not bfid:
			return #extract_bfid_from_ticket handles its own errors.
		self.__find_file(bfid, ticket, error_target="file_info",
				 item_name = "file_info",
				 include_volume_info = True)
		self.reply_to_caller(ticket)
		return

	#Underlying function that powers find_file_by_path(),
	# find_file_by_pnfsid() and find_file_by_location().
	#
	# item_name is used by file_info() to set the information into
	# as a tuple that is a member of the ticket with item_name as the
	# key.
	#
	# error_target is a string describing what is being looked for.
	def __find_file(self, bfid, ticket, error_target, item_name = None,
			include_volume_info = False):
		#Get the file information from the database.
		finfo  = getattr(self, 'file', {})[bfid]
		if not finfo:
			ticket['status'] = (e_errors.NO_FILE,
				"%s: %s not found" % (MY_NAME, error_target))
			Trace.log(e_errors.ERROR, "%s" % (ticket,))
			return
		if include_volume_info:
			#Get the volume information from the database.
			vinfo  = getattr(self, 'volume', {})[finfo['external_label']]
			if not vinfo:
				ticket['status'] = (e_errors.NO_VOLUME,
						    "%s: %s not found" % (MY_NAME, error_target))
				Trace.log(e_errors.ERROR, "%s" % (ticket,))
				return

		#Combine the file and volume information together.
		combined_dict = {}
		for key in finfo.keys():
			combined_dict[key] = finfo[key]
		if include_volume_info:
			for key in vinfo.keys():
				combined_dict[key] = vinfo[key]

		#Put the information into the ticket in the correct place.
	        if ticket.has_key('file_list'):
			ticket['file_list'].append(combined_dict)
			return
		else:
			if item_name:
				ticket[item_name] = combined_dict
				print "ticket:", ticket
			else:
				for key in combined_dict.keys():
					ticket[key] = combined_dict[key]
		ticket["status"] = (e_errors.OK, None)
		return

	# find_file_by_path() -- find a file using pnfs_path
	def __find_file_by_path(self, ticket):
		pnfs_path = self.extract_value_from_ticket("pnfs_name0", ticket,
							  fail_None = True)
		if not pnfs_path:
			return #extract_value_from_ticket handles its own errors.
		q="select bfid from file where pnfs_path='%s'"%(pnfs_path,)
		res=[]
		try:
			res = self.file.query_dictresult(q)
			#
			# edb module raises underlying DB errors as EnstoreError.
			#
		except e_errors.EnstoreError, msg:
			ticket['status'] = (msg.type,
					    "failed to find bfid for pnfs_path %s"%(pnfs_path,))
			return
		except:
			ticket['status'] = (e_errors.INFO_SERVER_ERROR,
					    "failed to find bfid for pnfs_path %s"%(pnfs_path,))
			return
		if not res :
			ticket['status'] = (e_errors.NO_FILE,
					    "%s: %s not found" % (MY_NAME, pnfs_path))
			Trace.log(e_errors.ERROR, "%s" % (ticket,))
			return
		if len(res)>1:
			ticket["status"] = (e_errors.OK, None)
			ticket['file_list'] = []
			for db_info in res:
				bfid = db_info.get('bfid')
				self.__find_file(bfid, ticket, pnfs_path)
		else:
			bfid = res[0].get('bfid')
			self.__find_file(bfid, ticket, pnfs_path)
		return

	# find_file_by_path() -- find a file using pnfs id
	def find_file_by_path(self, ticket):
		self.__find_file_by_path(ticket)
		self.reply_to_caller(ticket)
		return

	#This version can handle replying with a large number of file matches.
	def find_file_by_path2(self, ticket):
		self.__find_file_by_path(ticket)
		self.send_reply_with_long_answer(ticket)
		return

	# find_file_by_pnfsid() -- find a file using pnfs id
	def __find_file_by_pnfsid(self, ticket):
		pnfs_id = self.extract_value_from_ticket("pnfsid", ticket,
							  fail_None = True)
		if not pnfs_id:
			return #extract_value_from_ticket handles its own errors.
		if not enstore_functions3.is_pnfsid(pnfs_id):
			message = "pnfsid %s not valid" % \
				  (pnfs_id,)
			ticket["status"] = (e_errors.WRONG_FORMAT, message)
			Trace.log(e_errors.ERROR, message)
			self.reply_to_caller(ticket)
			return
		q = "select bfid from file where pnfs_id = '%s'" % (pnfs_id,)
		res=[]
		try:
			res = self.file_query_dictresult(q)
			#
			# edb module raises underlying DB errors as EnstoreError.
			#
		except e_errors.EnstoreError, msg:
			ticket['status'] = (msg.type,
					    "failed to find bfid for pnfs_id %s"%(pnfs_id,))

			return
		except:
			ticket['status'] = (e_errors.INFO_SERVER_ERROR,
					    "failed to find bfid for pnfs_id %s"%(pnfs_id,))
			return
		if not res :
			ticket['status'] = (e_errors.NO_FILE,
					    "%s: %s not found" % (MY_NAME, pnfs_id))
			Trace.log(e_errors.ERROR, "%s" % (ticket,))
			return

		if len(res)>1:
			ticket['status'] = (e_errors.TOO_MANY_FILES,
				"%s: %s %s matches found" % \
					    (MY_NAME, pnfs_id, len(res)))
			ticket['file_list'] = []
			for db_info in res:
				bfid = db_info.get('bfid')
				self.__find_file(bfid, ticket, pnfs_id)
		else:
			bfid = res[0].get('bfid')
			self.__find_file(bfid, ticket, pnfs_id)
		return ticket

	# find_file_by_pnfsid() -- find a file using pnfs id
	def find_file_by_pnfsid(self, ticket):
		self.__find_file_by_pnfsid(ticket)
		self.reply_to_caller(ticket)
		return

	#This version can handle replying with a large number of file matches.
	def find_file_by_pnfsid2(self, ticket):
		self.__find_file_by_pnfsid(ticket)
		self.send_reply_with_long_answer(ticket)
		return


	# find_file_by_location() -- find a file using pnfs_path
	def __find_file_by_location(self, ticket):

		#label = self.extract_external_label_from_ticket(ticket):
		external_label, record = self.extract_external_label_from_ticket(ticket)
		if not external_label:
			return #extract_external_lable_from_ticket handles its own errors.

		location_cookie = self.extract_value_from_ticket(
			"location_cookie", ticket, fail_None = True)
		if not location_cookie:
			return #extract_value_from_ticket handles its own errors.
		if not enstore_functions3.is_location_cookie(location_cookie):
			message = "volume location %s not valid" % \
				  (location_cookie,)
			ticket["status"] = (e_errors.WRONG_FORMAT, message)
			Trace.log(e_errors.ERROR, message)
			self.reply_to_caller(ticket)
			return

		q = "select \
			bfid \
			from file, volume \
			where \
				file.volume = volume.id and \
				label = '%s' and \
				location_cookie = '%s';" % \
		(external_label, location_cookie)
		res=[]
		try:
			res=self.file.query_dictresult(q)
			#
			# edb module raises underlying DB errors as EnstoreError.
			#
		except e_errors.EnstoreError, msg:
			ticket['status'] = (msg.type,
					    "failed to find bfid for volume:location %s:%s"%(external_label, location_cookie,))

			return ticket
		except:
			ticket['status'] = (e_errors.INFO_SERVER_ERROR,
					    "failed to find bfid for volume:location %s:%s"%(external_label, location_cookie,))
			return ticket

		if len(res)>1:
			ticket["status"] = (e_errors.OK, None)
			ticket['file_list'] = []
			for db_info in res:
				bfid = db_info.get('bfid')
				self.__find_file(bfid,
						 ticket,
						 "%s:%s" %
						 (external_label, location_cookie))
		else:
			bfid = res[0].get('bfid')
			self.__find_file(bfid, ticket, "%s:%s" % (external_label, location_cookie))
		return ticket

	# find_file_by_location() -- find a file using pnfs_path
	def find_file_by_location(self, ticket):
		self.__find_file_by_location(ticket)

		self.reply_to_caller(ticket)
		return

	#This version can handle replying with a large number of file matches.
	def find_file_by_location2(self, ticket):
		self.__find_file_by_location(ticket)

		self.send_reply_with_long_answer(ticket)
		return

	# find_same_file() -- find files that match the size and crc
	def __find_same_file(self, ticket):
		bfid, record = self.extract_bfid_from_ticket(ticket)
		if not bfid:
			return #extract_bfid_from_ticket handles its own errors.

		q = "select bfid from file " \
		    "where size = %d and crc = %d and sanity_size = %d " \
		    "and sanity_crc = %d order by bfid asc;" \
		    % (record['size'], record['complete_crc'],
		       record['sanity_cookie'][0], record['sanity_cookie'][1])

		res = self.file.query_getresult(q)

		files = []
		for i in res:
			files.append(self.file[i[0]])
		ticket["files"] = files
		ticket["status"] = (e_errors.OK, None)

		return ticket

	# find_same_file() -- find files that match the size and crc
	def find_same_file(self, ticket):
		self.__find_same_file(ticket)

		self.reply_to_caller(ticket)
		return

	#This version can handle replying with a large number of file matches.
	def find_same_file2(self, ticket):
		self.__find_same_file(ticket)

		self.send_reply_with_long_answer(ticket)
		return


	def __query_db_part1(self, ticket):
		try:
			q = ticket["query"]
			# only select is allowed
			qu = string.upper(q)
			query_parts = string.split(qu)

			if query_parts[0] != "SELECT" or "INTO" in query_parts:
				#Don't use e_errors.DATABASE_ERROR, since
				# this really is a situation for the info
				# server and is not a general database error.
				msg = "only simple select statement is allowed"
				ticket["status"] = (e_errors.INFO_SERVER_ERROR,
						    msg)
				#self.reply_to_caller(ticket)
				return True
		except KeyError, detail:
			msg = "%s: key %s is missing" % (MY_NAME, detail)
			ticket["status"] = (e_errors.KEYERROR, msg)
			Trace.log(e_errors.ERROR, msg)
			#self.reply_to_caller(ticket)
			####XXX client hangs waiting for TCP reply
			return True
		return False

	def __query_db_part2(self, ticket):
		q = ticket["query"]
		result = {}
		try:
			res = self.db.query(q)
			result['result'] = res.getresult()
			result['fields'] = res.listfields()
			result['ntuples'] = res.ntuples()
			result['status'] = (e_errors.OK, None)
		except (edb.pg.ProgrammingError, edb.pg.InternalError):
			exc_type, exc_value = sys.exc_info()[:2]
			msg = 'query_db(): '+str(exc_type)+' '+str(exc_value)+' query: '+q
			result['status'] = (e_errors.DATABASE_ERROR, msg)

		return result

	def query_db(self, ticket):

		if self.__query_db_part1(ticket):
			#Errors are send back to the client.
			self.reply_to_caller(ticket)
			return

		ticket["status"] = (e_errors.OK, None)
		self.reply_to_caller(ticket)

		# get a user callback
		if not self.get_user_sockets(ticket):
			return
		callback.write_tcp_obj(self.data_socket,ticket)

		result =  self.__query_db_part2(ticket)

		# finishing up

		callback.write_tcp_obj_new(self.data_socket, result)
		self.data_socket.close()
		callback.write_tcp_obj(self.control_socket,ticket)
		self.control_socket.close()
		return

	# This is even newer and better implementation that replaces
	# query_db().  Now the network communications are done using
	# send_reply_caller_with_long_answer().
	def query_db2(self, ticket):
		#Determine if the SQL statement is allowed.
		if self.__query_db_part1(ticket):
			#Errors are send back to the client.
			self.reply_to_caller(ticket)
			return

		# start communication
		ticket["status"] = (e_errors.OK, None)
		try:
		    control_socket = self.send_reply_with_long_answer_part1(ticket)
		except (socket.error, select.error), msg:
		    Trace.log(e_errors.INFO, "query_db2(): %s" % (str(msg),))
		    return

		# get reply
		reply = self.__query_db_part2(ticket)

		# send the reply
		try:
		    self.send_reply_with_long_answer_part2(control_socket, reply)
		except (socket.error, select.error), msg:
		    Trace.log(e_errors.INFO, "query_db2(): %s" % (str(msg),))
		    return

if __name__ == '__main__':
	Trace.init(string.upper(MY_NAME))
	intf = Interface()
	csc = (intf.config_host, intf.config_port)
	infoServer = Server(csc)
	infoServer.handle_generic_commands(intf)

	while 1:
		try:
			Trace.log(e_errors.INFO, "Info Server (re)starting")
			infoServer.serve_forever()
		except edb.pg.Error, exp:	# does it work?
			infoServer.reconnect(exp)
			continue
		except edb.pg.ProgrammingError, exp:
			infoServer.reconnect(exp)
			continue
		except edb.pg.InternalError, exp:
			infoServer.reconnect(exp)
			continue
		except ValueError, exp:
			infoServer.reconnect(exp)
			continue
		except SystemExit, exit_code:
			infoServer.db.close()
			sys.exit(exit_code)
		except:
			#infoServer.serve_forever_error(infoServer.log_name)
			Trace.handle_error()
			infoServer.reconnect("paranoid")
			continue

