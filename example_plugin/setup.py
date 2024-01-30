from setuptools import setup

setup(
    name="example-plugin",
    py_modules=["example"],
    entry_points={
        "zenoh-cli.codecs.encoders": ["example = example:example_encoder"],
        "zenoh-cli.codecs.decoders": ["example = example:example_decoder"],
    },
)
