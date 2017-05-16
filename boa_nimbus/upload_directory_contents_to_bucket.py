import os
import threading
import click
import boto3
from botocore.exceptions import ClientError
import hashing_helpers

class UploadDirectoryContentsToBucketDeployStepAction(object):
    
    def __init__(self, full_config, step_config):
        self.bucket_name_prefix = step_config.get("BucketNamePrefix", "")
        self.directory = step_config["Directory"]
        self.except_files = step_config.get("ExceptFiles", [])
        self.upload_only_if_not_exists_files = step_config.get("UploadOnlyIfNotExists", [])
    
    def run(self):
        
        response = boto3.client("sts").get_caller_identity()
        
        bucket_name = self.bucket_name_prefix + response["Account"]
        
        thread_list = []
        
        for dir_name, subdir_list, file_list in os.walk(self.directory):
            
            for each_file in file_list:
                
                each_s3_key = os.path.join(dir_name, each_file)
                
                each_s3_key = each_s3_key[len(self.directory)+1:]
                
                if each_s3_key in self.except_files:
                    continue
                
                each_file_path = os.path.join(dir_name, each_file)
                
                t = threading.Thread(
                    target = self.upload_file_if_necessary,
                    kwargs = {
                        "bucket_name": bucket_name,
                        "each_file_path": each_file_path,
                        "each_s3_key": each_s3_key
                    }
                )
                
                thread_list.append(t)
        
        for each_thread in thread_list:
            each_thread.start()
        
        for each_thread in thread_list:
            each_thread.join()
                
    
    def upload_file_if_necessary(self, bucket_name, each_file_path, each_s3_key):
        
        s3_client = boto3.client("s3")
        
        each_file_md5 = hashing_helpers.file_md5_checksum(os.path.abspath(each_file_path))
        each_file_sha256_base64 = hashing_helpers.file_sha256_checksum_base64(os.path.abspath(each_file_path))
        
        preexisting_file_md5 = None
        
        try:
            response = s3_client.head_object(
                Bucket = bucket_name,
                Key = each_s3_key
            )
        
            preexisting_file_md5 = response.get("Metadata", {}).get("boa-nimbus-md5", "")
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                pass
            else:
                raise
        
        if preexisting_file_md5 is not None and each_s3_key in self.upload_only_if_not_exists_files:
            return
        
        if preexisting_file_md5 == each_file_md5:
            click.echo("Skipping upload of {}. No changes since last upload.".format(
                each_s3_key
            ))
            return
        
        click.echo("Uploading file: {}.".format(
            each_s3_key
        ))
        
        
        s3_object_content = open(each_file_path, "rb").read()
        
        s3_client.put_object(
            Bucket = bucket_name,
            Key = each_s3_key,
            Body = s3_object_content,
            Metadata = {
                "boa-nimbus-md5": each_file_md5,
                "boa-nimbus-sha256-base64": each_file_sha256_base64
            }
        )