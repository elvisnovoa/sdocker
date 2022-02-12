#!/bin/bash

set -ex

mkdir -p ~/.sdocker
if [[ ! -f ~/.sdocker/sdocker.conf ]]
then
    cp src/sdocker/config/sdocker.conf ~/.sdocker/sdocker.conf
fi

if [[ `command -v /usr/bin/sdocker` == "" ]]
then
    sudo ln -s $PWD/src/sdocker/sdocker /usr/bin/sdocker
fi

if [[ `command -v docker` == "" ]]
then
    echo "docker not installed, please refer on how to install docker CLI (https://docs.docker.com/get-docker/)."
    exit 1
elif [[ `command -v docker-compose` == "" ]]
then
    echo "Installing docker-compose ..."
    python3 -m pip install docker-compose
fi

mkdir -p ~/.sagemaker
mkdir -p ~/temp
cp src/sdocker/config/config.yaml ~/.sagemaker/config.yaml

python3 -m pip install git+https://github.com/samdwar1976/sagemaker-python-sdk.git@remote_docker_host
