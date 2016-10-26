# boa-nimbus

Command Line Interface (CLI) for packaging and uploading Python-based Lambda functions as part of a larger CloudFormation-based deployment.

## Why?

This makes it easy to deploy and update Lambda functions deployed with CloudFormation templates. You can now maintain a tight feedback loop when making changes and still use CloudFormation for the functions and their associated resources.

AWS CloudFormation is great for declaring and launching AWS resources for a project, but using it with Lambda functions severely limits them unless their code is already packaged and uploaded to S3. That means if you want to make full use of Lambda, your project needs to handle its own packaging, uploading, and updating of those Lambda package ZIPs **before** deploying your project's CloudFormation template(s).

This CLI takes care of that for you just by keeping your Lambda function sources in the directory structure it expects within your own project's repository.

## Features

 * Creates an S3 Bucket for hosting uploaded Lambda function packages (ZIPs).
 * Performs [deployment packaging](http://docs.aws.amazon.com/lambda/latest/dg/lambda-python-how-to-create-deployment-package.html) of Python-based Lambda functions.
 * Installs normal pip dependencies.
 * Installs pip modules from local source (for sharing your own Python modules between functions).
 * Supports building and uploading of only functions whose source (or deployment ZIP) changed since the last build.
 * Allows uploading of unrelated static S3 objects.
 * Creates AWS resources as part of a CloudFormation stack.
 * Includes Lambda-based CloudFormation custom resource for removing S3 objects on stack deletion.
 * Its CloudFormation stack exports the bucket's name.

[Import the stack's exported value](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference-importvalue.html) representing the bucket's name into your project's CloudFormation template and you're good to go!

## How to use

### Example
Check out a basic, working example project at [boa-nimbus-sample](https://github.com/moduspwnens/boa-nimbus-sample).

### Directory Structure

Create a **boa-nimbus** directory inside your main project's root directory, then add the directories as shown below.

```
boa-nimbus
          /lambda
          /lambda-pip-modules
          /s3
```
The **lambda** directory should contain a directory for each Lambda function you'd like to package and upload. For example:

```
boa-nimbus/lambda/UserImageUploadResizer
boa-nimbus/lambda/NewPostSubmissionHandler
```

Each one of those directories should contain the Lambda function's source code, along with an optional *requirements.txt* specifying any dependencies it needs.

Upon deployment, the function will be packaged as a zip with the directory's name and uploaded to the S3 bucket with a key prefix of "lambda/". For example, the above two Lambda functions would be deployed to the bucket as:

```
lambda/UserImageUploadResizer.zip
lambda/NewPostSubmissionHandler.zip
```

This consistency is what allows their paths to be specified in your main project's CloudFormation template.

The **lambda-pip-modules** directory should contain a directory for each module you would like to build locally and have included in one or more Lambda functions. It should have a [distutils setup.py file](https://docs.python.org/2/distutils/setupscript.html) in its root so that pip knows how to install it.

```
boa-nimbus/lambda-pip-modules/user-image-defaults
boa-nimbus/lambda-pip-modules/user-image-defaults/setup.py
boa-nimbus/lambda-pip-modules/user-image-defaults/user_image_defaults
boa-nimbus/lambda-pip-modules/user-image-defaults/user_image_defaults/__init__.py
boa-nimbus/lambda-pip-modules/user-image-defaults/user_image_defaults/defaults.py

boa-nimbus/lambda-pip-modules/my-project-exceptions
boa-nimbus/lambda-pip-modules/my-project-exceptions/setup.py
boa-nimbus/lambda-pip-modules/my-project-exceptions/my_project_exceptions
boa-nimbus/lambda-pip-modules/my-project-exceptions/my_project_exceptions/__init__.py
boa-nimbus/lambda-pip-modules/my-project-exceptions/my_project_exceptions/exception_classes.py
```

The two examples above show how it could be used to store default user image values or a common set of custom Exception classes for use throughout the project.

To include a local module with a function, add a line in the function's *requirements.txt* file with the path to the module's root directory (the one containing setup.py). The path should be relative to the project's root.

```
boa-nimbus/lambda-pip-modules/user-image-defaults
boa-nimbus/lambda-pip-modules/my-project-exceptions
```

This will ensure the two shared modules are installed and packaged with my Lambda function.

The **s3** directory should contain any static S3 objects to upload. It's optional, but you can use it to include static things you wouldn't want to package with your Lambda function (for whatever reason).

```
boa-nimbus/s3/Bunny.jpg
boa-nimbus/s3/subdirectory1/document.pdf
```

Static S3 objects are uploaded to the S3 bucket with their keys being their paths relative to the *s3* directory. The files above would have the following keys as deployed in the S3 bucket:

```
Bunny.jpg
subdirectory1/document.pdf
```

### Usage

Be sure you've set up your directory structure first, then:

```shell
# Ensure your AWS credentials are set. Use the AWS CLI docs for example setup.
# http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html

# Install boa-nimbus.
pip install git+git://github.com/moduspwnens/boa-nimbus.git

# Change directory to project root.
cd ~/projects/my-project1

# Deploy resources.
boa-nimbus deploy --stack-name my-project1-lambda
```

You now have a CloudFormation stack containing an S3 bucket with all of your Lambda functions packaged and uploaded. For your main project's CloudFormation template, just include a parameter for specifying this stack's name and reference it in your Lambda function resources. For example:

```yaml
---
AWSTemplateFormatVersion: '2010-09-09'
Description: My Project 1
Parameters:
  LambdaPackageStackName:
    Type: String
    Default: my-project1-lambda
    Description: Name of the CloudFormation stack deployed by boa-nimbus.
    MinLength: 1
Resources:
  UserImageUploadResizer:
    Type: AWS::Lambda::Function
    Properties:
      Description: Resize an uploaded user image.
      Handler: index.lambda_handler
      MemorySize: 128
      Code:
        S3Bucket:
          Fn::ImportValue:
            Fn::Sub: '${LambdaPackageStackName}-S3Bucket'
        S3Key: lambda/UserImageUploadResizer.zip
      Runtime: python2.7
      Role: [...]
```

To update your uploaded S3 resources (including repackaging the Lambda functions, if they've changed), just run the deploy command again.

```
boa-nimbus deploy --stack-name my-project1-lambda
```

Once you've deployed your main project's stack, the biggest time-saver is in updating the uploaded resources **and updating the Lambda functions to use them.** You can do this using the `--project-stack-name` argument instead.

```
boa-nimbus deploy --project-stack-name my-project1
```

boa-nimbus will look up its stack from the parameters of your main project's stack. This way, it can do the same redeployment and then update your Lambda functions' code as necessary.

When you're finished, you can simply delete the CloudFormation stack from the [web console](https://console.aws.amazon.com/cloudformation/home), or use this command:

```
boa-nimbus destroy --stack-name my-project1-lambda
```

Note that you'll need to delete your main project's stack first if it still exists.