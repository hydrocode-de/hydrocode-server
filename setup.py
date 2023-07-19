from setuptools import setup, find_packages


def version():
    with open('hserv/__version__.py') as f:
        loc = dict()
        exec(f.read(), loc, loc)
        return loc['__version__']


def requirements():
    with open('requirements.txt') as f:
        return f.read().splitlines()


def readme():
    with open('README.md') as f:
        return f.read()


setup(
    name='hserv',
    version=version(),
    author='Mirko Mälicke',
    author_email='mirko@hydrocode.de',
    description='cli / api toolchain for managing hydrocode servers',
    long_description=readme(),
    long_description_content_type='text/markdown',
    install_requires=requirements(),
    packages=find_packages(),
)
