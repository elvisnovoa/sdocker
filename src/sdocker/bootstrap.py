def generate_bootstrap_script(home, efs_ip_address, port, user_uid, gpu_option, docker_image_name):
    bootstrap_script = f"""#!/bin/bash
    set -ex
    exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
    
    echo "Mounting EFS to /root"
    
    sudo mkdir -p /root
    sudo mount -t nfs \
    -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
    {efs_ip_address}:/{user_uid} \
    /root
    
    sudo mkdir -p /home/sagemaker-user
    sudo mount -t nfs \
    -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
    {efs_ip_address}:/{user_uid} \
    /home/sagemaker-user
    
    if ( ! [[ "{home}" == "/home/sagemaker-user" ]] || [[ "{home}" == "/root" ]] )
    then
        sudo mkdir -p {home}
        sudo mount -t nfs \
        -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2 \
        {efs_ip_address}:/{user_uid} \
        {home}
        
        sudo -u ec2-user docker run -d \
        -p {port}:2375 \
        -p 8080:8080 {gpu_option} \
        -v /root:/root \
        -v /home/sagemaker-user:/home/sagemaker-user \
        -v {home}:{home} \
        --privileged \
        --name dockerd-server \
        -e DOCKER_TLS_CERTDIR="" {docker_image_name}
    else
        sudo -u ec2-user docker run -d \
        -p {port}:2375 \
        -p 8080:8080 {gpu_option} \
        -v /root:/root \
        -v /home/sagemaker-user:/home/sagemaker-user \
        --privileged \
        --name dockerd-server \
        -e DOCKER_TLS_CERTDIR="" {docker_image_name}
    fi
    """
    return bootstrap_script