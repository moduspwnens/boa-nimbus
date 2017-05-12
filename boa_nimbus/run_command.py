import os
import click
import subprocess

class RunCommandBuildStepAction(object):
    
    def __init__(self, full_config, step_config):
        self.run_directory = step_config.get("Directory", "")
        self.command = step_config.get("Command", "")
        
        if len(self.command) == 0:
            raise click.ClickException("\"RunCommand\" build step has no command.")
    
    def run(self):
        
        click.echo("Running \"{}\".".format(self.command))
        
        change_dir = self.run_directory != ""
        
        if change_dir:
            previous_working_dir = os.getcwd()
            os.chdir(self.run_directory)
        
        try:
            p = subprocess.run(
                self.command,
                shell = True,
                check = True
            )
        
        finally:
            if change_dir:
                os.chdir(previous_working_dir)
        