#!/bin/bash

set -ex

mkdir -p ~/.sdocker

if [[ `command -v /usr/bin/sdocker` == "" ]]
then
    if [[ $EUID != 0 ]]
    then
        sudo ln -s $PWD/src/sdocker/sdocker /usr/bin/sdocker
        sudo chmod +x $PWD/src/sdocker/sdocker
    else
        ln -s $PWD/src/sdocker/sdocker /usr/bin/sdocker
        chmod +x $PWD/src/sdocker/sdocker
    fi
fi

if [[ `command -v docker` == "" ]]
then
    wget https://get.docker.com/ -O installer.sh
    chmod +x installer.sh
    ./installer.sh
    if [[ `command -v docker` == "" ]]
    then
        echo "docker not installed, please refer on how to install docker CLI (https://docs.docker.com/get-docker/)."
        exit 1
    fi
elif [[ `command -v docker-compose` == "" ]]
then
    echo "Installing docker-compose ..."
    python3 -m pip install docker-compose
fi

mkdir -p ~/.sagemaker
echo -e "local:\n    container_root: $HOME/temp" > ~/.sagemaker/config.yaml
mkdir -p ~/temp

python3 -m pip install "sagemaker>=2.80.0"
