import botocore
import logging
import boto3
import requests
import json
import time
import os
from config import get_home, ReadFromFile

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
        
    def create_sg(self, name, desc, source_sg, from_port, to_port):
        
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
            try:
                response = self.ec2_client.create_security_group(
                    Description=desc,
                    GroupName=name,
                    VpcId=self.config["VpcId"]
                )
                rule_response = self.ec2_client.authorize_security_group_ingress(
                    GroupId=response["GroupId"],
                    IpPermissions=[
                        {
                            "FromPort": from_port,
                            "IpProtocol": 'tcp',
                            "ToPort": to_port,
                            "UserIdGroupPairs": [
                                {
                                    "Description": desc,
                                    "GroupId": response["GroupId"] if source_sg=="self" else source_sg,
                                },
                            ],
                        },
                    ]
                )
                logging.info(f"Security Group id: {response['GroupId']}")
            except botocore.exceptions.ClientError as error:
                if error.response["Error"]["Code"] != "InvalidGroup.Duplicate":
                    raise errorß
            sg = response["GroupId"]
        else:
            sg = check_response['SecurityGroups'][0]["GroupId"]
        return sg
    
    def prepare_efs(self, sg):
        if sg not in self.config["MountTargetSecurityGroups"]:
            response = self.config["EFSClient"].modify_mount_target_security_groups(
                MountTargetId=self.config["MountTargetId"],
                SecurityGroups=[*self.config["MountTargetSecurityGroups"], sg]
            )
    
    def terminate_current_host(self):
        home = get_home()
        sdocker_host_filename = f"{home}/.sdocker/sdocker-hosts.conf"
        sdocker_host_config = ReadFromFile(sdocker_host_filename)
        response = self.ec2_client.terminate_instances(
            InstanceIds=[sdocker_host_config["ActiveHosts"][0]["InstanceId"]]
        )
        instance_id = sdocker_host_config["ActiveHosts"][0]["InstanceId"]
        instance_dns = sdocker_host_config["ActiveHosts"][0]["InstanceDns"]
        print(f"Successfully terminated instance {instance_id} with private DNS {instance_dns}")
        logging.info(f"Successfully terminated instance {instance_id} with private DNS {instance_dns}")

    def create_host(self):
        
        home = get_home()
        docker_sg = self.create_sg(
            "DockerHost",
            "Docker host security group",
            self.config["SecurityGroups"][0],
            0,
            65535
        )
        efs_sg = self.create_sg(
            "EFSDockerHost",
            "EFS security group used with Docker host",
            "self",
            2049,
            2049
        )
        self.prepare_efs(efs_sg)
        bootstrap_script = f"""#!/bin/bash
        set -ex
        exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
        
            sudo mkdir -p {home}
            sudo mount -t nfs \
                -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
                {self.config['EfsIpAddress']}:/{self.config['UserUid']} \
                {home}

            sudo -u ec2-user docker run -d -p {port}:2375 -p 8080:8080 -v {home}:{home} --privileged --name dockerd-server -e DOCKER_TLS_CERTDIR="" docker:dind
        """
        args = {}
        args["ImageId"] = self.config["ImageId"]
        args["InstanceType"] = self.args.instance_type
        if self.config["Key"]:
            args["KeyName"] = self.config["Key"]
        args["SecurityGroupIds"] = [docker_sg, efs_sg]
        args["SubnetId"] = self.config["SubnetIds"][0]
        args["MinCount"] = 1
        args["MaxCount"] = 1
        args["UserData"] = bootstrap_script
        args["BlockDeviceMappings"] = [
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {
                        "VolumeSize": self.config["EBSVolumeSize"]
                    }
                }
            ]
        
        response = self.ec2_client.run_instances(**args)
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
        
        if not IsHealthy:
            print("Failed to establish connection with docker daemon on DockerHost instance. Terminating instance")
            logging.info("Failed to establish connection with docker daemon on DockerHost instance. Terminating instance")
            self.terminate_current_host()
        
        assert IsHealthy, "Aborting."
        
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
        commands = {
            "create-host": self.create_host,
            "terminate-current-host": self.terminate_current_host
        }
        commands[self.args.func]()