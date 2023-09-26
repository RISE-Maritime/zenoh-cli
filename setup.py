import os

from setuptools import setup


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="zenoh-cli",
    version="0.1.0",
    license="Apache License 2.0",
    description="CLI for Zenoh",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    url="https://github.com/MO-RISE/zenoh-cli",
    author="Fredrik Olsson",
    author_email="fredrik.x.olsson@ri.se",
    maintainer="Fredrik Olsson",
    maintainer_email="fredrik.x.olsson@ri.se",
    py_modules=["zenoh_cli"],
    entry_points={
        "console_scripts": [
            "zenoh=zenoh_cli:main",
        ],
    },
    python_requires=">=3.8",
    install_requires=["eclipse-zenoh==0.7.2-rc", "parse"],
)
