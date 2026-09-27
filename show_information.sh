#!/usr/bin/env bash
# Show how to get into your Local Lab: the web address, the SSH command, the
# username and the current password.  Run it any time:
#
#   /opt/hackrange-labs/show_information.sh
#
# (It may ask for your Ubuntu password, because the lab password is kept where
# only an administrator can read it.)
#
# Author: Tim Rice
if [ ! -x /usr/local/sbin/hackrange-access ]; then
    echo "The Local Lab is not installed yet.  See the README for the install command."
    exit 1
fi
exec sudo /usr/local/sbin/hackrange-access info
