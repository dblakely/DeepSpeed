"""
Copyright 2020 The Microsoft DeepSpeed Team

DeepSpeed library

Create a new wheel via the following command: python setup.py bdist_wheel

The wheel will be located at: dist/*.whl
"""

import os
import torch
import shutil
import subprocess
import warnings
from setuptools import setup, find_packages
from torch.utils.cpp_extension import CUDAExtension, BuildExtension, CppExtension

import op_builder


def fetch_requirements(path):
    with open(path, 'r') as fd:
        return [r.strip() for r in fd.readlines()]


install_requires = fetch_requirements('requirements/requirements.txt')
extras_require = {
    '1bit_adam': fetch_requirements('requirements/requirements-1bit-adam.txt'),
    'readthedocs': fetch_requirements('requirements/requirements-readthedocs.txt'),
    'dev': fetch_requirements('requirements/requirements-dev.txt'),
}

# If MPI is available add 1bit-adam requirements
if torch.cuda.is_available():
    if shutil.which('ompi_info') or shutil.which('mpiname'):
        cupy = f"cupy-cuda{torch.version.cuda.replace('.','')[:3]}"
        extras_require['1bit_adam'].append(cupy)

# Make an [all] extra that installs all needed dependencies
all_extras = set()
for extra in extras_require.items():
    for req in extra[1]:
        all_extras.add(req)
extras_require['all'] = list(all_extras)

cmdclass = {}

# For any pre-installed ops force disable ninja
cmdclass['build_ext'] = BuildExtension.with_options(use_ninja=False)

TORCH_MAJOR = torch.__version__.split('.')[0]
TORCH_MINOR = torch.__version__.split('.')[1]

if not torch.cuda.is_available():
    # Fix to allow docker buils, similar to https://github.com/NVIDIA/apex/issues/486
    print(
        "[WARNING] Torch did not find cuda available, if cross-compling or running with cpu only "
        "you can ignore this message. Adding compute capability for Pascal, Volta, and Turing "
        "(compute capabilities 6.0, 6.1, 6.2)")
    if os.environ.get("TORCH_CUDA_ARCH_LIST", None) is None:
        os.environ["TORCH_CUDA_ARCH_LIST"] = "6.0;6.1;6.2;7.0;7.5"

ext_modules = []

from op_builder import ALL_OPS

# Default to pre-install kernels to false so we rely on JIT
BUILD_OP_DEFAULT = int(os.environ.get('DS_BUILD_OPS', 0))
print(f"DS_BUILD_OPS={BUILD_OP_DEFAULT}")


def command_exists(cmd):
    result = subprocess.Popen(f'type {cmd}', stdout=subprocess.PIPE, shell=True)
    return result.wait() == 0


def op_enabled(op_name):
    assert hasattr(ALL_OPS[op_name], 'BUILD_VAR'), \
        f"{op_name} is missing BUILD_VAR field"
    env_var = ALL_OPS[op_name].BUILD_VAR
    return int(os.environ.get(env_var, BUILD_OP_DEFAULT))


install_ops = dict.fromkeys(ALL_OPS.keys(), False)
for op_name in ALL_OPS.keys():
    # Is op disabled from environment variable
    if op_enabled(op_name):
        builder = ALL_OPS[op_name]
        # Is op compatible with machine arch/deps
        if builder.is_compatible():
            install_ops[op_name] = op_enabled(op_name)
            ext_modules.append(builder.builder())
            # Add any necessary python requirements for this op
            install_requires += builder.python_requirements()

compatible_ops = {op_name: op.is_compatible() for (op_name, op) in ALL_OPS.items()}

print(f'Install Ops={install_ops}')

# Write out version/git info
git_hash_cmd = "git rev-parse --short HEAD"
git_branch_cmd = "git rev-parse --abbrev-ref HEAD"
if command_exists('git'):
    result = subprocess.check_output(git_hash_cmd, shell=True)
    git_hash = result.decode('utf-8').strip()
    result = subprocess.check_output(git_branch_cmd, shell=True)
    git_branch = result.decode('utf-8').strip()
else:
    git_hash = "unknown"
    git_branch = "unknown"

# Parse the DeepSpeed version string from version.txt
version_str = open('version.txt', 'r').read().strip()

# Build specifiers like .devX can be added at install time. Otherwise, add the git hash.
# example: DS_BUILD_STR=".dev20201022" python setup.py sdist bdist_wheel
version_str += os.environ.get('DS_BUILD_STRING', f'+{git_hash}')

torch_version = ".".join([TORCH_MAJOR, TORCH_MINOR])
cuda_version = ".".join(torch.version.cuda.split('.')[:2])
torch_info = {"version": torch_version, "cuda_version": cuda_version}

print(f"version={version_str}, git_hash={git_hash}, git_branch={git_branch}")
with open('deepspeed/git_version_info_installed.py', 'w') as fd:
    fd.write(f"version='{version_str}'\n")
    fd.write(f"git_hash='{git_hash}'\n")
    fd.write(f"git_branch='{git_branch}'\n")
    fd.write(f"installed_ops={install_ops}\n")
    fd.write(f"compatible_ops={compatible_ops}\n")
    fd.write(f"torch_info={torch_info}\n")

print(f'install_requires={install_requires}')
print(f'compatible_ops={compatible_ops}')
print(f'ext_modules={ext_modules}')

setup(name='deepspeed',
      version=version_str,
      description='DeepSpeed library',
      author='DeepSpeed Team',
      author_email='deepspeed@microsoft.com',
      url='http://deepspeed.ai',
      install_requires=install_requires,
      extras_require=extras_require,
      packages=find_packages(exclude=["docker",
                                      "third_party"]),
      include_package_data=True,
      scripts=[
          'bin/deepspeed',
          'bin/deepspeed.pt',
          'bin/ds',
          'bin/ds_ssh',
          'bin/ds_report'
      ],
      classifiers=[
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8'
      ],
      license='MIT',
      ext_modules=ext_modules,
      cmdclass=cmdclass)
