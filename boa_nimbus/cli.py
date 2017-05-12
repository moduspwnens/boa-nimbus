#!/usr/bin/env python3

import os
import sys
import json
import hashlib
import yaml
import click

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

import docker_helpers
import hashing_helpers
import build_cache_helpers

from run_command import RunCommandBuildStepAction
from preprocess_swagger_input import PreprocessSwaggerInputBuildStepAction
from build_local_python_pip_modules import BuildLocalPythonPipModulesBuildStepAction
from build_python_lambda_functions import BuildPythonLambdaFunctionsBuildStepAction

boafile_name = "boafile.yaml"

@click.version_option(
    version = open(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), 
            'version.txt'
        )
    ).read()
)

@click.group(invoke_without_command=True)
@click.option('--verbose', is_flag=True, default=False)
@click.option('--region', help='AWS region to use.')
@click.option('--profile', help='AWS CLI profile to use.')
@click.option('--use-docker/--no-use-docker', default=True)
@click.pass_context
def cli(ctx, verbose, region, profile, use_docker):
    
    if region is not None:
        os.environ['AWS_DEFAULT_REGION'] = region
    
    if profile is not None:
        os.environ['AWS_DEFAULT_PROFILE'] = profile
    
    ctx.obj = {
        'VERBOSE': verbose
    }
    
    if ctx.invoked_subcommand is None:
        build()

@click.command()
@click.option('--use-docker/--no-use-docker', default=True)
@click.pass_context
def build(ctx, use_docker):
    
    if not os.path.exists(boafile_name):
        raise click.ClickException("No {} file found in current directory.".format(boafile_name))
    
    if use_docker:
        docker_helpers.verify_docker_reachable()
        docker_helpers.build_packager_docker_image()
    
    boafile_config = yaml.load(open(boafile_name).read())
    
    build_cache_hashes_dir = boafile_config.get("BuildCacheHashesDirectory")
    
    if build_cache_hashes_dir is not None:
        os.makedirs(build_cache_hashes_dir, exist_ok = True)
        build_cache_helpers.build_cache_hashes_directory = build_cache_hashes_dir
    
    
    
    build_step_groups = boafile_config.get("BuildStepGroups", [])
    
    if len(build_step_groups) == 0:
        raise click.ClickException("No \"BuildStepGroups\" specified in {}.".format(boafile_name))
    
    for each_group_dict in build_step_groups:
        run_build_step_group(boafile_config, each_group_dict, use_docker)
    
    #click.echo("Boafile config: {}".format(json.dumps(boafile_config)))
    
cli.add_command(build)


def run_build_step_group(full_config, group_config, use_docker):
    
    each_group_name = group_config.get("Name", "<Untitled group>")
    
    build_only_if_changes_in_path = group_config.get("IfChangesInPath")
    
    if build_only_if_changes_in_path is not None:
        if not build_cache_helpers.has_build_hash_changed_for_path(each_group_name, build_only_if_changes_in_path):
            click.echo("Skipping group: {}. No change since last build.".format(
                build_only_if_changes_in_path
            ))
            return
    
    click.echo("Starting group: {}".format(each_group_name))
    
    step_list = group_config.get("Steps", [])
    for each_step in step_list:
        run_build_step(full_config, each_step, use_docker)
    
    if build_only_if_changes_in_path is not None:
        build_cache_helpers.write_build_hash_for_path(
            each_group_name, 
            build_only_if_changes_in_path
        )

def run_build_step(full_config, step_config, use_docker):
    step_action = step_config.get("Action", "")
    
    action_handler_class = None
    
    if step_action == "RunCommand":
        action_handler_class = RunCommandBuildStepAction
    elif step_action == "PreprocessSwaggerInput":
        action_handler_class = PreprocessSwaggerInputBuildStepAction
    elif step_action == "BuildLocalPythonPipModules":
        action_handler_class = BuildLocalPythonPipModulesBuildStepAction
    elif step_action == "BuildPythonLambdaFunctions":
        action_handler_class = BuildPythonLambdaFunctionsBuildStepAction
    else:
        click.echo("Unknown command action: {}".format(step_action), err=True)
    
    if action_handler_class is not None:
        new_action_handler = action_handler_class(full_config, step_config)
        new_action_handler.use_docker = use_docker
        new_action_handler.run()
