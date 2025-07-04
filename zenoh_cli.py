"""Main entrypoint for this application"""

import sys
import json
import time
import atexit
import logging
import os
import pathlib
import warnings
import argparse
from base64 import b64decode, b64encode
from typing import Dict, Callable
import threading

import zenoh
import parse
import networkx as nx


logger = logging.getLogger("zenoh-cli")


def info(
    session: zenoh.Session,
    config: zenoh.Config,
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
):
    info = session.info
    print(f"zid: {session.zid()}")
    print(f"routers: {info.routers_zid()}")
    print(f"peers: {info.peers_zid()}")


def scout(
    session: zenoh.Session,
    config: zenoh.Config,
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
):
    print("Scouting...")
    scout = zenoh.scout(what="peer|router")
    threading.Timer(1.0, lambda: scout.stop()).start()

    for hello in scout:
        print(hello)


def delete(
    session: zenoh.Session,
    config: zenoh.Config,
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
):
    for key in args.key:
        session.delete(key)


def put(
    session: zenoh.Session,
    config: zenoh.Config,
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
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
                    key_expr=key,
                    payload=value,
                    # encoding=args.encoding,
                    # priority=args.priority,
                    # congestion_control=args.congestion_control,
                )

            else:
                logger.error("Failed to parse line: %s", line)

    else:
        session.put(
            key_expr=args.key,
            payload=encoder(args.key, args.value),
            # encoding=args.encoding,
            # priority=args.priority,
            # congestion_control=args.congestion_control,
        )


def _print_sample_to_stdout(sample: zenoh.Sample, fmt: str, decoder: str):
    key = sample.key_expr
    payload = sample.payload.to_bytes()

    try:
        value = DECODERS[decoder](key, payload)
    except Exception:
        logger.exception("Decoder (%s) failed, skipping!", decoder)
        return

    sys.stdout.write(fmt.format(key=key, value=value).rstrip())
    sys.stdout.write("\n")
    sys.stdout.flush()


def get(
    session: zenoh.Session,
    config: zenoh.Config,
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
):
    encoder = ENCODERS[args.encoder]

    for response in session.get(
        args.selector,
        payload=encoder(args.selector, args.value) if args.value is not None else None,
    ):
        if response.ok:
            _print_sample_to_stdout(response.ok, args.line, args.decoder)
        else:
            logger.error(
                "Received error (%s) on get(%s)",
                response.err.payload.to_bytes(),
                args.selector,
            )


def subscribe(
    session: zenoh.Session,
    config: zenoh.Config,
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
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
    session: zenoh.Session,
    config: zenoh.Config,
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
):
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    from jsonpointer import resolve_pointer

    graph = nx.Graph()

    me = str(session.info.zid())
    graph.add_node(me, whatami=config.get_json("mode"))

    # Scout the nearby network
    scout = zenoh.scout(what="peer|router")
    threading.Timer(1.0, lambda: scout.stop()).start()

    for answer in scout:
        logging.debug("Scout answer: %s", answer)
        logging.debug("Scout answer zid: %s", answer.zid)
        logging.debug("Scout answer whatami: %s", answer.whatami)

        graph.add_node(str(answer.zid), whatami=str(answer.whatami))

    # Query routers for more information
    for response in session.get("@/*/router"):
        if response.ok:
            logging.debug("Received router response: %s", response.ok.payload)
            data = json.loads(response.ok.payload.to_string())

            # Start adding edges and nodes
            zid = data["zid"]
            metadata = data["metadata"]
            graph.add_node(zid, whatami="router", metadata=metadata)
            for sess in data["sessions"]:
                peer = sess["peer"]
                whatami = sess["whatami"]

                try:
                    # Zenohd >= 1.4.0
                    link_protocols = ",".join(
                        [link["src"].split("/")[0] for link in sess["links"]]
                    )
                except TypeError:
                    # Zenohd < 1.4.0
                    link_protocols = ",".join(
                        [link.split("/")[0] for link in sess["links"]]
                    )

                graph.add_node(peer, whatami=whatami)
                graph.add_edge(zid, peer, protocol=link_protocols)

        else:
            logger.error(
                "Received error (%s)",
                response.err.payload.to_bytes(),
            )
            pass

    pos = nx.spring_layout(graph, seed=3113794652)

    # Nodes
    routers = [
        node for node, attrs in graph.nodes.items() if attrs["whatami"] == "router"
    ]
    peers = [node for node, attrs in graph.nodes.items() if attrs["whatami"] == "peer"]
    clients = [
        node for node, attrs in graph.nodes.items() if attrs["whatami"] == "client"
    ]

    info = session.info

    me = str(info.zid())

    # Node labels
    labels = {
        zid: resolve_pointer(attributes, f"/metadata{args.metadata_field}", zid[:5])
        for zid, attributes in graph.nodes(data=True)
    }
    labels[me] = "Me!"

    nx.draw_networkx(
        graph,
        pos,
        nodelist=routers,
        edgelist=[],
        node_color="steelblue",
        node_size=500,
        with_labels=False,
    )
    nx.draw_networkx(
        graph,
        pos,
        nodelist=peers,
        edgelist=[],
        node_color="aliceblue",
        with_labels=False,
    )
    nx.draw_networkx(
        graph,
        pos,
        nodelist=clients,
        edgelist=[],
        node_color="Lightgreen",
        with_labels=False,
    )

    nx.draw_networkx(
        graph,
        pos,
        nodelist=[me],
        edgelist=[],
        node_color="lightcoral",
        with_labels=False,
    )

    nx.draw_networkx_labels(
        graph, pos, labels, font_color="darkgrey", font_weight="bold"
    )

    # Edges
    nx.draw_networkx(
        graph,
        pos,
        nodelist=[],
        edge_color="white",
        with_labels=False,
    )
    nx.draw_networkx_edge_labels(
        graph,
        pos,
        edge_labels=nx.get_edge_attributes(graph, "protocol"),
        rotate=False,
        font_color="black",
    )
    plt.tight_layout()
    plt.axis("off")

    if not args.save_fig:
        plt.show()
        return

    output_file = "zenoh_network.png"
    plt.gcf().set_size_inches(10, 10)
    plt.savefig(output_file)
    plt.close()
    print(f"Network visualization saved to {os.path.abspath(output_file)}")


