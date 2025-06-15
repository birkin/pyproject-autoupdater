import re
from typing import Any
import tomli

def load_toml_file(path: str) -> dict[str, Any]:
    with open(path, 'rb') as f:
        return tomli.load(f)

def is_valid_tilde_dep(dep: str) -> bool:
    # Example match: "Django~=4.2.0"
    return re.fullmatch(r'^[^~]+~=\d+\.\d+\.0$', dep.strip()) is not None

def validate_pyproject(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    # Check top-level sections
    project = data.get('project')
    if not isinstance(project, dict):
        errors.append('Missing or invalid [project] section.')

    dep_groups = data.get('dependency-groups')
    if not isinstance(dep_groups, dict):
        errors.append('Missing or invalid [dependency-groups] section.')

    # Validate dependencies in [project]
    if isinstance(project, dict):
        deps = project.get('dependencies')
        if not isinstance(deps, list):
            errors.append('project.dependencies missing or not a list.')
        else:
            for dep in deps:
                if not isinstance(dep, str):
                    errors.append(f'project.dependencies entry is not a string: {dep!r}')
                elif not is_valid_tilde_dep(dep):
                    errors.append(f'project.dependencies entry invalid (not tilde/patch-0): {dep!r}')

    # Validate dependency-groups (staging and prod)
    if isinstance(dep_groups, dict):
        for group in ('staging', 'prod'):
            group_deps = dep_groups.get(group)
            if not isinstance(group_deps, list):
                errors.append(f'dependency-groups.{group} missing or not a list.')
            else:
                for dep in group_deps:
                    if not isinstance(dep, str):
                        errors.append(f'dependency-groups.{group} entry is not a string: {dep!r}')
                    elif not is_valid_tilde_dep(dep):
                        errors.append(f'dependency-groups.{group} entry invalid (not tilde/patch-0): {dep!r}')
    return errors

def run_toml_check() -> None:
    data = load_toml_file('pyproject.toml')
    errors = validate_pyproject(data)
    if errors:
        print('Validation errors:')
        for err in errors:
            print(f'- {err}')
    else:
        print('pyproject.toml is valid!')

if __name__ == '__main__':
    run_toml_check()
