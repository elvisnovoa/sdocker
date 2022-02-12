# Sdocker - Docker integration for SageMaker Studio
Helper application to setup Docker Host on SageMaker Studio
## Prerequsites
- Studio Kernel with docker installed
- SageMaker Studio setup in `VPCOnly` mode
- Execution role for Studio with the below permissions:
  ```
  sagemaker:DescribeDomain
  sagemaker:DescribeUserProfile
  sagemaker:ListTags
  elasticfilesystem:DescribeMountTargets
  elasticfilesystem:DescribeMountTargetSecurityGroups
  elasticfilesystem:ModifyMountTargetSecurityGroups
  ec2:RunInstances
  ec2:DescribeInstances
  ec2:DescribeSecurityGroups
  ec2:DescribeNetworkInterfaces
  ec2:DescribeNetworkInterfaceAttribute
  ec2:CreateSecurityGroup
  ec2:AuthoriseSecurityGroupIngress
  ```
## Setup
Setup is very staightforward, you clone this repo and then run `./setup.sh`:
```
$ git clone https://github.com/samdwar1976/sdocker.git
$ cd sdocker
$ ./setup.sh
```
The setup includes:
- Copying configuration file template `sdocker.conf` to `~/.sdocker`
- Checking if docker exits.
- Checking if docker-compose exists, and install it if not.
- Configure SageMaker Python SDK `local mode` to work with `sdocker` by changing storage location from `/tmp` to `~/temp` and fixing dependancy on `localhost` to make it pull host from default docker context. The fix is a temporary workaround until this [PR](https://github.com/aws/sagemaker-python-sdk/pull/2864) is merged with `SageMaker Python SDK`.

Finally, configure `~/.sdocker/sdocker.conf` with an *AMI* of your choice and EC2 Key Pair. Make sure your *AMI* has docker daemon installed and running by default. We recommend using *AWS Deep Learning Base AMI (Amazon Linux 2).*. You can use below ASW CLI command to find latest AWS Deep learning AMI ID:

```
$ aws ec2 describe-images --region <region> --owners amazon --filters "Name=name,Values=AWS Deep Learning Base AMI (Amazon Linux 2) Version ????"
```
For more information on how to create an EC2 key pair check this [link](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html#having-ec2-create-your-key-pair)

Your configuration file should like below:
```
{
    "ImageId": "ami-052783664d99ae241",
    "Key": "docker-key"
}
```


## Usage
```
$ sdocker create-host --instance-type <instance-type>
```
## Notes
- `sdocker` does not delete or stop EC2 instance after it created, always make sure you have terminated unused instances when you are done.
- Networking is setup between *Docker Host*, *SageMaker Studio* and *EFS* using two *Security Groups* (listed below), it is recommended to deleted these when you create new *SageMaker Studio Domain* so `sdocker` can create new ones that are setup correctly:
  - `DockerHost`
  - `EFSDockerHost`
- Currenlty, `sdocker` is setup EC2 with `400GB` root EBS volume which will be mainly used to store docker images.

