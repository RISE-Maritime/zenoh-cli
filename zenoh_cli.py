"""Main entrypoint for this application"""

import sys
import json
import time
import atexit
import logging
import pathlib
import warnings
import argparse
from base64 import b64decode, b64encode
from typing import Dict, Callable

import zenoh
import parse
import networkx as nx


logger = logging.getLogger("zenoh-cli")


def info(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    info = session.info()
    logger.info(f"zid: {info.zid()}")
    logger.info(f"routers: {info.routers_zid()}")
    logger.info(f"peers: {info.peers_zid()}")


def scout(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    result = zenoh.scout(what=args.what, timeout=args.timeout)
    for received in result.receiver():
        logger.info(received)


def delete(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    for key in args.key:
        session.delete(key)


def put(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    # Validation
    if pattern := args.line:
        if "key" not in pattern and not args.key:
            parser.error(
                "A key must be specified either on the command line or as a pattern parameter."
            )
        elif "value" not in pattern and not args.value:
            parser.error(
                "A value must be specified either on the command line or as a pattern parameter."
            )
    else:
        if not args.key or not args.value:
            parser.error("A topic and a value must be specified on the command line.")

    encoder = ENCODERS[args.encoder]

    if pattern := args.line:
        line_parser = parse.compile(pattern)

        for line in sys.stdin:
            if result := line_parser.parse(line):
                key = args.key or result["key"]
                value = args.value or result["value"]
                try:
                    value = encoder(key, value)
                except Exception:
                    logger.exception("Encoder (%s) failed, skipping!", args.encoder)
                    continue

                session.put(
                    keyexpr=key,
                    value=value,
                    # encoding=args.encoding,
                    # priority=args.priority,
                    # congestion_control=args.congestion_control,
                )

            else:
                logger.error("Failed to parse line: %s", line)

    else:
        session.put(
            keyexpr=args.key,
            value=encoder(args.key, args.value),
            # encoding=args.encoding,
            # priority=args.priority,
            # congestion_control=args.congestion_control,
        )


def _print_sample_to_stdout(sample: zenoh.Sample, fmt: str, decoder: str):
    key = sample.key_expr
    payload = sample.value.payload

    try:
        value = DECODERS[decoder](key, payload)
    except Exception:
        logger.exception("Decoder (%s) failed, skipping!", decoder)
        return

    sys.stdout.write(f"{fmt.format(key=key, value=value)}\n")
    sys.stdout.flush()


def get(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    for response in session.get(args.selector, zenoh.Queue()):
        try:
            reply = response.ok
            _print_sample_to_stdout(reply, args.line, args.decoder)
        except Exception:
            logger.error(
                "Received error (%s) on get(%s)",
                reply.err.payload.decode(),
                args.selector,
            )


def subscribe(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    def listener(sample: zenoh.Sample):
        """Print received samples to stdout according to specified format"""
        _print_sample_to_stdout(sample, args.line, args.decoder)

    subscribers = [session.declare_subscriber(key, listener) for key in args.key]

    while True:
        try:
            time.sleep(0.1)
        except KeyboardInterrupt:
            sys.exit(0)


def network(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    graph = nx.Graph()

    for response in session.get("@/router/*", zenoh.Queue()):
        try:
            reply = response.ok
            data = json.loads(reply.payload)

            # Start adding edges and nodes
            zid = data["zid"]
            for sess in data["sessions"]:
                peer = sess["peer"]
                whatami = sess["whatami"]
                link_protocols = ",".join(
                    [link.split("/")[0] for link in sess["links"]]
                )
                graph.add_node(peer, whatami=whatami)
                graph.add_edge(zid, peer, protocol=link_protocols)

        except Exception:
            logger.error(
                "Received error (%s) on get(%s)",
                reply.err.payload.decode(),
                args.selector,
            )

    pos = nx.spring_layout(graph)
    nx.draw_networkx(graph, pos, labels=nx.get_node_attributes(graph, "whatami"))
    nx.draw_networkx_edge_labels(
        graph, pos, edge_labels=nx.get_edge_attributes(graph, "protocol"), rotate=False
    )

    import matplotlib.pyplot as plt

    plt.show()


## Bundled codecs


### Text codec
def encode_from_text(key: str, value: str) -> bytes:
    return value.encode()


def decode_to_text(key: str, value: bytes) -> str:
    return value.decode()


### Base64 codec
def encode_from_base64(key: str, value: str) -> bytes:
    return b64decode(value.encode())


def decode_to_base64(key: str, value: bytes) -> str:
    return b64encode(value).decode()


### JSON codec
def encode_from_json(key: str, value: str) -> bytes:
    return encode_from_text(key, value)


def decode_to_json(key: str, value: bytes) -> str:
    # Makes sure the json is on a single line
    return json.dumps(json.loads(value))


ENCODERS: Dict[str, Callable] = {
    "text": encode_from_text,
    "base64": encode_from_base64,
    "json": encode_from_json,
}

DECODERS: Dict[str, Callable] = {
    "text": decode_to_text,
    "base64": decode_to_base64,
    "json": decode_to_json,
}


## Plugin handling
def gather_plugins():
    try:
        from importlib.metadata import entry_points
    except Exception as exc:
        logger.debug(
            "Falling back to importlib_metadata backport for python versions lower than 3.10"
        )
        from importlib_metadata import entry_points

    encoder_plugins = entry_points(group="zenoh-cli.codecs.encoders")
    decoder_plugins = entry_points(group="zenoh-cli.codecs.decoders")

    plugin_encoders = {}
    plugin_decoders = {}

    for plugin in encoder_plugins:
        plugin_encoders[plugin.name] = plugin

    for plugin in decoder_plugins:
        plugin_decoders[plugin.name] = plugin

    return plugin_encoders, plugin_decoders


def load_plugins(plugin_encoders, plugin_decoders):
    for name, plugin in plugin_encoders.items():
        try:
            ENCODERS[name] = plugin.load()
        except Exception:
            logger.exception("Failed to load encoder plugin with name: %s", name)

    for name, plugin in plugin_decoders.items():
        try:
            DECODERS[name] = plugin.load()
        except Exception:
            logger.exception("Failed to load decoder plugin with name: %s", name)


## Entrypoint
def main():
    plugin_encoders, plugin_decoders = gather_plugins()

    parser = argparse.ArgumentParser(
        prog="zenoh",
        description="Zenoh command-line client application",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=["peer", "client"],
        default="peer",
        type=str,
    )
    parser.add_argument(
        "--connect",
        action="append",
        type=str,
        help="Endpoints to connect to.",
    )
    parser.add_argument(
        "--listen",
        action="append",
        type=str,
        help="Endpoints to listen on.",
    )

    parser.add_argument(
        "--config",
        type=pathlib.Path,
        help="A path to a configuration file.",
    )
    parser.add_argument("--log-level", type=int, default=logging.INFO)

    ## Subcommands
    subparsers = parser.add_subparsers(required=True)

    ## Info subcommand
    info_parser = subparsers.add_parser("info")
    info_parser.set_defaults(func=info)

    ## Graph subcommand
    network_parser = subparsers.add_parser("network")
    network_parser.set_defaults(func=network)

    ## Scout subcommand
    scout_parser = subparsers.add_parser("scout")
    scout_parser.add_argument("-w", "--what", type=str, default="peer|router")
    scout_parser.add_argument("-t", "--timeout", type=float, default=1.0)
    scout_parser.set_defaults(func=scout)

    ## Delete subcommand
    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("-k", "--key", type=str, action="append", required=True)
    delete_parser.set_defaults(func=delete)

    ## Common parser for all subcommands
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--encoder",
        choices=list(ENCODERS.keys()) + list(plugin_encoders.keys()),
        default="text",
    )
    common_parser.add_argument(
        "--decoder",
        choices=list(DECODERS.keys()) + list(plugin_decoders.keys()),
        default="base64",
    )

    ## Put subcommand
    put_parser = subparsers.add_parser("put", parents=[common_parser])
    put_parser.add_argument("-k", "--key", type=str, default=None)
    put_parser.add_argument("-v", "--value", type=str, default=None)
    put_parser.add_argument("--line", type=str, default=None)
    put_parser.set_defaults(func=put)

    ## Subscribe subcommand
    subscribe_parser = subparsers.add_parser("subscribe", parents=[common_parser])
    subscribe_parser.add_argument(
        "-k", "--key", type=str, action="append", required=True
    )
    subscribe_parser.add_argument("--line", type=str, default="{value}")
    subscribe_parser.set_defaults(func=subscribe)

    ## Get subcommand
    get_parser = subparsers.add_parser("get", parents=[common_parser])
    get_parser.add_argument("-s", "--selector", type=str, required=True)
    get_parser.add_argument("--line", type=str, default="{value}")
    get_parser.set_defaults(func=get)

    ## Parse arguments and start doing our thing
    args = parser.parse_args()

    # Setup logger
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=args.log_level
    )
    logging.captureWarnings(True)
    warnings.filterwarnings("once")
    zenoh.init_logger()

    # Load the plugins
    load_plugins(plugin_encoders, plugin_decoders)

    # Put together zenoh session configuration
    conf = (
        zenoh.Config.from_file(str(args.config))
        if args.config is not None
        else zenoh.Config()
    )
    if args.mode is not None:
        conf.insert_json5(zenoh.config.MODE_KEY, json.dumps(args.mode))
    if args.connect is not None:
        conf.insert_json5(zenoh.config.CONNECT_KEY, json.dumps(args.connect))
    if args.listen is not None:
        conf.insert_json5(zenoh.config.LISTEN_KEY, json.dumps(args.listen))

    ## Construct session
    logger.info("Opening Zenoh session...")
    session = zenoh.open(conf)

    def _on_exit():
        session.close()

    atexit.register(_on_exit)

    # Dispatch to correct function
    try:
        args.func(session, parser, args)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
