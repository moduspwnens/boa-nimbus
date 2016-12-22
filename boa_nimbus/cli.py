#!/usr/bin/env python

from __future__ import print_function
import os
import sys
import shutil
import time
import hashlib
import subprocess
import json
import re
import base64
import click
import boto3
import botocore
import yaml

try:
    from urllib import quote_plus
except:
    from urllib.parse import quote_plus

assume_default_aws_region = "us-east-1"
amazon_linux_ecr_registry_id = "137112412989"
amazon_linux_docker_image_name = "amazonlinux"
amazon_linux_docker_image_tag = "latest"
exclude_files = [".DS_Store"]

deploy_dir = os.path.join(os.getcwd(), "boa-nimbus")
build_dir = os.path.join(os.getcwd(), "build", "boa-nimbus")
pip_cache_dir = os.path.join(build_dir, "pip-cache")
self_dir = os.path.dirname(os.path.realpath(__file__))
mimes_lookup_string = open(os.path.join(self_dir, "mime.types.txt")).read()
mimes_lookup_cache = {}

built_zip_hash_map = {}
local_lambda_packager_image_name = "boa-nimbus-packager"

def verify_deploy_dir_exists():
    if not os.path.exists(deploy_dir):
        raise click.ClickException((
            "No directory found at {}." "\n"
            "For instructions how to set up the correct directory structure, see the documentation here:" "\n"
            " * https://github.com/moduspwnens/boa-nimbus#how-to-use" "\n"
            "Please set up the correct directory structure and try again."
        ).format(deploy_dir))

def verify_aws_credentials_and_configuration():
    
    # Verify credentials are set.
    try:
        boto3.client('sts').get_caller_identity()
    except botocore.exceptions.NoCredentialsError:
        raise click.ClickException((
            "Unable to locate AWS credentials." "\n"
            "This utility uses the same credential finding process as the AWS Command Line Interface (CLI), which allows multiple options for configuration." "\n"
            "See the documentation here:" "\n"
            "  * http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html" "\n"
            "Please ensure your credentials are configured in one of the ways described there and try again."
        ))
    
    # Verify region is set.
    try:
        boto3.client('cloudformation')
    except botocore.exceptions.NoRegionError:
        click.echo('No AWS region specified. Assuming {}.'.format(assume_default_aws_region))
        os.environ['AWS_DEFAULT_REGION'] = assume_default_aws_region
    
def verify_docker_reachable():
    
    try:
        p = subprocess.Popen(
            ["docker", "ps"],
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE
        )
    except:
        raise click.ClickException("Unable to verify docker is installed and reachable. Is it?")
    
    exit_code = p.wait()
    
    p_stdout, p_stderr = p.communicate()
    
    if exit_code != 0:
        click.echo(p_stderr)
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
    
    p = subprocess.Popen(
        docker_login_args
    )
    
    if p.wait() != 0:
        raise click.ClickException("Docker did not accept the auth token.")
    
    click.echo("Pulling latest Amazon Linux image.")
    
    docker_image_full_name = "{}/{}:{}".format(
        proxy_endpoint_server,
        amazon_linux_docker_image_name,
        amazon_linux_docker_image_tag
    )
    
    p = subprocess.Popen(
        ["docker", "pull", docker_image_full_name]
    )
    
    if p.wait() != 0:
        raise click.ClickException("Docker was not able to pull the image.")
    
    click.echo("Building boa-nimbus packager from Amazon Linux image.")
    
    p = subprocess.Popen(
        ["docker", "build", "-t", local_lambda_packager_image_name, "-"],
        stdin = subprocess.PIPE
    )
    
    dockerfile_text = """
    FROM {}
    
    RUN curl -s https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python get-pip.py && rm -f get-pip.py
    RUN pip install virtualenv
    #RUN yum -y update && yum -y upgrade ; yum clean all
    RUN yum -y groupinstall "Development Tools" ; yum clean all
    RUN yum install -y python27-devel gcc ; yum clean all
    RUN virtualenv /venv
    """.format(
        docker_image_full_name
    )
    
    yum_requirements_path = os.path.join(deploy_dir, "lambda", "yum-dependencies.txt")
    
    if os.path.exists(yum_requirements_path):
        yum_requirements_list = open(yum_requirements_path).read().split("\n")
        yum_requirements_list = list(x.strip() for x in yum_requirements_list)
        
        dockerfile_text += """
        RUN yum install -y {} ; yum clean all
        """.format(" ".join(yum_requirements_list))
    
    p.communicate(
        input = dockerfile_text
    )
    
    if p.wait() != 0:
        raise click.ClickException("Unable to build {} Docker image from Amazon Linux image.".format(local_lambda_packager_image_name))

