#!/bin/bash
# $Id$
# specify bash not sh to run on SunOS
# Fermilab internal enstore system use ups / upd product installation and setup
# utilities
# outside fermilab we do not have this environment
# this is to replace the functionality, provided by corresponding utility that uses ups/upd
# the default place os this utility is /usr/local/etc/setups.sh
# fakes setup function for products enstore, python and ftt for anything else uses ups

if [ -f /fnal/ups/etc/setups.sh ]
then
        . /fnal/ups/etc/setups.sh
elif [ -f /local/ups/etc/setups.sh ]
then
        . /local/ups/etc/setups.sh
fi

setup() {
        last=${!#}
        if [ $last = "enstore" -o $last = "python" -o $last = "ftt" ]
        then
                return 0
        else
		if [ "${UPS_DIR:-x}" != "x" ]
		then
                . `$UPS_DIR/bin/ups setup $last`
		fi
        fi
	return 0
}

# fakes ups function for products enstore, python and ftt for anything else uses ups
ups() {
	last=${!#}
	if [ $last == "enstore" ];
		then
		echo $ENSTORE_DIR
        elif [ $last = "enstore" -o $last = "python" -o $last = "ftt" ]
        then
                return
		#echo `type $last`
	else
		if [ "${UPS_DIR:-x}" != "x" ]
		then
		    $UPS_DIR/bin/ups "$@"
		fi
	fi 
}
if [ "${ENSTORE_DIR:-x}" = "x" ];
then
	# this is a very trivial way to check if enstore is set
	# the usual location of enstore is /home/enstore
	e_home=
	#e_dir=`rpm -ql enstore_sa | head -1`
	# if ENSTORE_HOME is defined execute setup-enstore in the user area
	if [ "${ENSTORE_HOME:-x}" != "x" -a -f "${ENSTORE_HOME}/site_specific/config/setup-enstore" ]; then
	    source ${ENSTORE_HOME}/site_specific/config/setup-enstore
	    return 0
	fi
	# otherwise execute a common setup-enstore from enstore area
	if [ -f ${e_home}/site_specific/config/setup-enstore ]; then
	    source ${e_home}/site_specific/config/setup-enstore
	    return 0
	else
	    echo '****'
	    echo '**** Unable to initialize the UPSII environment'
	    echo '****'
	    return 1
	fi
fi

