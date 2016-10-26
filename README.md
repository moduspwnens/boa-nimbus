# boa-nimbus

Python CLI for packaging and uploading Python-based Lambda functions as part of a larger deployment.

## Why?

AWS CloudFormation is great for declaring and launching AWS resources for a project, but using it with Lambda functions severely limits them unless their code is already packaged and uploaded to S3. That means if you want to make full use of Lambda, your project needs to handle its own packaging, uploading, and updating of those Lambda package ZIPs **before** deploying your project's CloudFormation template(s).

This CLI allows you to structure your Lambda source files in a way that takes care of all that for you.

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

Not yet implemented.