# Bundled codecs


# Text codec
def encode_from_text(key: str, value: str) -> bytes:
    return value.encode()


def decode_to_text(key: str, value: bytes) -> str:
    return value.decode()


# Base64 codec
def encode_from_base64(key: str, value: str) -> bytes:
    return b64decode(value.encode())


def decode_to_base64(key: str, value: bytes) -> str:
    return b64encode(value).decode()


# JSON codec
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


# Plugin handling
def gather_plugins():
    # NOTE: Python 3.8.x-3.9.x doesn't support the `group` keyword argument in
    # entry_points, in that case we fallback to `importlib_metadata`.
    if sys.version_info.minor >= 10:
        from importlib.metadata import entry_points
    else:
        logger.debug(
            "Falling back to importlib_metadata backport for python versions lower than 3.10"
        )
        from importlib_metadata import entry_points

    encoder_plugins = entry_points(group="zenoh_cli.codecs.encoders")
    decoder_plugins = entry_points(group="zenoh_cli.codecs.decoders")

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


# Entrypoint
def main():
    plugin_encoders, plugin_decoders = gather_plugins()

    parser = argparse.ArgumentParser(
        prog="zenoh",
        description="Zenoh command-line client application",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=["peer", "client", "router"],
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

    parser.add_argument(
        "--cfg",
        action="append",
        type=str,
        default=[],
        help="Configuration option according to 'PATH:VALUE'",
    )

    parser.add_argument(
        "--log-level",
        type=int,
        default=30,
        help="Log level: 10=DEBUG, 20=INFO, 30=WARNING, 40=ERROR, 50=CRITICAL 0=NOTSET",
    )

    # Subcommands
    subparsers = parser.add_subparsers(required=True)

    # Info subcommand
    info_parser = subparsers.add_parser("info")
    info_parser.set_defaults(func=info)

    # Network subcommand
    network_parser = subparsers.add_parser("network")
    network_parser.set_defaults(func=network)
    network_parser.add_argument(
        "--metadata-field",
        type=str,
        default="/name",
        help="JSON pointer to a field in a routers metadata configuration",
    )
    network_parser.add_argument(
        "--save-fig",
        action="store_true",
        help="Save the network visualization to a file instead of displaying it",
    )

    # Scout subcommand
    scout_parser = subparsers.add_parser("scout")
    scout_parser.add_argument("-w", "--what", type=str, default="peer|router")
    scout_parser.add_argument("-t", "--timeout", type=float, default=1.0)
    scout_parser.set_defaults(func=scout)

    # Delete subcommand
    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("-k", "--key", type=str, action="append", required=True)
    delete_parser.set_defaults(func=delete)

    # Common parser for all subcommands
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

    # Put subcommand
    put_parser = subparsers.add_parser("put", parents=[common_parser])
    put_parser.add_argument("-k", "--key", type=str, default=None)
    put_parser.add_argument("-v", "--value", type=str, default=None)
    put_parser.add_argument("--line", type=str, default=None)
    put_parser.set_defaults(func=put)

    # Subscribe subcommand
    subscribe_parser = subparsers.add_parser("subscribe", parents=[common_parser])
    subscribe_parser.add_argument(
        "-k", "--key", type=str, action="append", required=True
    )
    subscribe_parser.add_argument("--line", type=str, default="{value}")
    subscribe_parser.set_defaults(func=subscribe)

    # Get subcommand
    get_parser = subparsers.add_parser("get", parents=[common_parser])
    get_parser.add_argument("-s", "--selector", type=str, required=True)
    get_parser.add_argument("-v", "--value", type=str, default=None)
    get_parser.add_argument("--line", type=str, default="{value}")
    get_parser.set_defaults(func=get)

    # Parse arguments and start doing our thing
    args = parser.parse_args()

    # Setup logger
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=args.log_level
    )
    logging.captureWarnings(True)
    warnings.filterwarnings("once")

    zenoh.init_log_from_env_or("error")

    # Load the plugins
    load_plugins(plugin_encoders, plugin_decoders)

    # Put together zenoh session configuration
    conf = (
        zenoh.Config.from_file(str(args.config))
        if args.config is not None
        else zenoh.Config()
    )
    if args.mode is not None:
        conf.insert_json5("mode", json.dumps(args.mode))
    if args.connect is not None:
        conf.insert_json5("connect/endpoints", json.dumps(args.connect))
    if args.listen is not None:
        conf.insert_json5("listen/endpoints", json.dumps(args.listen))

    for config_option in args.cfg:
        path, value = config_option.split(":", maxsplit=1)
        logger.info("Configuring with PATH=%s, VALUE=%s", path, value)
        try:
            conf.insert_json5(path, value)
        except:
            conf.insert_json5(path, json.dumps(value))

    # Construct session
    logger.info("Opening Zenoh session...")
    with zenoh.open(conf) as session:
        # Dispatch to correct function
        try:
            args.func(session, conf, parser, args)
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    main()