# http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python/600612#600612
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

#http://stackoverflow.com/questions/3431825/generating-an-md5-checksum-of-a-file/3431838#3431838
def file_sha256_checksum_base64(fname):
    hash_sha256 = hashlib.sha256()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    
    return hash_sha256.digest().encode('base64').strip()

#http://code.activestate.com/recipes/576973-getting-the-sha-1-or-md5-hash-of-a-directory/
def directory_sha1_hash(directory):
    import hashlib, os
    SHAhash = hashlib.sha1()
    if not os.path.exists (directory):
        return -1
    
    for root, dirs, files in os.walk(directory):
        for names in files:
            filepath = os.path.join(root,names)
            try:
                f1 = open(filepath, 'rb')
            except:
                # You can't open the file for some reason
                f1.close()
                continue

            while 1:
                # Read file in as little chunks
                buf = f1.read(4096)
                if not buf : break
                SHAhash.update(hashlib.sha1(buf).hexdigest())
            f1.close()
    
    return SHAhash.hexdigest()

def deploy_or_update_stack(stack_name, bucket_name = None):
    
    cloudformation_client = boto3.client("cloudformation")
    
    last_status = None
    stack_id = None
    this_stack = None
    
    template_body = open(os.path.join(self_dir, "bucket-stack-template.yaml")).read()
    
    stack_already_exists = False
    
    try:
        response = cloudformation_client.describe_stacks(
            StackName = stack_name
        )
        stack_already_exists = True
        
        this_stack = response["Stacks"][0]
        stack_id = this_stack["StackId"]
        last_status = this_stack["StackStatus"]
        
        current_parameter_list = this_stack.get("Parameters", [])
        
    except botocore.exceptions.ClientError as e:
        if "does not exist" not in e.response['Error']['Message']:
            raise
    
    parameters_list = []
    
    if bucket_name is not None:
        parameters_list.append({
            "ParameterKey": "BucketName",
            "ParameterValue": bucket_name
        })
    else:
        parameters_list = current_parameter_list
    
    if not stack_already_exists:
        click.echo("Deploying stack.")
        
        response = cloudformation_client.create_stack(
            StackName = stack_name,
            TemplateBody = template_body,
            Capabilities = [ "CAPABILITY_IAM" ],
            Parameters = parameters_list
        )
        stack_id = response["StackId"]
        last_status = "CREATE_IN_PROGRESS"
        
    else:
        click.echo("Updating stack.")
        try:
            response = cloudformation_client.update_stack(
                StackName = stack_name,
                TemplateBody = template_body,
                Capabilities = [ "CAPABILITY_IAM" ],
                Parameters = parameters_list
            )
        except botocore.exceptions.ClientError as e:
            if not (e.response["Error"]["Code"] == "ValidationError" and "No updates are to be performed." in e.response["Error"]["Message"]):
                raise
            click.echo("No updates necessary.")
    
    s3_bucket_name = None
    
    expected_wait_statuses = [
        "CREATE_IN_PROGRESS",
        "UPDATE_IN_PROGRESS",
        "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS"
    ]
    
    while last_status in expected_wait_statuses:
        response = cloudformation_client.describe_stacks(
            StackName = stack_id
        )
    
        this_stack = response["Stacks"][0]
    
        last_status = this_stack["StackStatus"]
    
        click.echo(" > Stack status: {}".format(last_status))
    
        if last_status not in expected_wait_statuses:
            break
    
        time.sleep(10)

    if last_status not in [ "CREATE_COMPLETE", "UPDATE_COMPLETE" ]:
        raise click.ClickException("Stack reached unexpected status: {}".format(last_status))
    
    for each_output_pair in this_stack.get("Outputs", []):
        if each_output_pair["OutputKey"] == "S3Bucket":
            s3_bucket_name = each_output_pair["OutputValue"]
            break
    
    return s3_bucket_name

