import argparse
import logging
import re
from pathlib import Path
from typing import Any

import tomllib

log = logging.getLogger(__name__)


def load_toml_file(path: str) -> dict[str, Any]:
    with open(path, 'rb') as f:
        return tomllib.load(f)


def is_valid_tilde_dep(dep: str) -> bool:
    # Example match: "Django~=4.2.0"
    return re.fullmatch(r'^[^~]+~=\d+\.\d+\.0$', dep.strip()) is not None


def validate_pyproject(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    valid: bool = False

    ## check top-level sections -------------------------------------
    project = data.get('project')
    if not isinstance(project, dict):
        errors.append('Missing or invalid [project] section.')

    requires_python = project.get('requires-python')
    if not isinstance(requires_python, str):
        errors.append('Missing or invalid [project] requires-python] section.')

    dependencies = project.get('dependencies')
    if not isinstance(dependencies, list):
        errors.append('Missing or invalid [project] dependencies section.')

    dep_groups = data.get('dependency-groups')
    if not isinstance(dep_groups, dict):
        errors.append('Missing or invalid [dependency-groups] section.')

    ## check that dependency-groups exist ---------------------------
    for group in ('staging', 'prod'):
        toml_group_deps = dep_groups.get(group)
        if not isinstance(toml_group_deps, list):
            errors.append(f'dependency-groups.{group} missing or not a list.')
    if not errors:
        valid = True
    log.debug(f'valid: {valid}')
    log.debug(f'errors: {errors}')
    return valid, errors


def run_toml_check(toml_path: Path) -> tuple[bool, list[str]]:
    """
    Validates the pyproject.toml file.
    Returns a tuple of (valid, errors).
    """
    errors: list[str] = []
    valid: bool = False
    data = load_toml_file(str(toml_path))
    (valid, errors) = validate_pyproject(data)
    return (valid, errors)
    # if errors:
    #     print('Validation errors:')
    #     for err in errors:
    #         print(f'- {err}')
    # else:
    #     print('pyproject.toml is valid!')


if __name__ == '__main__':
    ## get --toml-path arg ------------------------------------------
    parser = argparse.ArgumentParser(description='Validate pyproject.toml file.')
    parser.add_argument('--toml-path', type=Path, required=True, help='Path to pyproject.toml file')
    args = parser.parse_args()
    ## run check ----------------------------------------------------
    (valid, errors) = run_toml_check(args.toml_path)
