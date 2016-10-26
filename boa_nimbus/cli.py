#!/usr/bin/env python

from __future__ import print_function
import os
import sys
import shutil
import argparse
import time
import hashlib
import subprocess
import json
import boto3
import botocore

exclude_files = [".DS_Store"]

deploy_dir = os.path.join(os.getcwd(), "cloudformation-deploy")
build_dir = os.path.join(os.getcwd(), "build", "cloudformation-deploy")
self_dir = os.path.dirname(os.path.realpath(__file__))

parser = argparse.ArgumentParser()
parser.add_argument("--stack-name", default="project-bucket1", help="Name for the CloudFormation stack.")
parser.add_argument("--clean", action="store_true", help="Remove all build artifacts first.")

def verify_deploy_dir_exists():
    if not os.path.exists(deploy_dir):
        # TODO: Point to a URL explaining how to lay out the files for this utility.
        raise Exception("No directory found at {}.".format(deploy_dir))

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

cloudformation_client = boto3.client("cloudformation")

def deploy_or_update_stack(stack_name):
    print("Deploying bucket.")
    
    last_status = None
    stack_id = None
    this_stack = None
    
    template_body = open(os.path.join(self_dir, "bucket-stack-template.yaml")).read()
    
    try:
        response = cloudformation_client.create_stack(
            StackName = stack_name,
            TemplateBody = template_body,
            Capabilities = [ "CAPABILITY_IAM" ]
        )
        stack_id = response["StackId"]
        last_status = "CREATE_IN_PROGRESS"
        
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] != "AlreadyExistsException":
            raise
        
        try:
            response = cloudformation_client.update_stack(
                StackName = stack_name,
                TemplateBody = template_body,
                Capabilities = [ "CAPABILITY_IAM" ]
            )
        except botocore.exceptions.ClientError as e:
            if not (e.response["Error"]["Code"] == "ValidationError" and "No updates are to be performed." in e.response["Error"]["Message"]):
                raise
            
        response = cloudformation_client.describe_stacks(
            StackName = stack_name
        )
        
        this_stack = response["Stacks"][0]
        stack_id = this_stack["StackId"]
        last_status = this_stack["StackStatus"]
    
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
    
        print(" > Stack status: {}".format(last_status))
    
        if last_status not in expected_wait_statuses:
            break
    
        time.sleep(10)

    if last_status not in [ "CREATE_COMPLETE", "UPDATE_COMPLETE" ]:
        raise Exception("Stack reached unexpected status: {}".format(last_status))
    
    for each_output_pair in this_stack.get("Outputs", []):
        if each_output_pair["OutputKey"] == "S3Bucket":
            s3_bucket_name = each_output_pair["OutputValue"]
            break
    
    return s3_bucket_name

def build_and_upload_lambda_packages(s3_bucket_name):
    
    lambda_src_dir = os.path.join(deploy_dir, "lambda")
    
    if not os.path.exists(lambda_src_dir):
        print("No AWS Lambda sources to upload found in {}.".format(s3_src_dir))
        return
    
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
                if file_sha256_checksum_base64(zip_output_path) == each_function_previous_build_metadata["zip"]:
                    print("{} already built.".format(each_function_name))
                    continue
        
        print("Building Lambda function: {}".format(each_function_name))
        
        function_build_dir = os.path.join(build_dir, "lambda", each_function_name)
    
        if os.path.exists(function_build_dir):
            shutil.rmtree(function_build_dir)
    
        shutil.copytree(each_function_source_dir, function_build_dir)
        
        pip_requirements_path = os.path.join(function_build_dir, "requirements.txt")
    
        if os.path.exists(pip_requirements_path):
            
            print("Installing dependencies.")
            p = subprocess.Popen(
                ["pip", "install", "-r", pip_requirements_path, "-t", function_build_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        
            exit_code = p.wait()
            p_stdout, p_stderr = p.communicate()
        
            if exit_code != 0:
                print("pip invocation failed.", file=sys.stderr)
                print(p_stderr, file=sys.stderr)
                sys.exit(1)
    
        build_zip_path = os.path.join(build_dir, "lambda", each_function_name)
        if os.path.exists("{}.zip".format(build_zip_path)):
            os.unlink("{}.zip".format(build_zip_path))
    
        shutil.make_archive(build_zip_path, "zip", function_build_dir)
        
        new_build_metadata = {
            "source": source_dir_hash,
            "zip": file_sha256_checksum_base64(zip_output_path)
        }
        
        open(each_function_build_metadata_file_path, "w").write(json.dumps(new_build_metadata, indent=4))
        
        shutil.rmtree(function_build_dir)
    
        print("Successfully built Lambda function: {}.".format(each_function_name))
    

s3_client = boto3.client("s3")

def upload_plain_s3_objects(s3_bucket_name):
    
    s3_src_dir = os.path.join(deploy_dir, "s3")
    
    if not os.path.exists(s3_src_dir):
        print("No static S3 objects to upload found in {}.".format(s3_src_dir))
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

def upload_s3_object_if_unchanged(s3_bucket_name, s3_key, file_path):
    
    should_upload_file = False
    local_file_hash = file_sha256_checksum_base64(file_path)
    
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
        print("Uploading {}...".format(s3_key))
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(s3_bucket_name)
        
        with open(file_path, 'rb') as data:
            bucket.upload_fileobj(
                data,
                s3_key,
                ExtraArgs = {
                    "Metadata": {
                        "sha256base64": local_file_hash
                    }
                }
            )
        

def main():
    args = parser.parse_args()
    
    if args.clean and os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    
    verify_deploy_dir_exists()
    
    if not os.path.exists(build_dir):
        mkdir_p(build_dir)
    
    s3_bucket_name = deploy_or_update_stack(args.stack_name)
    
    build_and_upload_lambda_packages(s3_bucket_name)
    
    upload_plain_s3_objects(s3_bucket_name)

if __name__ == "__main__":
    main()
    