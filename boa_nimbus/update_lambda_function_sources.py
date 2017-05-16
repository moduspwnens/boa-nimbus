import os
import json
import threading
import click
import boto3
from botocore.exceptions import ClientError
import yaml

lambda_client = boto3.client("lambda")

class UpdateLambdaFunctionSourcesDeployStepAction(object):
    
    def __init__(self, full_config, step_config):
        self.bucket_name_prefix = step_config.get("BucketNamePrefix", "")
        self.stack_name = step_config["StackName"]
        self.template_path = step_config["TemplatePath"]
        self.lambda_package_directory = step_config["LambdaPackageRelativeDirectory"]
    
    def run(self):
        
        response = boto3.client("sts").get_caller_identity()
        
        bucket_name = self.bucket_name_prefix + response["Account"]
        
        cf_resource_iterator = boto3.client("cloudformation").get_paginator("list_stack_resources").paginate(
            StackName = self.stack_name
        )
        
        logical_physical_resource_map = {}
        
        for each_response in cf_resource_iterator:
            resource_list = each_response.get("StackResourceSummaries", [])
            
            for each_resource in resource_list:
                logical_physical_resource_map[each_resource["LogicalResourceId"]] = each_resource["PhysicalResourceId"]
        
        cf_template = yaml.load(open(self.template_path, "r"))
        
        resources_map = cf_template.get("Resources", {})
        
        thread_list = []
        
        for each_resource_key, each_resource_dict in resources_map.items():
            if each_resource_dict.get("Type") != "AWS::Lambda::Function":
                continue
            
            physical_resource_id = logical_physical_resource_map.get(each_resource_key)
            
            if physical_resource_id is None:
                click.echo("Unable to find {} in existing stack's resources.".format(
                    each_resource_key
                ), err = True)
                continue
            
            each_function_code_dict = each_resource_dict.get("Properties", {}).get("Code", {})
            
            each_function_s3_key = each_function_code_dict.get("S3Key")
            
            if each_function_s3_key is None:
                continue
            
            t = threading.Thread(
                target = self.update_function_code_if_necessary, 
                kwargs = {
                    "logical_resource_id": each_resource_key,
                    "physical_resource_id": physical_resource_id,
                    "bucket_name": bucket_name,
                    "s3_key": each_function_s3_key
                }
            )
            
            thread_list.append(t)
        
        for each_thread in thread_list:
            each_thread.start()
        
        for each_thread in thread_list:
            each_thread.join()
            
        
        #click.echo("Boafile: {}".format(cf_template))
    
    def update_function_code_if_necessary(self, logical_resource_id, physical_resource_id, bucket_name, s3_key):
        
        try:
            response = boto3.client("s3").head_object(
                Bucket = bucket_name,
                Key = s3_key
            )
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                click.echo("No file found at s3://{}/{}.".format(
                    bucket_name,
                    s3_key
                ), err = True)
                return
            else:
                raise
        
        s3_object_sha256_base64 = response.get("Metadata", {}).get("boa-nimbus-sha256-base64", "")
        
        response = lambda_client.get_function(
            FunctionName = physical_resource_id
        )
        
        function_sha256_base64 = response["Configuration"]["CodeSha256"]
        
        if s3_object_sha256_base64 == function_sha256_base64:
            click.echo("Skipping {}. No changes needed.".format(
                logical_resource_id
            ))
            return
        
        click.echo("Updating code of {}.".format(each_resource_key))
        
        lambda_client.update_function_code(
            FunctionName = physical_resource_id,
            S3Bucket = bucket_name,
            S3Key = s3_key
        )
        