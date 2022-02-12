import os
import json
import boto3
import logging

def get_home():
    home = os.getenv("HOME")
    if home=="" or home==None:
        home = "/home/sagemaker"
    return home

class ReadConfig():
        
    def __init__(self):
        
        logging.info("Fetching SageMaker Studio configuration")
        def ReadFromFile(filename):
            try:
                with open(filename, "r") as meta_file:
                    data = json.load(meta_file)
                return data
            except FileNotFoundError:
                raise FileNotFoundError(f"File {filename} not found")
            except:
                logger.error(f"An error occured while trying to access {filename}")
                raise OSError
        self.config={}
        home = get_home()
        internal_metadata = "/opt/.sagemakerinternal/internal-metadata.json"
        resource_metadata = "/opt/ml/metadata/resource-metadata.json"
        config_file = f"{home}/.sdocker/sdocker.conf"
        internal_meta = ReadFromFile(internal_metadata)
        resource_meta = ReadFromFile(resource_metadata)
        config_data = ReadFromFile(config_file)
        self.config["UserProfile"] = resource_meta["UserProfileName"]
        self.config["DomainId"] = resource_meta["DomainId"]
        if internal_meta["AppNetworkAccessType"]=="VpcOnly":
            self.config["VPCOnly"] = True
        else:
            self.config["VPCOnly"] = False
        self.config["Region"] = os.environ.get("REGION_NAME")
        
        assert self.config["VPCOnly"], "SageMaker Studio Domain must be in \"VPCOnly mode\"."
        
        sm_client = boto3.client("sagemaker", region_name=self.config["Region"])
        domain_reponse = sm_client.describe_domain(DomainId=self.config["DomainId"])
        UserProfile_reponse = sm_client.describe_user_profile(DomainId=self.config["DomainId"], UserProfileName=self.config["UserProfile"])
        self.config["SubnetIds"] = domain_reponse["SubnetIds"]
        self.config["VpcId"] = domain_reponse["VpcId"]
        self.config["EfsId"] = domain_reponse["HomeEfsFileSystemId"]
        self.config["UserUid"] = UserProfile_reponse["HomeEfsFileSystemUid"]
        if "UserSettings"  in UserProfile_reponse.keys() and "SecurityGroups" in UserProfile_reponse["UserSettings"].keys():
            self.config["SecurityGroups"] = UserProfile_reponse["UserSettings"]["SecurityGroups"] 
        else:
            self.config["SecurityGroups"] = domain_reponse["DefaultUserSettings"]['SecurityGroups"]
        if "UserSettings" in UserProfile_reponse.keys() and "ExecutionRole" in UserProfile_reponse["UserSettings"]:
            self.config["ExecutionRole"] = UserProfile_reponse["UserSettings"]["ExecutionRole"]
        else:
            self.config["ExecutionRole"] = domain_reponse["DefaultUserSettings"]["ExecutionRole"]
        self.config["UserProfileArn"] = UserProfile_reponse["UserProfileArn"]
        # TODO add pagination support
        Tags_reponse = sm_client.list_tags(ResourceArn=self.config["UserProfileArn"])
        self.config["Tags"] = Tags_reponse["Tags"]
        self.config["ImageId"] = config_data["ImageId"]
        self.config["Key"] = config_data["Key"]
        efs_client = boto3.client("efs", region_name=self.config["Region"])
        Efs_response = efs_client.describe_mount_targets(FileSystemId=self.config["EfsId"])
        self.config["EfsIpAddress"] = Efs_response["MountTargets"][0]["IpAddress"]
        self.config["NetworkInterfaceId"] = Efs_response["MountTargets"][0]["NetworkInterfaceId"]
        logging.debug(f"Resource: {self.config}")
        
