#!/bin/bash
# to setup fishtest on Ubuntu, simply run: 
# sudo bash setup-fishtest.sh

# upgrade the system
apt-get -y update
apt-get -y upgrade

# install other packages
apt-get install -y build-essential unzip zsh
apt-get install -y python python-dev python-pip python-numpy python-scipy python-zmq
apt-get install -y apache2
apt-get install -y mongodb-server

pip install pyramid
pip install waitress
pip install boto
pip install requests

# create user fishtest
useradd -m fishtest
adduser fishtest sudo

# download and setup fishtest
sudo -i -u fishtest wget https://github.com/ppigazzini/fishtest/archive/master.zip
sudo -i -u fishtest unzip master.zip
sudo -i -u fishtest mv fishtest-master fishtest
cd /home/fishtest/fishtest/fishtest
python setup.py develop
cat /dev/null > /home/fishtest/fishtest.secret
chown fishtest:fishtest /home/fishtest/fishtest.secret

# execute script
sudo -i -u fishtest /bin/bash /home/fishtest/fishtest/fishtest/start.sh

