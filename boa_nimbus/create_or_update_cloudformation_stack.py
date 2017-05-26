import os
import time
import click
import boto3
from botocore.exceptions import ClientError
import hashing_helpers

cf_client = boto3.client("cloudformation")
s3_client = boto3.client("s3")

class CreateOrUpdateCloudFormationStackDeployStepAction(object):
    
    def __init__(self, full_config, step_config):
        self.bucket_name_prefix = step_config.get("SourceBucketNamePrefix", "")
        self.stack_name = step_config["StackName"]
        self.template_path = step_config["TemplatePath"]
        self.stack_parameter_updates = step_config.get("StackParameterUpdates", {})
    
    def run(self):
        
        click.echo("Creating / updating CloudFormation stack: {}".format(self.stack_name))
        
        response = boto3.client("sts").get_caller_identity()
        
        bucket_name = self.bucket_name_prefix + response["Account"]
        
        stack_exists = False
        try:
            response = cf_client.describe_stacks(
                StackName = self.stack_name
            )
            stack_exists = True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ValidationError' and "does not exist" in str(e):
                pass
            else:
                raise
        
        cf_template_key = "boa-nimbus/{}.cftemplate".format(
            hashing_helpers.file_md5_checksum(os.path.abspath(self.template_path))
        )
        
        try:
            s3_client.head_object(
                Bucket = bucket_name,
                Key = cf_template_key
            )
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                click.echo("Uploading stack template to S3.")
                s3_client.put_object(
                    Bucket = bucket_name,
                    Key = cf_template_key,
                    Body = open(os.path.abspath(self.template_path)).read()
                )
            else:
                raise
        
        should_wait_for_stack_ready = False
        
        required_params_map = {}
        required_params_map["S3SourceBucket"] = bucket_name
        
        for each_key, each_value in self.stack_parameter_updates.items():
            if each_key == "ApiDefinitionVersion":
                # The value should be a hash of the given file.
                param_value = hashing_helpers.file_md5_checksum(each_value)
                required_params_map[each_key] = param_value
        
        required_parameter_list = []
        
        for each_key, each_value in required_params_map.items():
            required_parameter_list.append({
                "ParameterKey": each_key,
                "ParameterValue": each_value
            })
        
        if not stack_exists:
            # Upload the template file to S3.
            
            click.echo("Creating CloudFormation stack ({}).".format(
                self.stack_name
            ))
            
            response = cf_client.create_stack(
                StackName = self.stack_name,
                TemplateURL = "https://s3.amazonaws.com/{}/{}".format(
                    bucket_name,
                    cf_template_key
                ),
                Parameters = required_parameter_list,
                Capabilities = [
                    "CAPABILITY_IAM"
                ]
            )
            
            should_wait_for_stack_ready = True
        
        else:
            
            click.echo("Updating CloudFormation stack ({}).".format(
                self.stack_name
            ))
            
            new_parameter_list = []
            new_parameter_list.extend(required_parameter_list)
            
            for each_parameter_dict in response["Stacks"][0]["Parameters"]:
                if each_parameter_dict["ParameterKey"] in required_params_map:
                    continue
                else:
                    new_parameter_list.append({
                        "ParameterKey": each_parameter_dict["ParameterKey"],
                        "UsePreviousValue": True
                    })
            
            try:
                response = cf_client.update_stack(
                    StackName = self.stack_name,
                    TemplateURL = "https://s3.amazonaws.com/{}/{}".format(
                        bucket_name,
                        cf_template_key
                    ),
                    Parameters = new_parameter_list,
                    Capabilities = [
                        "CAPABILITY_IAM"
                    ]
                )
                should_wait_for_stack_ready = True
            except ClientError as e:
                if e.response['Error']['Code'] == 'ValidationError' and "No updates are to be performed." in str(e):
                    click.echo("No updates necessary for CloudFormation stack.")
                else:
                    raise
        
        if should_wait_for_stack_ready:
            
            stack_ending_status = None
            
            while True:
                
                response = cf_client.describe_stacks(
                    StackName = self.stack_name
                )
                
                this_stack = response["Stacks"][0]
                this_stack_status = this_stack["StackStatus"]
                
                click.echo(" > Stack status: {}".format(this_stack_status))
                
                if not this_stack_status.endswith("_IN_PROGRESS"):
                    stack_ending_status = this_stack_status
                    break
                
                time.sleep(15)
            
            if "ROLLBACK" in stack_ending_status:
                raise click.ClickException("Stack update ended with status: {}".format(stack_ending_status))