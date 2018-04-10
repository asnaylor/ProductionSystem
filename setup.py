"""Setuptools Module."""
from setuptools import setup, find_packages

setup(
    name="productionsystem",
    version="0.1",
    packages=find_packages(),
    install_requires=['CherryPy',
                      'daemonize',
                      'enum34',
                      'requests',
                      'SQLAlchemy',
                      'Sphinx',
                      ],
    tests_require=["mock", 'pylint', 'coverage'],
    test_suit="test.*",
    entry_points={
        'WebApp': ['basic = productionsystem.webapp.WebApp']
    },
    # metadata for upload to PyPI
    author="Alexander Richards",
    author_email="a.richards@imperial.ac.uk",
    description="Production System",
    license="MIT",
    keywords="production",
    url="https://github.com/alexanderrichards/ProductionSystem"
)