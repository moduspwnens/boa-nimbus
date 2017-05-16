import os
import subprocess
import click
import boto3
from botocore.exceptions import ClientError

class CreateBucketIfNotExistsDeployStepAction(object):
    
    def __init__(self, full_config, step_config):
        self.bucket_name_prefix = step_config.get("BucketNamePrefix", "")
    
    def run(self):
        
        click.echo("Checking / creating bucket with prefix: \"{}\".".format(self.bucket_name_prefix))
        
        response = boto3.client("sts").get_caller_identity()
        
        bucket_name = self.bucket_name_prefix + response["Account"]
        
        click.echo("Bucket name: {}".format(bucket_name))
        
        bucket_exists = False
        
        try:
            response = boto3.client("s3").head_bucket(
                Bucket = bucket_name
            )
            bucket_exists = True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                pass
            else:
                raise
        
        if not bucket_exists:
            click.echo("Creating bucket.")
            
            boto3.client("s3").create_bucket(
                Bucket = bucket_name
            )