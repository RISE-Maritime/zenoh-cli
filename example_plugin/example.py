def example_encoder(key, value):
    return f"From plugin: {value}".encode()


def example_decoder(key, value):
    return f"From plugin: {value}"
