# /// script
# requires-python = "==3.12.*"
# dependencies = ["python-dotenv==1.0.*"]
# ///

"""
See README.md for extensive info.
<https://github.com/Brown-University-Library/requirements-auto-updater/blob/main/README.md>

Info...
- Main manager function is`manage_update()`, at bottom above dundermain.
- Functions are in order called by `manage_update()`.

Usage...
`$ uv run ./auto_updater.py "/path/to/project_code_dir/"`
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from lib import lib_common, lib_django_updater, lib_environment_checker
from lib.lib_call_runtests import run_followup_tests, run_initial_tests
from lib.lib_compilation_evaluator import CompiledComparator
from lib.lib_emailer import send_email_of_diffs

## load envars ------------------------------------------------------
this_file_path = Path(__file__).resolve()
stuff_dir = this_file_path.parent.parent
dotenv_path = stuff_dir / '.env'
assert dotenv_path.exists(), f'file does not exist, ``{dotenv_path}``'
load_dotenv(find_dotenv(str(dotenv_path), raise_error_if_not_found=True), override=True)

## define constants -------------------------------------------------
ENVAR_EMAIL_FROM = os.environ['AUTO_UPDTR__EMAIL_FROM']
ENVAR_EMAIL_HOST = os.environ['AUTO_UPDTR__EMAIL_HOST']
ENVAR_EMAIL_HOST_PORT = os.environ['AUTO_UPDTR__EMAIL_HOST_PORT']
UV_PATH = os.environ['AUTO_UPDTR__UV_PATH']

## set up logging ---------------------------------------------------
log_dir: Path = stuff_dir / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)  # creates the log-directory inside the stuff-directory if it doesn't exist
log_file_path: Path = log_dir / 'auto_updater.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s [%(module)s-%(funcName)s()::%(lineno)d] %(message)s',
    datefmt='%d/%b/%Y %H:%M:%S',
    filename=log_file_path,
)
log = logging.getLogger(__name__)


## ------------------------------------------------------------------
## main code -- called by manage_update() ---------------------------
## ------------------------------------------------------------------


def compile_requirements(project_path: Path, python_version: str, environment_type: str, uv_path: Path) -> Path:
    """
    Compiles the project's `requirements.in` file into a versioned `requirements.txt` backup.
    Returns the path to the newly created backup file.
    """
    log.info('::: compiling requirements ----------')
    ## prepare requirements.in filepath -----------------------------
    requirements_in: Path = project_path / 'requirements' / f'{environment_type}.in'  # local.in, staging.in, production.in
    log.debug(f'requirements.in path, ``{requirements_in}``')
    ## ensure backup-directory is ready -----------------------------
    backup_dir: Path = project_path.parent / 'requirements_backups'
    log.debug(f'backup_dir: ``{backup_dir}``')
    backup_dir.mkdir(parents=True, exist_ok=True)
    ## prepare compiled_filepath ------------------------------------
    timestamp: str = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
    compiled_filepath: Path = backup_dir / f'{environment_type}_{timestamp}.txt'
    log.debug(f'backup_file: ``{compiled_filepath}``')
    ## prepare compile command --------------------------------------
    compile_command: list[str] = [
        str(uv_path),
        'pip',
        'compile',
        str(requirements_in),
        '--output-file',
        str(compiled_filepath),
        '--universal',
        '--python',
        python_version,
    ]
    log.debug(f'compile_command: ``{compile_command}``')
    ## run compile command ------------------------------------------
    try:
        subprocess.run(compile_command, check=True)
        log.info('ok / uv pip compile was successful')
    except subprocess.CalledProcessError:
        message = 'Error during pip compile'
        log.exception(message)
        raise Exception(message)
    return compiled_filepath

    ## end def compile_requirements()


def remove_old_backups(project_path: Path, keep_recent: int = 30) -> None:
    """
    Removes all files in the backup directory other than the most-recent files.
    """
    log.info('::: removing old backups ----------')
    backup_dir: Path = project_path.parent / 'requirements_backups'
    backups: list[Path] = sorted([f for f in backup_dir.iterdir() if f.is_file() and f.suffix == '.txt'], reverse=True)
    old_backups: list[Path] = backups[keep_recent:]
    for old_backup in old_backups:
        log.debug(f'removing old backup: {old_backup}')
        old_backup.unlink()
    log.info('ok / old backups removed')
    return


def sync_dependencies(project_path: Path, backup_file: Path, uv_path: Path) -> None:
    """
    Prepares the venv environment.
    Syncs the recent `--output` requirements.in file to the venv.
    Exits the script if any command fails.

    Why this works, without explicitly "activate"-ing the venv...

    When a Python virtual environment is traditionally 'activated' -- ie via `source venv/bin/activate`
    in a shell -- what is really happening is that a set of environment variables is adjusted
    to ensure that when python or other commands are run, they refer to the virtual environment's
    binaries and site-packages rather than the system-wide python installation.

    This code mimics that environment modification by explicitly setting
    the PATH and VIRTUAL_ENV environment variables before running the command.
    """
    log.info('::: syncing dependencies ----------')
    ## prepare env-path variables -----------------------------------
    venv_tuple: tuple[Path, Path] = lib_common.determine_venv_paths(project_path)
    (venv_bin_path, venv_path) = venv_tuple
    ## set the local-env paths ---------------------------------------
    local_scoped_env = os.environ.copy()
    local_scoped_env['PATH'] = f'{venv_bin_path}:{local_scoped_env["PATH"]}'  # prioritizes venv-path
    local_scoped_env['VIRTUAL_ENV'] = str(venv_path)
    ## prepare sync command ------------------------------------------
    sync_command: list[str] = [str(uv_path), 'pip', 'sync', str(backup_file)]
    log.debug(f'sync_command: ``{sync_command}``')
    try:
        ## run sync command ------------------------------------------
        subprocess.run(sync_command, check=True, env=local_scoped_env)  # so all installs will go to the venv
        log.info('ok / `uv pip sync` was successful')
    except subprocess.CalledProcessError:
        message = 'Error during `uv pip sync`'
        log.exception(message)
        raise Exception(message)
    try:
        ## run `touch` to make the changes take effect ---------------
        log.info('::: running `touch` ----------')
        subprocess.run(['touch', './config/tmp/restart.txt'], check=True)
        log.info('ok / ran `touch`')
    except subprocess.CalledProcessError:
        message = 'Error during `touch'
        log.exception(message)
        raise Exception(message)
    return

    ## end def sync_dependencies()


def mark_active(backup_file: Path) -> None:
    """
    Marks the backup file as active by adding a header comment.
    """
    log.info('::: marking recent-backup as active ----------')
    with backup_file.open('r') as file:  # read the file
        content: list[str] = file.readlines()
    content.insert(0, '# ACTIVE\n')
    with backup_file.open('w') as file:  # write the file
        file.writelines(content)
    log.info('ok / marked recent-backup as active')
    return


def update_group_and_permissions(project_path: Path, backup_file: Path, group: str) -> None:
    """
    Tries to update group-ownership and group-permissions for relevant directories.
    Intentionally does not fail if the commands fail.
    """
    log.info('::: updating group and permissions ----------')
    backup_dir: Path = project_path.parent / 'requirements_backups'
    log.debug(f'backup_dir: ``{backup_dir}``')
    relative_env_path = project_path / '../env'
    env_path = relative_env_path.resolve()
    log.debug(f'env_path: ``{env_path}``')
    for path in [env_path, backup_dir]:
        log.debug(f'updating group and permissions for path: ``{path}``')
        chgrp_result: subprocess.CompletedProcess[str] = subprocess.run(
            ['chgrp', '-R', group, str(path)], capture_output=True, text=True, check=False
        )
        log.debug(f'chgrp_result: ``{chgrp_result}``')
        chmod_result: subprocess.CompletedProcess[str] = subprocess.run(
            ['chmod', '-R', 'g=rwX', str(path)], capture_output=True, text=True, check=False
        )
        log.debug(f'chmod_result: ``{chmod_result}``')
    log.info('ok / attempted update of group and permissions')
    return


## ------------------------------------------------------------------
## main manager function --------------------------------------------
## ------------------------------------------------------------------


def manage_update(project_path_str: str) -> None:
    """
    Main function to manage the update process for the project's dependencies.
    Calls various helper functions to validate, compile, compare, sync, and update permissions.
    """
    log.debug('starting manage_update()')

    ## ::: run environmental checks :::
    ## validate project path ----------------------------------------
    project_path: Path = Path(project_path_str).resolve()  # ensures an absolute path now
    lib_environment_checker.validate_project_path(project_path)
    ## cd to project dir --------------------------------------------
    os.chdir(project_path)
    ## get email addresses ------------------------------------------
    project_email_addresses: list[tuple[str, str]] = lib_environment_checker.determine_project_email_addresses(project_path)
    ## check branch -------------------------------------------------
    lib_environment_checker.check_branch(project_path, project_email_addresses)  # emails admins and exits if not on main
    ## check git status ---------------------------------------------
    lib_environment_checker.check_git_status(project_path, project_email_addresses)  # emails admins and exits if not clean
    ## get python version -------------------------------------------
    version_info: tuple[str, str, str] = lib_environment_checker.determine_python_version(
        project_path, project_email_addresses
    )  # ie, ('3.12.4', '~=3.12.0', '/path/to/python3.12')
    env_python_path_resolved = version_info[2]
    ## get environment-type -----------------------------------------
    environment_type: str = lib_environment_checker.determine_environment_type(project_path, project_email_addresses)
    ## get uv path --------------------------------------------------
    # uv_path: Path = lib_environment_checker.determine_uv_path(project_path, project_email_addresses)
    uv_path: Path = Path(UV_PATH)
    ## get group ----------------------------------------------------
    group: str = lib_environment_checker.determine_group(project_path, project_email_addresses)
    ## check for correct group and group-write permissions ---------
    lib_environment_checker.check_group_and_permissions(project_path, group, project_email_addresses)

    ## ::: initial tests :::
    ## run initial tests --------------------------------------------
    if environment_type != 'production':
        run_initial_tests(uv_path, project_path, project_email_addresses)

    ## ::: compilation :::
    ## compile requirements file ------------------------------------
    compiled_requirements: Path = compile_requirements(project_path, env_python_path_resolved, environment_type, uv_path)
    ## cleanup old backups ------------------------------------------
    remove_old_backups(project_path)
    ## see if the new compile is different --------------------------
    compiled_comparator = CompiledComparator()
    differences_found: bool = compiled_comparator.compare_with_previous_backup(
        compiled_requirements, old_path=None, project_path=project_path
    )

    ## ::: act on differences :::
    if differences_found:
        ## since it's different, update the venv --------------------
        sync_dependencies(project_path, compiled_requirements, uv_path)
        ## mark new-compile as active -------------------------------
        mark_active(compiled_requirements)
        ## make diff ------------------------------------------------
        diff_text: str = compiled_comparator.make_diff_text(project_path)
        ## check for django update ----------------------------------
        followup_collectstatic_problems: None | str = None
        django_update: bool = lib_django_updater.check_for_django_update(diff_text)
        if django_update:
            followup_collectstatic_problems = lib_django_updater.run_collectstatic(project_path)
        ## copy new compile to codebase -----------------------------
        followup_copy_problems: None | str = None
        followup_copy_problems = compiled_comparator.copy_new_compile_to_codebase(
            compiled_requirements, project_path, environment_type
        )
        ## run post-update tests ------------------------------------
        followup_tests_problems: None | str = None
        if environment_type != 'production':
            followup_tests_problems = run_followup_tests(uv_path, project_path)
        ## send diff email ------------------------------------------
        followup_problems = {
            'collectstatic_problems': followup_collectstatic_problems,
            'copy_problems': followup_copy_problems,
            'test_problems': followup_tests_problems,
        }
        log.debug(f'followup_problems, ``{followup_problems}``')
        send_email_of_diffs(project_path, diff_text, followup_problems, project_email_addresses)
        log.debug('email sent')

    ## ::: clean up :::
    ## try group and permissions update -----------------------------
    update_group_and_permissions(project_path, compiled_requirements, group)
    return

    ## end def manage_update()


if __name__ == '__main__':
    log.debug('\n\nstarting dundermain')

    parser = argparse.ArgumentParser(description='Updates dependencies for the specified project')
    parser.add_argument('--project', required=True, help='Path to the project directory')
    try:
        args = parser.parse_args()
        project_path = args.project
        log.debug(f'Project path: {project_path}')
        manage_update(project_path)
    except argparse.ArgumentError as e:
        log.error(f'Argument error: {e}')
        parser.print_help()
        sys.exit(1)
