import botocore
import logging as log
import boto3
import requests
import json
import time
import os
from config import get_home, ReadFromFile, UnhandledError
from bootstrap import generate_bootstrap_script

port = 1111
retry_wait = 5
timeout = 720
max_retries = 720 // retry_wait

def ping_host(dns, port, retry=True):
    """
    Check Docker host health by requesting /version from docker daemon on host
    """
    try:
        log.info(f"Pinging {dns}")
        response = requests.get(f"http://{dns}:{port}/version")
        log.info(f"DockerHost {dns} is healthy!")
        return (True, None)
    except Exception as error:
        if retry:
            log.error(f"Failed to reach {dns}, retrying in {retry_wait}s")
        else:
            log.error(f"Failed to reach {dns}, with error message {error.message}")
        return (False, error)


class Commands():
    """
    Class for sdocker commands
    """
    def __init__(self, args, config):
        """
        Create ec2 client and passes args and config
        """
        commands = {
            "create-host": self.create_host,
            "terminate-current-host": self.terminate_current_host,
            "terminate-host": self.terminate_host
        }
        self.ec2_client = boto3.client("ec2", region_name=config["Region"])
        self.args = args
        self.config = config
        commands[self.args.func]()


    def create_sg(self, name, desc, source_sg, from_port, to_port):
        """
        Creates security group if not found in VPC
        """
        sg_exist = False
        log.info(f"Checking {name} security group exists")
        try:
            check_response= self.ec2_client.describe_security_groups(
                Filters=[
                    {
                        "Name": "group-name",
                        "Values": [name]
                    },
                    {
                        "Name": "vpc-id",
                        "Values": [self.config["VpcId"]]
                    }
                ]
            )
            if len(check_response['SecurityGroups']) > 0:
                sg_exist = True
                log.info(f"Found {name} security group {check_response['SecurityGroups'][0]['GroupId']}")
            else:
                log.info(f"Security group {name} not found")
        except botocore.exceptions.ClientError as error:
            if error.response["Error"]["Code"] == "InvalidGroup.NotFound":
                log.info(f"Security group {name} not found, 'ClientError' was raised")
                sg_exist = False
            else:
                UnhandledError(error)
        except Exception as error:
            UnhandledError(error)
                
        if not sg_exist:
            log.info(f"Creating {name} security group")
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
                log.info(f"Security Group id: {response['GroupId']}")
            except botocore.exceptions.ClientError as error:
                if error.response["Error"]["Code"] != "InvalidGroup.Duplicate":
                    UnhandledError(error)
            except Exception as error:
                UnhandledError(error)
            sg = response["GroupId"]
        else:
            sg = check_response['SecurityGroups'][0]["GroupId"]
        return sg


    def prepare_efs(self, sg):
        """
        Adds mount target to EFS
        """
        if sg not in self.config["MountTargetSecurityGroups"]:
            try:
                response = self.config["EFSClient"].modify_mount_target_security_groups(
                    MountTargetId=self.config["MountTargetId"],
                    SecurityGroups=[*self.config["MountTargetSecurityGroups"], sg]
                )
            except Exception as error:
                UnhandledError(error)
    
    def terminate_host(self):
        instance_id = self.args.instance_id
        try:
            response = self.ec2_client.terminate_instances(
                InstanceIds=[instance_id]
            )
        except Excpetion as error:
            UnhandledError(error)
        finally:            
            os.system(f"docker context use default")
            os.system(f'docker context rm `docker context list -q | grep "{instance_id}"`')


    def terminate_current_host(self, instance_id=None):
        """
        Terminate Docker Host command
        """
        home = get_home()
        sdocker_host_filename = f"{home}/.sdocker/sdocker-hosts.conf"
        try:
            if not instance_id:
                sdocker_host_config = ReadFromFile(sdocker_host_filename)
                instance_id = sdocker_host_config["ActiveHosts"][0]["InstanceId"]
            response = self.ec2_client.terminate_instances(
                InstanceIds=[instance_id]
            )
        except Excpetion as error:
            UnhandledError(error)
        finally:            
            os.system(f"docker context use default")
            os.system(f'docker context rm `docker context list -q | grep "{instance_id}"`')
        instance_id = sdocker_host_config["ActiveHosts"][0]["InstanceId"]
        instance_dns = sdocker_host_config["ActiveHosts"][0]["InstanceDns"]
        print(f"Successfully terminated instance {instance_id} with private DNS {instance_dns}")
        log.info(f"Successfully terminated instance {instance_id} with private DNS {instance_dns}")


    def create_host(self):
        """
        Create Docker Host command
        """
        home = get_home()
        if self.args.subnet_id:
            if self.args.subnet_id in self.config["SubnetIds"]:
                self.config["SubnetId"] = self.args.subnet_id
            else:
                message = f"InvalidSubnetId: {self.args.subnet_id} is either invalid subnet id or not part of {self.config['VpcId']}"
                log.error(message)
                raise ValueError(message)
        else:
            self.config["SubnetId"] = self.config["SubnetIds"][0]
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
        docker_image_name = "docker:dind"
        gpu_option = ""
        if "GpuInfo" in self.ec2_client.describe_instance_types(InstanceTypes=[self.args.instance_type])['InstanceTypes'][0].keys():
            # https://stackoverflow.com/a/71866959/18516713
            docker_image_name = "brandsight/dind:nvidia-docker"
            gpu_option = "--gpus all"
        bootstrap_script = generate_bootstrap_script(home, self.config['EfsIpAddress'], port, self.config['UserUid'], gpu_option, docker_image_name)
        args = {}
        args["ImageId"] = self.config["ImageId"]
        args["InstanceType"] = self.args.instance_type
        if self.config["Key"]:
            args["KeyName"] = self.config["Key"]
        args["SecurityGroupIds"] = [docker_sg, efs_sg]
        args["SubnetId"] = self.config["SubnetId"]
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
        self.config["Tags"].append({"Key": "Name", "Value": "DockerHost"})
        args["TagSpecifications"] = [{"Tags": self.config["Tags"], "ResourceType": "instance"}]
        try:
            response = self.ec2_client.run_instances(**args)
        except Exception as error:
            UnhandledError(error)
        instance_id = response['Instances'][0]['InstanceId']
        instance_dns = response['Instances'][0]['PrivateDnsName']
        log.info(f"Successfully launched instance {instance_id} with private DNS {instance_dns}")
        print(f"Successfully launched DockerHost on instance {instance_id} with private DNS {instance_dns}")
        print("Waiting on docker host to be ready")
        IsHealthy = (False, "")
        retries = 0
        while not IsHealthy[0] and retries < max_retries:
            time.sleep(retry_wait)
            IsHealthy = ping_host(instance_dns, port)
            retries += 1
        
        if not IsHealthy[0]:
            print("Failed to establish connection with docker daemon on DockerHost instance. Terminating instance")
            log.error("Failed to establish connection with docker daemon on DockerHost instance. Terminating instance")
            log.error(f"Not able to reach docker daemon on host: {IsHealthy[1]}")
            self.terminate_current_host(instance_id)
        
        assert IsHealthy[0], "Aborting."
        
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
        try:
            with open(f"{home}/.sdocker/sdocker-hosts.conf", "w") as file:
                json.dump(active_host, file)
            os.system(f"docker context create {self.args.instance_type}_{instance_id} --docker host=tcp://{instance_dns}:{port}")
            os.system(f"docker context use {self.args.instance_type}_{instance_id}")
        except Exception as error:
            UnhandledError(error)
        return instance_id, instance_dns, port