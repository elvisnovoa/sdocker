#!/bin/bash

set -ex

mkdir -p ~/.sdocker
cp src/sdocker/config/sdocker.conf ~/.sdocker/sdocker.conf

if [[ `command -v /usr/bin/sdocker` == "" ]]
then
    sudo ln -s $PWD/src/sdocker/sdocker /usr/bin/sdocker
fi

if [[ `command -v docker` == "" ]]
then
    echo "docker not installed, please refer on how to install docker CLI (https://docs.docker.com/get-docker/)."
elif [[ `command -v docker-compose` == "" ]]
then
    echo "Installing docker-compose ..."
    python3 -m pip install docker-compose
fi
