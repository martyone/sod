from setuptools import setup, find_packages

setup(
    name='sod',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'click',
        'pygit2',
        'pytest',
    ],
    entry_points='''
        [console_scripts]
        sod=sod.sod:cli
    ''',
)
