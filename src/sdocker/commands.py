import botocore
import logging
import boto3
import requests
import json
import time
import os
from config import get_home

port = 1111
retry_wait = 5
timeout = 720
max_retries = 720 // retry_wait

def ping_host(dns, port, retry=True):
    try:
        logging.info(f"Pinging {dns}")
        response = requests.get(f"http://{dns}:{port}/version")
        logging.info(f"DockerHost {dns} is healthy!")
        return True
    except:
        if retry:
            logging.error(f"Failed to reach {dns}, retrying in {retry_wait}s")
        else:
            logging.error(f"Failed to reach {dns}")
        return False

class Commands():
    def __init__(self, args, config):
        self.ec2_client = boto3.client("ec2", region_name=config["Region"])
        self.args = args
        self.config = config
        
    def create_sg(self, name, desc, port):
        
        sg_exist = False
        logging.info(f"Checking {name} security group exists")
        try:
            check_response= self.ec2_client.describe_security_groups(
                GroupNames=[name]
            )
            sg_exist = True
            logging.info(f"Found {name} security group {check_response['SecurityGroups'][0]['GroupId']}")
        except botocore.exceptions.ClientError as error:
            if error.response["Error"]["Code"] == "InvalidGroup.NotFound":
                sg_exist = False
            else:
                raise error
                
        if not sg_exist:
            logging.info(f"Creating {name} security group")
            response = self.ec2_client.create_security_group(
                Description=desc,
                GroupName=name,
                VpcId=self.config["VpcId"]
            )
            rule_response = self.ec2_client.authorize_security_group_ingress(
                GroupId=response["GroupId"],
                port=port,
                protocol="tcp",
                source_group=self.config["SecurityGroups"][0]
            )
            logging.info(f"Security Group id: {response['GroupId']}")
            sg = response["GroupId"]
        else:
            sg = check_response['SecurityGroups'][0]["GroupId"]
        return sg
    
    def create_efs_sg(self):
        
        sg_exist = False
        logging.info("Checking EFSDockerHost security group exists")
        try:
            check_response= self.ec2_client.describe_security_groups(
                GroupNames=["EFSDockerHost"]
            )
            sg_exist = True
            logging.info(f"Found EFSDockerHost security group {check_response['SecurityGroups'][0]['GroupId']}")
        except botocore.exceptions.ClientError as error:
            if error.response["Error"]["Code"] == "InvalidGroup.NotFound":
                sg_exist = False
            else:
                raise error
        if not sg_exist:
            logging.info("Creating EFSDockerHost security group")
            response = self.ec2_client.create_security_group(
                Description="EFS security group used with Docker host",
                GroupName="DockerHost",
                VpcId=self.config["VpcId"]
            )
            rule_response = self.ec2_client.authorize_security_group_ingress(
                GroupId=response["GroupId"],
                port=port,
                protocol="tcp",
                source_group=self.config["SecurityGroups"][0]
            )
            logging.info(f"Security Group id: {response['GroupId']}")
            sg = response["GroupId"]
        else:
            sg = check_response['SecurityGroups'][0]["GroupId"]
        return sg
    
    def prepare_efs(self, sg):
        eni_response = self.ec2_client.describe_network_interfaces(describe_network_interfaces=[self.config["NetworkInterfaceId"]])
        sg_groups = eni_response["NetworkInterfaces"][0]["Groups"]
        sg_exist = false
        groups = []
        for sg_group in sg_groups:
            groups.append(sg_group["GroupId"])
            if sg_group["GroupId"] == sg:
                sg_exist = True
        if not sg_exist:
            groups.append(sg)
            eni_update_response = self.ec2_client.modify_network_interface_attribute(
                NetworkInterfaceId=self.config["NetworkInterfaceId"],
                Groups=groups
            )

    def create_host(self):
        
        home = get_home()
        docker_sg = self.create_sg("DockerHost", "Docker host security group", "0-65535")
        efs_sg = self.create_sg("EFSDockerHost", "EFS security group used with Docker host", "2049")
        self.prepare_efs(efs_sg)
        bootstrap_script = f"""#!/bin/bash
        set -ex               
        
        sudo su - ec2-user
        sudo mkdir -p {home}
        sudo chown 1000:1000 {home}
        sudo mount -t nfs \
            -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
            {self.config['EfsIpAddress']}:/{self.config['UserUid']} \
            {home}
            
        docker run -d -p {port}:2375 -p 8080:8080 -v {home}:{home} --privileged --name dockerd-server -e DOCKER_TLS_CERTDIR="" docker:dind
        """
        
        response = self.ec2_client.run_instances(
            ImageId=self.config["ImageId"],
            InstanceType=self.args.instance_type,
            KeyName=self.config["Key"],
            SecurityGroupIds=[docker_sg, efs_sg],
            SubnetId=self.config["SubnetIds"][0],
            MinCount=1,
            MaxCount=1,
            UserData=bootstrap_script,
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {
                        "VolumeSize": 400
                    }
                }
            ]
        )
        instance_id = response['Instances'][0]['InstanceId']
        instance_dns = response['Instances'][0]['PrivateDnsName']
        logging.info(f"Successfully launched instance {instance_id} with private DNS {instance_dns}")
        print(f"Successfully launched DockerHost on instance {instance_id} with private DNS {instance_dns}")
        print("Waiting on docker host to be ready")
        IsHealthy = False
        retries = 0
        while not IsHealthy and retries < max_retries:
            time.sleep(retry_wait)
            IsHealthy = ping_host(instance_dns, port)
            retries += 1
            
        assert IsHealthy, "Failed to establish connection with docker daemon on DockerHost instance. Please make sure to terminate instance manually. Aborting."
        
        print("Docker host is ready!")
        active_host = {
            "ActiveHosts": [
                {
                    "InstanceId": instance_id,
                    "InstanceDns": instance_dns,
                    "Port": port,
                    "InstanceType": self.args.instance_type
                }
            ]
        }
        home = get_home()
        with open(f"{home}/.sdocker/sdocker-hosts.conf", "w") as file:
            json.dump(active_host, file)
        os.system(f"docker context create {instance_dns} --docker host=tcp://{instance_dns}:{port}")
        os.system(f"docker context use {instance_dns}")
        return instance_id, instance_dns, port
    
    def run(self):
        commands = {"create-host": self.create_host}
        commands[self.args.func]()