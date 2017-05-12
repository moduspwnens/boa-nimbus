import os
import sys
import json
import subprocess
import uuid
import shutil
import click
import yaml
import docker_helpers
import hashing_helpers
import build_cache_helpers

exclude_files = [".DS_Store"]

class BuildPythonLambdaFunctionsBuildStepAction(object):
    
    def __init__(self, full_config, step_config):
        self.input_directory = step_config.get("InputDirectory", "")
        self.output_directory = step_config.get("OutputDirectory", "")
        self.local_python_packages_directory = step_config.get("LocalPythonPackagesDirectory")
        self.pip_cache_directory = step_config.get("PipCacheDirectory")
        
        self.build_cache_key_prefix = "BuildPythonLambdaFunctions"
    
    def run(self):
        
        click.echo("Running BuildPythonLambdaFunctions action.")
        
        os.makedirs(self.output_directory, exist_ok = True)
        
        for root, dir_list, file_list in os.walk(self.input_directory):
            if root != self.input_directory:
                break
            
            for each_dir in dir_list:
                self.build_lambda_function_from_dir(os.path.join(root, each_dir))
    
    def build_lambda_function_from_dir(self, source_dir):
        use_docker = hasattr(self, "use_docker") and self.use_docker
        
        build_cache_key = "{}-{}".format(
            self.build_cache_key_prefix,
            use_docker
        )
        
        if not build_cache_helpers.has_build_hash_changed_for_path(build_cache_key, source_dir):
            click.echo("Skipping Lambda function: {}. No change since last build.".format(
                source_dir
            ))
            return
        
        click.echo("Building Lambda function at dir: {}".format(source_dir))
        
        lambda_runtime = "python3.6"
        
        package_config_settings = {}
        
        try:
            package_config_settings = yaml.load(open(os.path.join(source_dir, "package.yaml")))
            lambda_runtime = package_config_settings["Options"]["Runtime"]
        except:
            pass
        
        if lambda_runtime not in ["python2.7", "python3.6"]:
            raise click.ClickException("Unsupported Lambda function runtime: {}".format(lambda_runtime))
        
        pip_requirements_path = os.path.join(source_dir, "requirements.txt")
        
        function_build_dir = os.path.join("/tmp", str(uuid.uuid4()))
        deps_output_dir = os.path.join("/tmp", str(uuid.uuid4()))
        
        for each_dir in [function_build_dir, deps_output_dir]:
            os.makedirs(each_dir)
        
        if os.path.exists(pip_requirements_path):
        
            pip_binary = "pip3.6"
            venv_path = "/venv3"
            venv_python_dir_path = "python3.6"
        
            if lambda_runtime == "python2.7":
                pip_binary = "pip2"
                venv_path = "/venv"
                venv_python_dir_path = "python2.7"
            
            if (self.pip_cache_directory is not None) and (not os.path.exists(self.pip_cache_directory)):
                os.makedirs(self.pip_cache_directory, exist_ok=True)
            
            if use_docker:
                docker_build_args = ["docker", "run", "--rm"]
            
                docker_build_args.extend(["-v", "{}:/requirements.txt".format(os.path.abspath(pip_requirements_path))])
                docker_build_args.extend(["-v", "{}:/build".format(deps_output_dir)])
            
                if self.local_python_packages_directory is not None:
                    docker_build_args.extend(["-v", "{}:/local-pip-packages".format(os.path.abspath(self.local_python_packages_directory))])
                
                if self.pip_cache_directory is not None:
                    docker_build_args.extend(["-v", "{}:/root/.cache".format(os.path.abspath(self.pip_cache_directory))])
            
                docker_build_args.extend(["-it", docker_helpers.local_lambda_packager_image_name, "/bin/bash", "-c"])
            
                run_commands = [
                    "source {}/bin/activate".format(venv_path),
                    "{} install --find-links file:///local-pip-packages -r /requirements.txt".format(pip_binary)
                ]
            
                for each_dir in ["lib", "lib64"]:
                    run_commands.append("cp -R {}/{}/{}/site-packages/* /build".format(venv_path, each_dir, venv_python_dir_path))
            
                post_install_commands = package_config_settings.get("PostInstallCommands", [])
            
                run_commands.extend(post_install_commands)
            
                docker_build_args.append(" && ".join(run_commands))
            
                try:
                    p = subprocess.run(
                        docker_build_args,
                        check = True
                    )
                except:
                    for each_dir in [function_build_dir, deps_output_dir]:
                        shutil.rmtree(each_dir)
                    raise
            
            else:
                
                pip_args = [
                    pip_binary, 
                    "install"
                ]
                
                if self.local_python_packages_directory is not None:
                    pip_args.extend([
                        "--find-links",
                        os.path.abspath(self.local_python_packages_directory)
                    ])
                
                pip_args.extend([
                    "-r",
                    os.path.abspath(pip_requirements_path),
                    "-t",
                    deps_output_dir
                ])
                
                try:
                    p = subprocess.run(
                        pip_args,
                        check = True
                    )
                except:
                    for each_dir in [function_build_dir, deps_output_dir]:
                        shutil.rmtree(each_dir)
                    raise
            
            
            
            for each_item in os.listdir(deps_output_dir):
                if each_item in exclude_files:
                    continue
                
                shutil.move(
                    os.path.join(deps_output_dir, each_item),
                    function_build_dir
                )
        
        
            
        for each_item in os.listdir(source_dir):
            if each_item == "package.yaml":
                continue
            if each_item in exclude_files:
                continue
            
            shutil.copy(
                os.path.join(source_dir, each_item),
                function_build_dir
            )
        
        function_name = os.path.split(source_dir)[1]
        
        click.echo("Function: {}".format(function_name))
        
        build_zip_path_without_extension = os.path.join(self.output_directory, function_name)
        build_zip_path = "{}.zip".format(build_zip_path_without_extension)
        if os.path.exists(build_zip_path):
            os.unlink(build_zip_path)
            
        click.echo("Creating Lambda function package at {}.".format(build_zip_path))
        shutil.make_archive(build_zip_path_without_extension, "zip", function_build_dir)
        
        for each_dir in [function_build_dir, deps_output_dir]:
            shutil.rmtree(each_dir)
        
        source_dir_hash = hashing_helpers.directory_sha1_hash(source_dir)
        new_zip_hash = hashing_helpers.file_sha256_checksum_base64(build_zip_path)
        
        new_build_metadata = {
            "source": source_dir_hash,
            "zip": new_zip_hash,
            "runtime": lambda_runtime
        }
        
        build_cache_helpers.write_build_hash_for_path(build_cache_key, source_dir)
        
        #click.echo("Metadata: {}".format(json.dumps(new_build_metadata)))
            
        
            
            
            