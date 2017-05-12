import os
import sys
import json
import subprocess
import hashlib
import click
import hashing_helpers
import build_cache_helpers

class BuildLocalPythonPipModulesBuildStepAction(object):
    
    
    
    def __init__(self, full_config, step_config):
        self.input_directory = step_config.get("InputDirectory", "")
        self.output_directory = step_config.get("OutputDirectory", "")
        
        self.build_cache_hashes_directory = full_config.get("BuildCacheHashesDirectory")
        
        self.build_cache_key = "BuildLocalPythonPipModules"
    
    def run(self):
        
        click.echo("Running BuildLocalPythonPipModules action.")
        
        use_docker = hasattr(self, "use_docker") and self.use_docker
        
        if use_docker:
            click.echo("WARNING: Docker-based builds of pip modules not yet implemented. Building without Docker.")
        
        for root, dir_list, file_list in os.walk(self.input_directory):
            if root != self.input_directory:
                break
            
            for each_dir in dir_list:
                self.build_pip_module_from_dir(os.path.join(root, each_dir))
    
    def build_pip_module_from_dir(self, source_dir):
        
        if not build_cache_helpers.has_build_hash_changed_for_path(self.build_cache_key, source_dir):
            click.echo("Skipping module: {}. No change since last build.".format(
                source_dir
            ))
            return
        
        click.echo("Building pip module: {}".format(source_dir))
        
        pip_build_args = [
            sys.executable,
            "-u",
            "setup.py",
            "-q",
            "sdist",
            "--dist-dir",
            os.path.abspath(self.output_directory)
        ]
        
        previous_working_dir = os.getcwd()
        os.chdir(source_dir)
        
        try:
            p = subprocess.run(
                pip_build_args,
                check = True,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE
            )
        except Exception as e:
            try:
                click.error(p.stderr)
            except:
                pass
            
            raise
        finally:
            os.chdir(previous_working_dir)
        
        build_cache_helpers.write_build_hash_for_path(self.build_cache_key, source_dir)
        