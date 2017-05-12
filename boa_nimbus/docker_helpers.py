import subprocess
import click
import base64
import boto3

amazon_linux_ecr_registry_id = "137112412989"
amazon_linux_docker_image_name = "amazonlinux"
amazon_linux_docker_image_tag = "latest"
local_lambda_packager_image_name = "boa-nimbus-packager"

def verify_docker_reachable():
    
    try:
        p = subprocess.run(
            ["docker", "ps"],
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
            check = True
        )
    except:
        try:
            click.error(p.stderr)
        except:
            pass
        
        raise click.ClickException("Unable to verify docker is installed and reachable. Is it?")

def pull_latest_amazon_linux_docker_image():
    
    click.echo("Fetching credentials for Amazon ECR.")
    
    response = boto3.client("ecr").get_authorization_token(
        registryIds = [amazon_linux_ecr_registry_id]
    )
    
    auth_token = response["authorizationData"][0]["authorizationToken"]
    proxy_endpoint = response["authorizationData"][0]["proxyEndpoint"]
    
    username, password = base64.b64decode(auth_token).decode().split(":")
    
    proxy_endpoint_server_protocol = "/".join(proxy_endpoint.split("/")[:3])
    proxy_endpoint_server = proxy_endpoint.split("/")[2]
    
    click.echo("Setting credentials in Docker.")
    
    docker_login_args = ["docker", "login", "-u", username, "-p", password, "-e", "none", proxy_endpoint_server_protocol]
    
    p = subprocess.run(
        docker_login_args,
        check = True,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE
    )
    
    click.echo("Pulling latest Amazon Linux image.")
    
    docker_image_full_name = "{}/{}:{}".format(
        proxy_endpoint_server,
        amazon_linux_docker_image_name,
        amazon_linux_docker_image_tag
    )
    
    p = subprocess.run(
        ["docker", "pull", docker_image_full_name],
        check = True,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE
    )
        
    return docker_image_full_name

def build_packager_docker_image():
    
    docker_image_full_name = pull_latest_amazon_linux_docker_image()
    
    click.echo("Building boa-nimbus packager from Amazon Linux image.")
    
    dockerfile_text = """
    FROM {}
    RUN yum -y groupinstall "Development Tools"
    RUN yum install -y python35-devel
    RUN yum install -y zlib-devel bzip2-devel openssl-devel ncurses-devel sqlite-devel readline-devel tk-devel gdbm-devel db4-devel libpcap-devel xz-devel expat-devel
    RUN curl https://www.python.org/ftp/python/3.6.1/Python-3.6.1.tar.xz -o python.tar.xz && tar xf python.tar.xz && cd Python* && ./configure --prefix=/usr/local --enable-shared LDFLAGS="-Wl,-rpath /usr/local/lib" && make && make altinstall && cd .. && rm -rf Python*
    RUN curl -s https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python get-pip.py && rm -f get-pip.py
    RUN pip install virtualenv
    #RUN yum -y update && yum -y upgrade
    RUN yum install -y python27-devel gcc
    RUN virtualenv /venv
    RUN python3.6 -m venv /venv3
    """.format(
        docker_image_full_name
    )
    
    '''
    yum_requirements_path = os.path.join(deploy_dir, "lambda", "yum-dependencies.txt")
    
    if os.path.exists(yum_requirements_path):
        yum_requirements_list = open(yum_requirements_path).read().split("\n")
        yum_requirements_list = list(x.strip() for x in yum_requirements_list)
        
        dockerfile_text += """
        RUN yum install -y {}
        """.format(" ".join(yum_requirements_list))
    '''
    
    p = subprocess.run(
        ["docker", "build", "-t", local_lambda_packager_image_name, "-"],
        input = dockerfile_text.encode("utf-8"),
        check = True,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE
    )
    