def build_lambda_packages(s3_bucket_name = None, use_docker = True):
    
    lambda_src_dir = os.path.join(deploy_dir, "lambda")
    
    if not os.path.exists(lambda_src_dir):
        click.echo("No AWS Lambda sources to upload found in {}.".format(s3_src_dir))
        return
    
    lambda_zips_to_upload = []
    
    for (each_path, each_dir_list, each_file_list) in os.walk(lambda_src_dir):
        if each_path == lambda_src_dir:
            continue
        
        each_function_name = each_path[len(os.path.dirname(each_path))+1:]
        each_function_source_dir = each_path
        
        each_function_build_metadata_file_path = os.path.join(build_dir, "lambda", "{}.json".format(each_function_name))
        
        each_function_previous_build_metadata = {
            "source": "",
            "zip": ""
        }
        
        if os.path.exists(each_function_build_metadata_file_path):
            try:
                each_function_previous_build_metadata = json.loads(open(each_function_build_metadata_file_path).read())
            except:
                pass
        
        source_dir_hash = directory_sha1_hash(each_function_source_dir)
        
        zip_output_path = os.path.join(build_dir, "lambda", "{}.zip".format(each_function_name))
        
        if os.path.exists(zip_output_path):
            if each_function_previous_build_metadata["source"] == source_dir_hash:
                existing_zip_hash = file_sha256_checksum_base64(zip_output_path)
                if existing_zip_hash == each_function_previous_build_metadata["zip"]:
                    click.echo("{} already built.".format(each_function_name))
                    
                    s3_object_key = "lambda/{}.zip".format(each_function_name)
                    
                    built_zip_hash_map[s3_object_key] = existing_zip_hash
                    
                    lambda_zips_to_upload.append((
                        s3_bucket_name,
                        s3_object_key,
                        zip_output_path
                    ))
                    
                    continue
        
        click.echo("Building Lambda function: {}".format(each_function_name))
        
        function_build_dir = os.path.join(build_dir, "lambda", each_function_name)
    
        if os.path.exists(function_build_dir):
            shutil.rmtree(function_build_dir)
    
        shutil.copytree(each_function_source_dir, function_build_dir)
        
        pip_requirements_path = os.path.join(function_build_dir, "requirements.txt")
        
        package_config_path = os.path.join(function_build_dir, "package.yml")
        package_config_settings = {}
        
        if os.path.exists(package_config_path):
            package_config_settings = yaml.load(open(package_config_path).read())
    
        if os.path.exists(pip_requirements_path):
            
            click.echo("Installing dependencies.")
            
            if use_docker:
                
                if not os.path.exists(pip_cache_dir):
                    mkdir_p(pip_cache_dir)
                
                docker_build_args = ["docker", "run"]
                
                docker_build_args.extend(["-v", "{}:/requirements.txt".format(pip_requirements_path)])
                docker_build_args.extend(["-v", "{}:/build".format(function_build_dir)])
                docker_build_args.extend(["-v", "{}:/boa-nimbus".format(deploy_dir)])
                docker_build_args.extend(["-v", "{}:/root/.cache".format(pip_cache_dir)])
                
                docker_build_args.extend(["-it", local_lambda_packager_image_name, "/bin/bash", "-c"])
                
                run_commands = [
                    "source /venv/bin/activate",
                    "pip install -r /requirements.txt"
                ]
                
                for each_dir in ["lib", "lib64"]:
                    run_commands.append("cp -R /venv/{}/python2.7/site-packages/* /build".format(each_dir))
                
                post_install_commands = package_config_settings.get("PostInstallCommands", [])
                
                run_commands.extend(post_install_commands)
                
                docker_build_args.append(" && ".join(run_commands))
                
                p = subprocess.Popen(
                    docker_build_args,
                    #stdout=subprocess.PIPE,
                    #stderr=subprocess.PIPE
                )
                
                exit_code = p.wait()
                #p_stdout, p_stderr = p.communicate()
                
                if exit_code != 0:
                    #click.echo(p_stderr, err=True)
                    raise click.ClickException("Docker-based installation of dependencies failed.")
            else:
                try:
                    p = subprocess.Popen(
                        ["pip", "install", "-r", pip_requirements_path, "-t", function_build_dir],
                        stdout = subprocess.PIPE,
                        stderr = subprocess.PIPE
                    )
                except OSError as e:
                    if e.errno == 2:
                        raise click.ClickException("Pip not found. Is it installed?")
                    else:
                        raise
        
                exit_code = p.wait()
                p_stdout, p_stderr = p.communicate()
        
                if exit_code != 0:
                    click.echo(p_stderr, err=True)
                    raise click.ClickException("Pip returned an error when trying to install dependencies.")
    
        build_zip_path = os.path.join(build_dir, "lambda", each_function_name)
        if os.path.exists("{}.zip".format(build_zip_path)):
            os.unlink("{}.zip".format(build_zip_path))
    
        shutil.make_archive(build_zip_path, "zip", function_build_dir)
        
        new_zip_hash = file_sha256_checksum_base64(zip_output_path)
        
        new_build_metadata = {
            "source": source_dir_hash,
            "zip": new_zip_hash
        }
        
        open(each_function_build_metadata_file_path, "w").write(json.dumps(new_build_metadata, indent=4))
        
        shutil.rmtree(function_build_dir)
    
        click.echo("Successfully built Lambda function: {}.".format(each_function_name))
        
        s3_object_key = "lambda/{}.zip".format(each_function_name)
        
        lambda_zips_to_upload.append((
            s3_bucket_name,
            s3_object_key,
            zip_output_path
        ))
        
        built_zip_hash_map[s3_object_key] = new_zip_hash
        
    if s3_bucket_name is not None:
        for each_lambda_zip_tuple in lambda_zips_to_upload:
            upload_s3_object_if_unchanged(*each_lambda_zip_tuple)

