### Local Mode Training and Inference in SageMaker Studio

![](https://cdn-images-1.medium.com/max/800/0*6aoqaAfvP_h6IU_B)

Photo by [Mehmet Ali Peker](https://unsplash.com/@mrpeker?utm_source=medium&utm_medium=referral) on [Unsplash](https://unsplash.com?utm_source=medium&utm_medium=referral)

Often the case Data Scientists and Machine Learning engineers use Jupyter Notebooks to run and develop ML pipelines. When using cloud services and in particular AWS and SageMaker, it makes sense to onboard SageMaker Studio which is marketed as a one stop ML development IDE that runs on the cloud.

ML development cycle in cloud services involve heavy dependency on _Docker_ images and containers. Preprocessing, training, inference jobs and even Jupyter Notebooks that runs on SageMaker Studio, they all require docker containers to run. And although AWS offer a wide selection of prebuilt containers, engineers will often need to interact with these containers especially in the development stage, whether it is building and testing a container or troubleshooting part of ML pipeline. It makes much more sense to run containers _‘locally’_ before deploying them on the cloud.

Currently, Docker functionality is missing from SageMaker Studio, since its Jupyter Kernels are themselves docker containers running in non-privileged mode, this prevents users from having access to docker daemon which is required to run docker commands. Thus using _‘Local Mode’_ functionality of _SageMaker Python SDK_ is also not natively supported from within SageMaker Studio.

In this article, we are going to explain how we can use a docker host that runs on EC2 instance and connect to it from SageMaker Studio to provide full docker functionality, including SageMaker Python SDK _‘Local mode’_. All code in this article is also available in my repository. To follow this article, you should already have SageMaker Studio setup with _‘VPCOnly’_ mode.

---

### Setting up Docker Host:

In this section, we are going to start by quickly explaining basic architecture of SageMaker Studio, which will help understand the different steps required in setting up our docker host. We then go over how we setup a docker host.

SageMaker Studio runs a  _JupyterServer_ app which connects to one or more _KernelGateway_ apps. Both of these apps are docker containers and run on seperate instances. Multiple _KernelGateway_ apps can run on same instance but all apps including _JupyterServer_ app share same Elastic FileSystem (_EFS_). In fact, all users within a SageMaker Studio domain share same EFS, and each user only have access to their own folder in that EFS. 

![SageMaker Studio high-level Architecture](https://cdn-images-1.medium.com/max/800/1*_kJjLZ79o8GWpqnKab_Kmg.png)

SageMaker Studio components (from https://docs.aws.amazon.com/sagemaker/latest/dg/images/studio/studio-components.png)

To setup docker host, we take advantage of SageMaker Studio’s VPC connectivity and provision an EC2 instance in same subnet where SageMaker Studio is connected to. This will help us mount EFS used by Studio Domain on our EC2 and enabling us to build images and access files, without having to send these files to the host. We then going to run a seperate docker daemon on our EC2 instance that would act as our docker host. There are number of ways to achieve that, but here we are going to use Docker-in-Docker image `docker:dind`. Then we will setup up a docker context in SageMaker Studio to connect to a remote docker daemon running on our host EC2 instance.

There are many other small details that we need to do (like setting up networking for example) to complete this setup. To save time and effort, I went ahead a created a python application `sdocker` that can be cloned from a repository on GitHub to simplify this setup.

`sdocker` does the following:

* Installs `docker` and `docker-compose` .
* Configure SageMaker Python SDK to work with remote docker host.
* Create a softlink to be able to run `sdocker` from anywhere in the Studio App.
* Create security groups and associate them with Host instance.
* Create EFS mount target associated with EC2 Host.
* Provision EC2 instance as a Host
* Mount EFS on Host
* Run docker-in-docker container on Host exposing port `1111` for docker daemon and port `8080` for local endpoints.

To be able to use `sdocker`, our SageMaker Studio execution role needs to have the below permissions:
```
"Effect": "Allow",  
 "Action": [  
    "sagemaker:DescribeDomain",  
    "sagemaker:DescribeUserProfile",  
    "sagemaker:ListTags",  
    "elasticfilesystem:DescribeMountTargets",  
    "elasticfilesystem:DescribeMountTargetSecurityGroups",  
    "elasticfilesystem:ModifyMountTargetSecurityGroups",  
    "ec2:RunInstances",  
    "ec2:DescribeImages",  
    "ec2:TerminateInstances",  
    "ec2:DescribeInstances",  
    "ec2:DescribeSecurityGroups",  
    "ec2:DescribeNetworkInterfaces",  
    "ec2:DescribeNetworkInterfaceAttribute",  
    "ec2:CreateSecurityGroup",  
    "ec2:AuthorizeSecurityGroupIngress"  
],  
"Resource": "*"
```
---

### Using Local Mode in SageMaker Studio

To demonstrate how to use _‘Local Mode’_ and docker host in SageMaker Studio, we can this run [example](https://github.com/samdwar1976/sdocker/blob/main/example/sagemaker-studio-local-mode.ipynb) . It goes through setting up `sdocker` , fixing `Python3 (Data Science)` kernel dependancies required for local mode, and run a local training and inference example.

We will need to clone `sdocker` repository first using the below command (or using git widget on Studio):
```
$ git clone https://github.com/samdwar1976/sdocker.git
```
And open Jupyter notebook located in `sdocker/example/sagemaker-studio-local-mode.ipynb` , choose `Python3 (Data Science)` kernel with `ml.t3.medium` instance type.

![](https://cdn-images-1.medium.com/max/800/1*e4U_yin_vVy5MFDrh5nc2g.png)

Once we run the cells under **Initial setup** and restart the kernel, we are ready to create a docker host. The output should look like below image. When the host is ready, take note of host DNS, as we are going to use it later to `ping` our local endpoint.

![](https://cdn-images-1.medium.com/max/800/1*eniUgM-L8e321VJcCYUivA.png)

Then go ahead and execute the next two cells, which will start local training (see below image). 

![](https://cdn-images-1.medium.com/max/800/1*Rc8r2vIZeKoSP9RSWlXFww.png)

![](https://cdn-images-1.medium.com/max/800/1*GcSdDLLiqiI1EhlM89fyEA.png)

After that, we are going to create a local endpoint (see below image)

![](https://cdn-images-1.medium.com/max/800/1*E20Z-HomEL4-IyxIe-AD2w.png)

![](https://cdn-images-1.medium.com/max/800/1*pOXDRZAiR6VJT_7KfKb87A.png)

And send a couple of invocations (see below image)

![](https://cdn-images-1.medium.com/max/800/1*jdJdbGSVqkM07uLsJOLkXQ.png)

We can also open terminal from our kernel and send a `ping` request to our local endpoint using below command:
```
$ curl -v ip-xxx-xxx-xxx-xxx.ec2.internal:8080/ping

*   Trying xxx.xxx.xxx.xxx...  
* TCP_NODELAY set  
* Expire in 200 ms for 4 (transfer 0x55735b42ff50)  
* Connected to ip-xxx-xxx-xxx-xxx.ec2.internal (xxx.xxx.xxx.xxx) port 8080 (#0)  
> GET /ping HTTP/1.1  
> Host: xxx-xxx-xxx-xxx.ec2.internal:8080  
> User-Agent: curl/7.64.0  
> Accept: */*  
>   
< HTTP/1.1 200 OK  
< Server: nginx/1.14.0 (Ubuntu)  
< Date: Tue, 15 Feb 2022 09:34:21 GMT  
< Content-Type: application/json  
< Content-Length: 0  
< Connection: keep-alive  
<   
* Connection #0 to host xxx-xxx-xxx-xxx.ec2.internal left intact
```
We can also execute normal docker commands
```
$ docker info  
$ docker ps
```
Finally, we can go ahead and run last remaining cells to delete local endpoint. The final cell will issue an `sdocker` command to terminate Docker Host instance to avoid any unnecessary cost.

**NOTE: Please make sure to double check the EC2 instance is terminated after you finish running this notebook to avoid any extra charges.**

You can find more information about `sdocker` in its repository linked [here](https://github.com/samdwar1976/sdocker#readme)
