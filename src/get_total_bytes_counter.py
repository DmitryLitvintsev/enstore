#!/usr/bin/env python
######################################################################
# src/$RCSfile$   $Revision$
#
import string
import sys

import enstore_constants
import inventory

CDF = "cdf"
D0 = "d0"
STK = "stk"

LIBRARIES = {CDF, ["cdf"],
	     D0,  ["mezsilo", "samlto", "samm2", "sammam", "shelf-sammam"],
	     STK, ["9940", "eagle"]
	     }

def go(system, vq_file_name, vq_output_file):

    if system and system in LIBRARIES.keys():
	vq_libs = LIBRARIES[system]
    else:
	# assume all systems
	vq_libs = []
	for system in LIBRARIES.keys():
	    vq_libs = vq_libs + LIBRARIES[system]

    # read it in and pull out the libraries that we want
    vq_file = open(vq_file_name, 'r')
    total_bytes = 0.0
    for line in vq_file.readlines():
	fields = string.split(line)
	if len(fields) == 2:
	    lib = fields[0]
	    bytes = fields[1]
	else:
	    # this line has the wrong format, skip it
	    continue
	if lib in vq_libs:
	    # get rid of the newline
	    bytes = string.strip(bytes)
	    total_bytes = total_bytes + float(bytes)
    else:
	# output the file that has the number of bytes in it.
	vq_file.close()
	output_file = open(vq_output_file, 'w')
	output_file.write("%s Bytes\n"%(total_bytes,))
	output_file.close()


if __name__ == "__main__":

    # get the file we need to read
    dirs = inventory.inventory_dirs()
    vq_file_name = inventory.get_vq_format_file(dirs[0])

    # get the file we need to write
    if len(sys.argv) > 1:
	vq_output_file = sys.argv[1]

	# get the system from the args
	if len(sys.argv) > 2:
	    system = sys.argv[2]
	else:
	    system = ""

	    go(system, vq_file_name, vq_output_file)
    else:
	# this is an error we need to be given the file to write
	pass

