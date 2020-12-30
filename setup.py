from setuptools import setup

setup(
    name='sod',
    version='0.1',
    py_modules=['sod'],
    install_requires=[
        'click',
        'pygit2',
    ],
    entry_points='''
        [console_scripts]
        sod=sod:cli
    ''',
)
