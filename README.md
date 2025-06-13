## Overview...

Enables automatic dependency and venv updating.

Called directly -- or, typically, by a cron job -- this script:
- checks a bunch of expectations about the project
    - if expectations fail, an email noting the failure will go out to the target-project admins if possible; otherwise to the auto-updater admins
- makes a backup of the current `uv.lock` file
- runs a command which  creates a new lock-file and updates the venv
- if there's a change:
    - confirms tests pass
    - commits and emails diffs on success; reverts and emails info on failure

---


## Flow...

(see `manage_update()`, near bottom dundermain, for details)

- Performs these initial checks:
    - validates submitted project-path
    - determines the admin-emails
    - validates expected branch
    - validates expected git-status
    - determines the `local/staging/production` environment
    - determines a `uv` path
    - determines the group
    - validates group and permissions on the venv and the `requirements_backups` directories
    - calls project's run_tests.py

- If any of the above steps fail, emails project-admins (or updater-admins)

- Backups the current `uv.lock` file, saving the last 30

- Runs the command `uv sync --upgrade --group local/staging/prod`
    - This creates a new lock-file and updates the venv.


- Checks the lock-file to see if anything is new

- If there is something new: 
    - runs the usual `touch` command to let passenger know to reload the django-app
    - performs a diff showing the change, and creates diff text
    - checks the diff for a django update, and if django was updated, runs its collectstatic command
    - runs `run_tests.py` again

- If tests pass:
    - runs a git-pull, then a git-add, then a git-commit, then a git-push
    - emails the diff to the project-admins

- If tests fail:
    - restores the `uv.lock` file from the backup
    - runs `uv sync --group local/staging/prod` to revert the venv
    - if django was updated, runs its collectstatic command
    - emails the diff, and the test-issues, to the project-admins

- Finally, attempts to recursively update group & permissions on the 'stuff' directory

---


## Usage...

- Directly:
    ```
    $ cd "/path/to/pyproject-autoupdater/"
    $ uv run ./auto_update.py --project_path "/path/to/project_to_update_code_dir/"
    ```

- Via cron on servers (eg to run every day at midnight) (all one line):
    ```
    0 0 * * * cd "/path/to/pyproject-autoupdater/" && path/to/uv run ./auto_update.py --project_path "/path/to/project_to_update_code_dir/"
    ```

---


## Project assumptions...

- `uv` is installed.
- The `pyproject.toml` file contains tilde-notation (`package~=1.2.0`) wherever possible. That third numeral is important; we only want to update the `patch` version.
- There is a `.env` file in the "outer-stuff" directory.
- The `.env` file contains an `ADMINS_JSON` entry with the following structure:
    ```
    ADMINS_JSON='
        [
            [ "exampleFirstname1 exampleLastname1", "example1@domain.edu" ],
            [ "exampleFirstname2 exampleLastname2", "example2@domain.edu" ]
        ]'
    ```

---


## Notes...

- Suggestion: we do not tweak this script for different project-structures; rather, we restructure our apps to fit these assumptions (to keep this script simple, and for the benefits of a more standardized project structure).

- The `backup_dependencies` dir defaults to storing the last 30 `uv.lock` files. With a cron-job running once-a-day, that gives us a month to detect a problem and be able to access the previously-active `uv.lock` file. You can tell which were active because they'll contain the string `# ACTIVE` at the top.

- To monitor: using the tilde-notation to ensure that only the `patch` version is updated _could_ still install new non-patch-level versions of dependencies. In the 2 months of monitoring this in real usage on two projects, this has not caused an issue. And if it does, hopefully `run_tests.py` will catch it.

---


## Motivation...

We need to make upgrading dependency-packages more sustainable. 

By definition, the third part of package-notation (`major`, `minor`, `patch`) infers both backwards-compatibility and bug-fixes, so this should lighten the technical-debt load. However it _is_ possible for `patch` upgrades to contain backwards-incompatibilites -- [example](https://www.djangoproject.com/weblog/2023/may/03/security-releases/).

---
