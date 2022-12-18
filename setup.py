import os
from setuptools import setup
from setuptools import find_packages

def read_requirements():
    """Parse requirements from requirements.txt."""
    reqs_path = os.path.join('.', 'requirements.txt')
    with open(reqs_path, 'r') as f:
        requirements = [line.rstrip() for line in f]
    return requirements

setup(
    name='japanese personal name dataset',
    version='0.0.1',
    description='Japanese personal name dataset',
    install_requires=read_requirements(),
    author='shuheilocale',
    author_email='xxx@gmail.com',
    url='https://github.com/shuheilocale/japanese-personal-name-dataset',
    license='MIT License',
    packages=find_packages(exclude=('tests', 'docs')),
    test_suite='tests'
)