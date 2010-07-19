#!/bin/sh
###############################################################################
#
# $Id$
#
###############################################################################

#set -u  # force better programming and ability to use check for not set
if [ "${1:-}" = "-x" ] ; then set -xv; shift; fi
if [ "${1:-}" = "-q" ] ; then export quiet=1; shift; else quiet=0; fi

if [ "`whoami`" != 'root' ]
then
    echo You need to run this script as user "root"
    exit 1
fi

echo " 
You need to run this script only on the enstore configuration server host."

read -p "Are you on this host?[y/N]: " REPLY
if [ "$REPLY" = "y" -o "$REPLY" = "Y" ] 
then
    ENSTORE_CONFIG_HOST=`uname -n`
else
    exit 1
fi
rpm -q enstore > /dev/null
if [ $? -eq 0 ]; 
then
    ENSTORE_DIR=`rpm -ql enstore | head -1`
else
    ENSTORE_DIR=`rpm -ql enstore_sa | head -1`
fi
PYTHON_DIR=`rpm -ql Python-enstore | head -1`
FTT_DIR=`rpm -ql ftt | head -1`

PATH=/usr/sbin:$PATH

echo "Copying $ENSTORE_DIR/external_distr/setup-enstore to $ENSTORE_DIR/site_specific/config"
if [ ! -d $ENSTORE_DIR/site_specific/config ]
then
    mkdir -p $ENSTORE_DIR/site_specific/config
fi

rm -rf /tmp/enstore_header
echo "ENSTORE_DIR=$ENSTORE_DIR" > /tmp/enstore_header
echo "PYTHON_DIR=$PYTHON_DIR" >> /tmp/enstore_header
echo "FTT_DIR=$FTT_DIR" >> /tmp/enstore_header

rm -rf $ENSTORE_DIR/site_specific/config/setup-enstore
cat /tmp/enstore_header $ENSTORE_DIR/external_distr/setup-enstore > $ENSTORE_DIR/site_specific/config/setup-enstore

echo "Finishing configuration of $ENSTORE_DIR/site_specific/config/setup-enstore"
echo "export ENSTORE_CONFIG_HOST=${ENSTORE_CONFIG_HOST}"
echo "export ENSTORE_CONFIG_HOST=${ENSTORE_CONFIG_HOST}" >> $ENSTORE_DIR/site_specific/config/setup-enstore

read -p "Enter ENSTORE configuration server port [7500]: " REPLY
if [ -z "$REPLY" ]
then 
	REPLY=7500
fi
echo "export ENSTORE_CONFIG_PORT=${REPLY}"
echo "export ENSTORE_CONFIG_PORT=${REPLY}" >> $ENSTORE_DIR/site_specific/config/setup-enstore

read -p "Enter ENSTORE configuration file location [${ENSTORE_DIR}/site_specific/config/enstore_system.conf]: " REPLY
if [ -z "$REPLY" ]
then
    REPLY=${ENSTORE_DIR}/site_specific/config/enstore_system.conf
fi
echo "export ENSTORE_CONFIG_FILE=${REPLY}"
echo "export ENSTORE_CONFIG_FILE=${REPLY}" >> $ENSTORE_DIR/site_specific/config/setup-enstore

read -p "Enter ENSTORE mail address: " REPLY

echo "export ENSTORE_MAIL=${REPLY}"
echo "export ENSTORE_MAIL=${REPLY}" >> $ENSTORE_DIR/site_specific/config/setup-enstore

#read -p "Enter ENSTORE web site directory: " REPLY
#echo "export ENSTORE_WWW_DIR=${REPLY}"
#echo "export ENSTORE_WWW_DIR=${REPLY}" >> $ENSTORE_DIR/config/setup-enstore
#if [ ! -d ${REPLY} ]
#then
#    echo "creating ${REPLY}"
#    mkdir -p ${REPLY}
#fi

read -p "Enter ENSTORE farmlets dir [/usr/local/etc/farmlets]: " REPLY
if [ -z "$REPLY" ]
then
        REPLY="/usr/local/etc/farmlets"
fi
echo "export FARMLETS_DIR=${REPLY}"
echo "export FARMLETS_DIR=${REPLY}" >> $ENSTORE_DIR/site_specific/config/setup-enstore
if [ ! -d ${REPLY} ]
then
    echo "creating ${REPLY}"
    mkdir -p ${REPLY}
fi



echo "
Enstore install finished.
Please check $ENSTORE_DIR/site_specific/config/setup-enstore.
In case you are going to use ssh for product distribution, updates and maintenance you need to add the following entries
to $ENSTORE_DIR/site_specific/config/setup-enstore:
ENSSH=<path to ssh binary>
ENSCP=<path scp bynary>

Now you can proceed with enstore configuration.

For the system recommendations and layout please read ${ENSTORE_DIR}/etc/configuration_recommendations.
To create a system configuration file you can use ${ENSTORE_DIR}/etc/enstore_configuration_template
or refer to one of real enstore configuration files, such as ${ENSTORE_DIR}/etc/stk.conf
After the enstore configuration file has has been created you can proceed with ${ENSTORE_DIR}/external_distr/make_farmlets.sh"
 
