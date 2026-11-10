import argparse
from dataclasses import asdict
import json
import sys

from .client import OfflineClient
from .bootstrap import RobloxBootstrap, read_credential
from .lab import run_demo
from .protocol import decode
from .probe import probe_endpoint


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimental standalone Roblox transport and character initialization.")
    commands = parser.add_subparsers(dest="command", required=True)
    gui = commands.add_parser('gui', help='Open the lightweight scanner window')
    gui.add_argument('--config', default=None)
    gui.add_argument('--cookies', default=None)
    commands.add_parser("demo", help="Run a local UDP exchange against the lab fixture")
    negotiate = commands.add_parser("negotiate", help="Try offline negotiation with one explicit IPv4 peer")
    negotiate.add_argument("host", help="Numeric IPv4 address")
    negotiate.add_argument("port", type=int)
    negotiate.add_argument("--protocol", type=int, required=True, help="Explicit RakNet version; no Roblox default is assumed")
    negotiate.add_argument("--mtu", type=int, default=1200)
    negotiate.add_argument("--timeout", type=float, default=2)
    inspect = commands.add_parser("inspect", help="Decode one offline packet from hexadecimal without network access")
    inspect.add_argument("hex_payload")
    for name, help_text in (
        ("login", "Verify your web session only; does not join an experience"),
        ("bootstrap", "Request authenticated connection info; does not establish a game session"),
        ("probe", "Bootstrap and send two credential-free UDP diagnostics; does not join the game"),
        ("native-open", "Try recovered RbxOpenRequest1/2 in sequence; does not join or spawn a player"),
        ("connect", "Run encrypted transport; character stage initializes and verifies your avatar"),
    ):
        auth = commands.add_parser(name, help=help_text)
        source = auth.add_mutually_exclusive_group()
        source.add_argument("--cookie-env", metavar="NAME", help="Read only this explicitly named environment variable; default is hidden local input")
        source.add_argument("--cookie-file", metavar="PATH", help="Read the explicitly selected local UTF-8 session file without displaying it")
        if name == 'connect':
            source.add_argument('--mass-cookie-file', metavar='COUNT', type=int,
                                help='Launch COUNT unique cookies from cookies.txt in a shared interactive console')
            auth.add_argument('--mass-cookies-path', metavar='PATH', default='cookies.txt',
                              help='Optional alternate file for --mass-cookie-file COUNT')
        if name in ("bootstrap", "probe", "native-open", "connect"):
            destination = auth.add_mutually_exclusive_group()
            destination.add_argument("--place-id", type=int, help="Public game Place ID (default: 2336379484)")
            destination.add_argument('--vip-link', '--private-server-link', metavar='URL',
                                     help='Roblox private-server invitation URL; quote the complete URL')
            if name == 'connect':
                destination.add_argument('--brainrot', action='store_true',
                    help='Compact overhead scanner in place 109983668079237; requires --mass-cookie-file COUNT')
            auth.add_argument("--attempts", type=int, default=3)
        if name == "connect":
            auth.add_argument('--only-best', action='store_true',
                help='With --brainrot: report one BEST after initial scan, then join a new public server')
            auth.add_argument('--scan-workers', type=int, default=None, metavar='COUNT',
                help='With --brainrot --only-best: persistent account scanners (default 4); remaining cookies stay on standby')
            auth.add_argument('--scan-processes', type=int, default=None, metavar='COUNT',
                help='With --only-best: Python process groups (automatic up to 8); several accounts share each process')
            auth.add_argument('--scan-inflight', type=int, default=None, metavar='COUNT',
                help='With --only-best: maximum simultaneous world downloads (automatic based on process groups)')
            auth.add_argument('--scan-timeout', type=float, default=None, metavar='SECONDS',
                help='With --only-best: first join and scan budget, 1..75 seconds (default 4)')
            auth.add_argument('--scan-hop-timeout', type=float, default=None, metavar='SECONDS',
                help='With --only-best: subsequent join and scan budget, 1..75 seconds (default 3)')
            auth.add_argument('--scan-status', action='store_true',
                default=None,
                help='With --only-best: show progress every five seconds and skipped-server reasons')
            auth.add_argument('--scan-strict-timeouts', action='store_true',
                default=None,
                help='With --only-best: disable adaptive 20-second recovery after repeated short scan timeouts')
            auth.add_argument('--config', metavar='PATH', default=None,
                help='With --only-best: UTF-8 JSON settings and featured_pets (default config.txt beside rakbot)')
            auth.add_argument("--duration", type=float, default=None)
            auth.add_argument("--interactive", action="store_true",
                              help="Enable character stage and terminal commands; runs until quit unless duration is set")
            auth.add_argument("--application-stage", choices=("transport", "metadata", "ticket", "character"),
                              default="transport", help="character: isolated VM, replication, spawn request and Heli-Wars team selection")
    args = parser.parse_args()
    if args.command == 'gui':
        from .gui import main as gui_main
        return gui_main(config_path=args.config, cookies_path=args.cookies)
    if args.command == 'connect' and args.only_best and not args.brainrot:
        parser.error('--only-best requires --brainrot and --mass-cookie-file COUNT')
    if args.command == 'connect' and args.config is not None and not args.only_best:
        parser.error('--config requires --brainrot --only-best')
    if args.command == 'connect' and args.scan_workers is not None and not args.only_best:
        parser.error('--scan-workers requires --brainrot --only-best')
    if args.command == 'connect' and args.scan_workers is not None and args.scan_workers < 1:
        parser.error('--scan-workers must be a positive integer')
    if args.command == 'connect' and args.scan_processes is not None and not args.only_best:
        parser.error('--scan-processes requires --brainrot --only-best')
    if args.command == 'connect' and args.scan_processes is not None and args.scan_processes < 1:
        parser.error('--scan-processes must be a positive integer')
    if args.command == 'connect' and args.scan_inflight is not None and (not args.only_best or args.scan_inflight < 1):
        parser.error('--scan-inflight requires --brainrot --only-best and a positive integer')
    if args.command == 'connect' and args.scan_status and not args.only_best:
        parser.error('--scan-status requires --brainrot --only-best')
    if args.command == 'connect' and args.scan_strict_timeouts and not args.only_best:
        parser.error('--scan-strict-timeouts requires --brainrot --only-best')
    if args.command == 'connect' and args.scan_timeout is not None and not args.only_best:
        parser.error('--scan-timeout requires --brainrot --only-best')
    if args.command == 'connect' and args.scan_hop_timeout is not None and not args.only_best:
        parser.error('--scan-hop-timeout requires --brainrot --only-best')
    if args.command == 'connect' and args.brainrot:
        if args.mass_cookie_file is None:
            parser.error('--brainrot requires --mass-cookie-file COUNT')
        from .brainrot import PLACE_ID
        args.place_id = PLACE_ID
    if hasattr(args, 'place_id') and args.place_id is None and args.vip_link is None:
        args.place_id = 2336379484
    try:
        if args.command == 'connect' and args.mass_cookie_file is not None:
            from .mass import run_mass
            output, code = run_mass(args)
            if not args.brainrot:
                print(json.dumps(output, indent=2))
            return code
        if args.command in ("login", "bootstrap", "probe", "native-open", "connect"):
            auth = RobloxBootstrap(read_credential(args.cookie_env, args.cookie_file))
            if args.command == "login":
                output = auth.authenticate().summary()
            else:
                info = (auth.prepare_vip(args.vip_link, attempts=args.attempts) if args.vip_link
                        else auth.prepare(args.place_id, attempts=args.attempts))
                output = info.summary()
                if args.command == "probe":
                    output["transport_fields"] = info.transport_fields()
                    output["udp"] = probe_endpoint(*info.endpoints[0])
                elif args.command == "native-open":
                    from .native_open import attempt_native_open
                    output["native_open"] = attempt_native_open(info)
                elif args.command == "connect":
                    from .native_client import NativeClient
                    console = None
                    def emit(message):
                        if console is not None:
                            console.emit(message)
                        else:
                            print(message, file=sys.stderr, flush=True)
                    def show_player(player):
                        emit("player: " + json.dumps(player, ensure_ascii=True))
                    if args.interactive:
                        args.application_stage = 'character'
                    if args.application_stage == "character":
                        from .game_client import GameClient
                        from .console import Console
                        from contextlib import nullcontext
                        def show_character(character):
                            emit("character: " + json.dumps(character))
                        def show_command(result):
                            emit('command: ' + json.dumps(result, ensure_ascii=False))
                        with (Console(sys.stdin) if args.interactive else nullcontext()) as console:
                            client = GameClient(info, on_player=show_player, on_character=show_character,
                                                commands=console.commands if console else None,
                                                on_command=show_command)
                            if args.interactive:
                                emit('interactive: commands: help, players, status, where [username], teleport username, looptp username, stoploop, chat text, quit')
                            duration = args.duration if args.duration is not None else (None if args.interactive else 40)
                            output["connected"] = client.run(duration=duration)
                    else:
                        client = NativeClient(info, application_stage=args.application_stage, on_player=show_player)
                        output["connected"] = client.run(duration=args.duration if args.duration is not None else 15)
                    if args.application_stage == "character":
                        output.update(state=output["connected"]["state"],
                                      game_session=output["connected"]["game_session"],
                                      note=output["connected"]["note"])
        elif args.command == "inspect":
            packet = decode(bytes.fromhex(args.hex_payload))
            output = {"type": type(packet).__name__, **asdict(packet)}
        else:
            if args.command == "demo":
                result = run_demo()
            else:
                client = OfflineClient(protocol=args.protocol, mtu=args.mtu, timeout=args.timeout,
                                       on_state=lambda state: print(f"state: {state}", file=sys.stderr))
                result = client.negotiate(args.host, args.port)
            output = {**asdict(result), "roblox_session": False,
                      "note": "Offline RakNet negotiation only; no connected session or Roblox login."}
        print(json.dumps(output, indent=2))
        if args.command == "connect" and output["connected"]["state"].endswith("_rejected"):
            return 2
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

