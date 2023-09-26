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

from parse import compile
import zenoh

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
    for hello in result.receiver():
        logger.info(hello)


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
        elif "message" not in pattern and not args.message:
            parser.error(
                "A message must be specified either on the command line or as a pattern parameter."
            )
    else:
        if not args.key or not args.message:
            parser.error("A topic and a message must be specified on the command line.")

    if pattern := args.line:
        parser = compile(pattern)

        for line in sys.stdin:
            if result := parser.parse(line):
                key = args.key or result["key"]
                message = args.message or result["message"]
                session.put(
                    keyexpr=key,
                    value=b64decode(message) if args.base64 else message,
                    # encoding=args.encoding,
                    # priority=args.priority,
                    # congestion_control=args.congestion_control,
                )

            else:
                logger.error("Failed to parse line: %s", line)

    else:
        session.put(
            keyexpr=args.key,
            value=b64decode(args.message) if args.base64 else args.message,
            # encoding=args.encoding,
            # priority=args.priority,
            # congestion_control=args.congestion_control,
        )


def _print_sample_to_stdout(
    sample: zenoh.Sample, fmt: str, base64: bool = False, json: bool = False
):
    if base64:
        try:
            payload = b64encode(sample.value.payload)
        except TypeError:
            logger.exception(f"Could not b64encode payload: {sample.value.payload}")
            return
    else:
        payload = sample.value.payload

    try:
        payload = payload.decode()
    except UnicodeDecodeError:
        logger.exception(f"Could not decode payload: {payload}")
        return

    if json:
        try:
            payload = json.dumps(json.loads(payload))
        except json.JSONDecodeError:
            logger.exception(f"Could not decode payload as JSON: {payload}")
            return

    sys.stdout.write(f"{fmt.format(key=sample.key_expr, message=payload)}\n")
    sys.stdout.flush()


def get(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    for response in session.get(args.selector, zenoh.Queue()):
        if reply := response.ok:
            _print_sample_to_stdout(reply, args.line, args.base64, args.json)
        else:
            logger.error(
                "Received error (%s) on get(%s)",
                reply.err.payload.decode(),
                args.selector,
            )


def subscribe(
    session: zenoh.Session, parser: argparse.ArgumentParser, args: argparse.Namespace
):
    def listener(sample: zenoh.Sample):
        """Print received message to stdout according to specified format"""
        _print_sample_to_stdout(sample, args.line, args.base64, args.json)

    subscribers = [session.declare_subscriber(key, listener) for key in args.key]

    while True:
        try:
            time.sleep(0.1)
        except KeyboardInterrupt:
            sys.exit(0)


def main():
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
    common_parser.add_argument("--base64", action="store_true", default=False)

    ## Put subcommand
    put_parser = subparsers.add_parser("put", parents=[common_parser])
    put_parser.add_argument("-k", "--key", type=str, default=None)
    put_parser.add_argument("-m", "--message", type=str, default=None)
    put_parser.add_argument("--line", type=str, default=None)
    put_parser.set_defaults(func=put)

    ## Subscribe subcommand
    subscribe_parser = subparsers.add_parser("subscribe", parents=[common_parser])
    subscribe_parser.add_argument(
        "-k", "--key", type=str, action="append", required=True
    )
    subscribe_parser.add_argument("--line", type=str, default="{message}")
    subscribe_parser.add_argument("--json", action="store_true", default=False)
    subscribe_parser.set_defaults(func=subscribe)

    ## Get subcommand
    get_parser = subparsers.add_parser("get", parents=[common_parser])
    get_parser.add_argument("-s", "--selector", type=str, required=True)
    get_parser.add_argument("--line", type=str, default="{message}")
    get_parser.add_argument("--json", action="store_true", default=False)
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