def upload_plain_s3_objects(s3_bucket_name):
    
    s3_src_dir = os.path.join(deploy_dir, "s3")
    
    if not os.path.exists(s3_src_dir):
        click.echo("No static S3 objects to upload found in {}.".format(s3_src_dir))
        return
    
    for (each_path, each_dir_list, each_file_list) in os.walk(s3_src_dir):
        
        for each_file in each_file_list:
            if each_file in exclude_files:
                continue
            each_file_path = os.path.join(each_path, each_file)
            each_file_relative_path = each_file_path[len(s3_src_dir)+1:]
            
            upload_s3_object_if_unchanged(
                s3_bucket_name,
                each_file_relative_path,
                each_file_path
            )

def lookup_mime_type_for_extension(extension):
    if extension not in mimes_lookup_cache:
        m = re.search(r"^([^#][^\s]*).*\s{}($|\s)".format(extension), mimes_lookup_string, re.MULTILINE)
        mime_value = None
        if m is not None:
            mime_value = m.group(1)
        
        mimes_lookup_cache[extension] = mime_value
    
    return mimes_lookup_cache[extension]

def upload_s3_object_if_unchanged(s3_bucket_name, s3_key, file_path):
    
    should_upload_file = False
    local_file_hash = file_sha256_checksum_base64(file_path)
    
    s3_client = boto3.client("s3")
    
    try:
        response = s3_client.head_object(
            Bucket = s3_bucket_name,
            Key = s3_key
        )
        uploaded_file_hash = response.get("Metadata", {}).get("sha256base64", "")
        
        if uploaded_file_hash != local_file_hash:
            should_upload_file = True
            
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            should_upload_file = True
        else:
            raise
    
    if should_upload_file:
        click.echo("Uploading {}...".format(s3_key))
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(s3_bucket_name)
        
        extra_args_dict = {
            "Metadata": {
                "sha256base64": local_file_hash
            }
        }
        
        try:
            object_mime_type = lookup_mime_type_for_extension(file_path.split(".")[-1])
            if object_mime_type is not None:
                extra_args_dict["ContentType"] = object_mime_type
        except:
            pass
        
        with open(file_path, 'rb') as data:
            bucket.upload_fileobj(
                data,
                s3_key,
                ExtraArgs = extra_args_dict
            )

