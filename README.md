# Sdocker - Docker integration for SageMaker Studio
Helper application to setup Docker Host on SageMaker Studio
## Prerequsites
- SageMaker Studio setup in `VPCOnly` mode, and VPC has DNS hostnames and DNS resolution options enabled.
- Execution role for Studio with the below permissions:
  ```
  sagemaker:DescribeDomain
  sagemaker:DescribeUserProfile
  sagemaker:ListTags
  elasticfilesystem:DescribeMountTargets
  elasticfilesystem:DescribeMountTargetSecurityGroups
  elasticfilesystem:ModifyMountTargetSecurityGroups
  ec2:RunInstances
  ec2:TerminateInstances
  ec2:DescribeInstances
  ec2:DescribeImages
  ec2:DescribeSecurityGroups
  ec2:DescribeNetworkInterfaces
  ec2:DescribeNetworkInterfaceAttribute
  ec2:CreateSecurityGroup
  ec2:AuthorizeSecurityGroupIngress
  ```
- Docker
- Docker compose (required for `local mode`)
- Python 3
- Boto3
## Setup
Setup is staightforward, you clone this repo and then run `./setup.sh`:
```
$ git clone https://github.com/samdwar1976/sdocker.git
$ cd sdocker
$ ./setup.sh
```
`setup.sh` will do the following:
- Create `~/.sdocker` directory
- Setup softlink for `sdocker` to make it possible to run it from anywhere from command line
- Install `docker` and `docker-compose` (requires `wget` to be installed on system)
- Create `~/temp` directory used in `local mode`
- Create `config.yaml` to change temporay directory to `~/temp`
- Install branch `remote_docker_host` from SageMaker Python SDK which introduces Remote Docker Host capability (see [PR 2864](https://github.com/aws/sagemaker-python-sdk/pull/2864)). This is a temporary workaround until branch is merged with main.
## How SDocker works
`sdocker` provision an EC2 instance that is use as a remote docker host that is running docker daemon. `sdocker` does the following:
- Setup networking and security groups between the instance and SageMaker Studio Apps and EFS
- Provision EC2 instance
- Mount SageMaker Studio EFS on EC2 instance
- Run a `docker:dind` image as Host docker daemon and open map port 1111 to allow access to docker daemon.
- Create docker context on the client to connect to docker host

## Configuration
`sdocker` can be configured to choose a different *AMI*, include EC2 key pair and customize root EBS volume size. Configuration file location is  `~/.sdocker/sdocker.conf`.
Make sure your *AMI* has docker daemon installed and running by default. It is only tested on `Amazon linux 2` instances. We recommend using *AWS Deep Learning Base AMI (Amazon Linux 2).*. You can use below ASW CLI command to find latest AWS Deep learning AMI ID:

```
$ aws ec2 describe-images --region <region> --owners amazon --filters "Name=name,Values=AWS Deep Learning Base AMI (Amazon Linux 2) Version ????"
```
For more information on how to create an EC2 key pair check this [link](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html#having-ec2-create-your-key-pair)

An example of a valid configuration `~/.sdocker/sdocker.conf` file is shown below:
```
{
    "ImageId": "ami-052783664d99ae241",
    "Key": "docker-key",
    "EBSVOlumeSize": 500
}
```
## Usage
```
$ sdocker [COMMANDS][OPTIONS]

Where [COMMANDS] can be:
    create-host: Create security groups `DockerHost` and `EFSDockerHost`, then provision EC2 Docker Host. Takes one required [OPTIONS]:
        --instance-type <instance-type>
    
    terminate-current-host: Terminates current host, this will only work if creation was successful. Takes no [OPTIONS]
```
## Examples
Below example creates a docker host using `c5.xlarge` instance type:
```
$ sdocker create-host --instance-type c5.xlarge
```
Once the host is provisioned and `Healthy` it should show below message:
```
Successfully launched DockerHost on instance i-xxxxxxxxxxxxxxxxx with private DNS ip-xxx-xxx-xxx-xxx.ec2.internal
Waiting on docker host to be ready
Docker host is ready!
ip-xxx-xxx-xxx-xxx.ec2.internal
Successfully created context "ip-xxx-xxx-xxx-xxx.ec2.internal"
ip-xxx-xxx-xxx-xxx.ec2.internall
Current context is now "ip-xxx-xxx-xxx-xxx.ec2.internal"
```
Then you can use normal docker commands or use SageMaker Python SDK 'local mode'
Only when the Host was successfully created and turned `Healthy`, you can use below command to terminate the EC2 instance:
```
$ sdocker terminate-current-host
```
Otherwise, you will need to terminate the instance manually.
## Troubleshooting
- Consult `~/.sdocker/sdocker.log` for `sdocker` logs.
- To troubleshoot issues related to host instance (eg. `Unhealthy` host), check AWS EC2 console logs for `bootstrap` script logs.

## Notes
- `sdocker` does not terminate or stop EC2 instance after it created, always make sure you have terminated unused instances when you are done. You can use `terminate-current-host` command to terminate the current host.
- Networking is setup between *Docker Host*, *SageMaker Studio* and *EFS* using two *Security Groups* (listed below), it is recommended to deleted these when you create new *SageMaker Studio Domain* so `sdocker` can create new ones that are setup correctly:
  - `DockerHost`
  - `EFSDockerHost`
If you need to delete `EFSDockerHost` without deleting EFS or Studio domain, you can use the below AWS CLI to update mount target with new list of security groups:
```
$ aws efs modify-mount-target-security-groups --mount-target-id <mount target id> --security-groups <list of security groups>
```
Then you can go ahead and delete `EFSDockerHost`.
- Currenlty, `sdocker` is setup EC2 with `400GB` root EBS volume by default which will be mainly used to store docker images.
