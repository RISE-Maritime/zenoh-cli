from setuptools import setup

setup(
    name="example-plugin",
    py_modules=["example"],
    entry_points={
        "zenoh-cli.codecs.encoders": [
            "example1 = example:example_encoder_1",
            "example2 = example:example_encoder_2",
        ],
        "zenoh-cli.codecs.decoders": [
            "example1 = example:example_decoder_1",
            "example2 = example:example_decoder_2",
        ],
    },
)