def clean_build_artifacts(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    

@click.version_option(version=open(os.path.join(self_dir, 'version.txt')).read())

@click.group()
@click.option('--clean', is_flag=True, callback=clean_build_artifacts, expose_value=False, is_eager=True)
@click.option('--verbose', is_flag=True, default=False)
@click.option('--region', help='AWS region to use.')
@click.option('--profile', help='AWS CLI profile to use.')
@click.pass_context
def cli(ctx, verbose, region, profile):
    
    if region is not None:
        os.environ['AWS_DEFAULT_REGION'] = region
    
    if profile is not None:
        os.environ['AWS_DEFAULT_PROFILE'] = profile
    
    ctx.obj = {
        'VERBOSE': verbose
    }

@click.command()
@click.option('--clean', is_flag=True, callback=clean_build_artifacts, expose_value=False, is_eager=True)
@click.option('--use-docker/--no-use-docker', default=True)
@click.pass_context
def build(ctx, use_docker):
    
    if use_docker:
        verify_docker_reachable()
    
        pull_latest_amazon_linux_docker_image()
    
    build_lambda_packages(
        s3_bucket_name = None,
        use_docker = use_docker
    )
    

cli.add_command(build)

@click.command()
@click.option('--stack-name', help='Name of CloudFormation stack.')
@click.option('--project-stack-name', help='For updates: Name of main project\'s CloudFormation stack.')
@click.option('--bucket-name', help='The name of the bucket for the source stack.', default=None)
@click.option('--stack-name-parameter-key', default='S3SourceName', help='For updates: Name of parameter in the main project\'s template that specifies the stack deployed by this CLI.')
@click.option('--clean', is_flag=True, callback=clean_build_artifacts, expose_value=False, is_eager=True)
@click.option('--use-docker/--no-use-docker', default=True)
@click.pass_context
def deploy(ctx, stack_name, project_stack_name, bucket_name, stack_name_parameter_key, use_docker):
    
    if stack_name is None and project_stack_name is None:
        raise click.ClickException('Missing option \"--stack-name\"')
    
    verify_aws_credentials_and_configuration()
    
    if use_docker:
        verify_docker_reachable()
    
        pull_latest_amazon_linux_docker_image()
    
    cloudformation_client = boto3.client('cloudformation')
    
    project_stack = None
    
    if stack_name is None:
        # Determine stack_name from project_stack_name.
        response = cloudformation_client.describe_stacks(
            StackName = project_stack_name
        )
        
        project_stack = response['Stacks'][0]
        
        for each_parameter_set in project_stack.get('Parameters', []):
            if each_parameter_set['ParameterKey'] == stack_name_parameter_key:
                stack_name = each_parameter_set['ParameterValue']
                break
        
        if stack_name is None:
            raise click.ClickException('Unable to find expected parameter ({}) in stack: {}.'.format(
                stack_name_parameter_key,
                project_stack_name
            ))
    
    
    verify_deploy_dir_exists()
    
    if not os.path.exists(build_dir):
        mkdir_p(build_dir)
    
    s3_bucket_name = deploy_or_update_stack(stack_name, bucket_name)
    
    build_lambda_packages(
        s3_bucket_name = s3_bucket_name,
        use_docker = use_docker
    )
    
    upload_plain_s3_objects(s3_bucket_name)
    
    if project_stack_name is not None:
        click.echo('Updating Lambda functions in project stack: {}.'.format(project_stack_name))
        
        lambda_client = boto3.client('lambda')
        
        response = cloudformation_client.get_template(
            StackName = project_stack['StackId']
        )
        template_string = response['TemplateBody']
        
        
        template = None
        try:
            template = json.loads(template_string)
        except:
            try:
                template = yaml.load(template_string)
            except:
                raise click.ClickException('Unable to parse CloudFormation template of {}.'.format(project_stack_name))
        
        paginator = cloudformation_client.get_paginator('list_stack_resources')
        response_iterator = paginator.paginate(
            StackName = project_stack['StackId']
        )
        
        lambda_function_logical_physical_map = {}
        
        for each_response in response_iterator:
            for each_summary in each_response.get('StackResourceSummaries', []):
                if each_summary['ResourceType'] == 'AWS::Lambda::Function':
                    lambda_function_logical_physical_map[each_summary['LogicalResourceId']] = each_summary['PhysicalResourceId']
        
        for each_lambda_logical_id in lambda_function_logical_physical_map.keys():
            each_template_resource = template['Resources'][each_lambda_logical_id]
            each_code_resource = each_template_resource['Properties']['Code']
            
            if 'S3Bucket' not in each_code_resource:
                # This is an inline Lambda function unrelated to this CLI's resources.
                continue
            
            '''
            if stack_name_parameter_key not in json.dumps(each_code_resource['S3Bucket']):
                # This probably points to another unrelated bucket.
                continue
            '''
            
            source_s3_key = each_code_resource['S3Key']
            each_lambda_function_name = lambda_function_logical_physical_map[each_lambda_logical_id]
            
            
            
            response = lambda_client.get_function(
                FunctionName = each_lambda_function_name
            )
            
            existing_code_hash = response['Configuration']['CodeSha256']
            
            latest_code_hash = built_zip_hash_map[source_s3_key]
            
            update_necessary = (existing_code_hash != latest_code_hash)
            
            if update_necessary:
                click.echo('Updating code of {} ({}).'.format(
                    each_lambda_logical_id,
                    each_lambda_function_name
                ))
            
                lambda_client.update_function_code(
                    FunctionName = each_lambda_function_name,
                    S3Bucket = s3_bucket_name,
                    S3Key = source_s3_key
                )
            else:
                click.echo('Code already at latest for {} ({}).'.format(
                    each_lambda_logical_id,
                    each_lambda_function_name
                ))
    

cli.add_command(deploy)

@click.command()
@click.option('--stack-name', help='Name of CloudFormation stack.', required=True)
@click.pass_context
def destroy(ctx, stack_name):
    
    verify_aws_credentials_and_configuration()
    
    cloudformation_client = boto3.client("cloudformation")
    
    try:
        response = cloudformation_client.describe_stacks(
            StackName = stack_name
        )
    except botocore.exceptions.ClientError as e:
        if "does not exist" not in e.response['Error']['Message']:
            raise
        raise click.UsageError("No running stack found named \"{}\".".format(stack_name))
    
    stack_id = response["Stacks"][0]["StackId"]
    
    click.echo("Deleting stack.")
    
    cloudformation_client.delete_stack(
        StackName = stack_id
    )
    
    last_status = "DELETE_IN_PROGRESS"
    
    while last_status == "DELETE_IN_PROGRESS":
        time.sleep(10)
        
        response = cloudformation_client.describe_stacks(
            StackName = stack_id
        )
        
        last_status = response["Stacks"][0]["StackStatus"]
        
        click.echo(" > Stack status: {}".format(last_status))
    
    if last_status != "DELETE_COMPLETE":
        
        stack_region = stack_id.split(":")[3]
        
        events_page_link = "https://console.aws.amazon.com/cloudformation/home?region={}#/stacks?stackId={}&tab=events&filter=active".format(
            quote_plus(stack_region),
            quote_plus(stack_id)
        )
        
        raise click.ClickException((
            "Stack deletion failed. Entered unexpected state ({})." "\n"
            "View stack events here:" "\n"
            " * {}".format(last_status, events_page_link)
        ))
    
    click.echo("Stack deleted successfully.")

cli.add_command(destroy)

if __name__ == "__main__":
    main()
    