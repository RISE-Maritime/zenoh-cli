# zenoh-cli
A command line tool for publishing, subscribing and getting from a Zenoh session

Use cases:
* Trials
* As part of a bash pipeline

## Installation
`pip install zenoh-cli`

## Usage
```cmd
usage: zenoh [-h] [--mode {peer,client}] [--connect CONNECT] [--listen LISTEN] [--config CONFIG] [--log-level LOG_LEVEL] {info,network,scout,delete,put,subscribe,get} ...

Zenoh command-line client application

positional arguments:
  {info,network,scout,delete,put,subscribe,get}

options:
  -h, --help            show this help message and exit
  --mode {peer,client}
  --connect CONNECT     Endpoints to connect to. (default: None)
  --listen LISTEN       Endpoints to listen on. (default: None)
  --config CONFIG       A path to a configuration file. (default: None)
  --log-level LOG_LEVEL
```

## Extending with codecs for encoding/decoding values

`zenoh-cli` comes with a plugin system for easily extending it with custom encoders and decoders (codecs) for the data values. The plugin system makes use of the entrypoints provided by setuptools, see [here](https://setuptools.pypa.io/en/latest/userguide/entry_point.html) for details. `zenoh-cli` gather plugins from two custom "groups":

* `zenoh-cli.codecs.encoders`
* `zenoh-cli.codecs.decoders`

For an example, see [example_plugin](./example_plugin/)
