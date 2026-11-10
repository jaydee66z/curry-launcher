"""Authenticated HTTPS bootstrap. This does not implement Roblox's game transport."""

from dataclasses import dataclass, field
import getpass
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from ipaddress import ip_address
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import warnings


IDENTITY_URL = "https://users.roblox.com/v1/users/authenticated"
JOIN_URL = "https://gamejoin.roblox.com/v1/join-game"
INSTANCE_JOIN_URL = 'https://gamejoin.roblox.com/v1/join-game-instance'
PRIVATE_JOIN_URL = "https://gamejoin.roblox.com/v1/join-private-game"
RESOLVE_LINK_URL = "https://apis.roblox.com/sharelinks/v1/resolve-link"
PLACE_DETAILS_PREFIX = "https://games.roblox.com/v1/games/multiget-place-details?placeIds="
ALLOWED_URLS = frozenset((IDENTITY_URL, JOIN_URL, INSTANCE_JOIN_URL, PRIVATE_JOIN_URL, RESOLVE_LINK_URL))
MAX_RESPONSE = 2 * 1024 * 1024


class BootstrapError(ValueError):
    """A diagnostic that never incorporates raw HTTP bodies or credentials."""


class NetworkUnavailable(BootstrapError):
    """Transient HTTPS transport failure, distinct from an account refusal."""


class RateLimited(BootstrapError):
    def __init__(self, retry_after=10):
        self.retry_after = retry_after
        super().__init__('Roblox temporarily rate-limited requests (HTTP 429); waiting before retry.')


class JoinRefused(BootstrapError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'GameJoin refused connection data (status {status}); no game session established.')


class InstanceMismatch(BootstrapError):
    pass


class JoinPending(BootstrapError):
    """A server remained loading; this is not a failed account identity."""
    pass


def job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
        raise BootstrapError('Invalid server JobId.')
    parsed = uuid.UUID(value)
    if not parsed.int:
        raise BootstrapError('Invalid server JobId.')
    return str(parsed)


def public_servers_url(place_id, cursor=None, *, sort_order='Desc'):
    if type(place_id) is not int or not 0 < place_id < 2**63:
        raise BootstrapError('Invalid server-list Place ID.')
    if sort_order not in ('Asc', 'Desc'):
        raise BootstrapError('Invalid server-list sort order.')
    query = {'sortOrder': sort_order, 'excludeFullGames': 'true', 'limit': '100'}
    if cursor is not None:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048 or any(ord(c) < 33 or ord(c) > 126 for c in cursor):
            raise BootstrapError('Invalid server-list cursor.')
        query['cursor'] = cursor
    return f'https://games.roblox.com/v1/games/{place_id}/servers/Public?' + urlencode(query)


def _public_server_request(url):
    match = re.fullmatch(r'https://games\.roblox\.com/v1/games/([1-9][0-9]{0,18})/servers/Public\?(.{1,8192})', url)
    if not match:
        return False
    try:
        query = parse_qs(match[2], keep_blank_values=True, max_num_fields=4)
        if any(len(values) != 1 for values in query.values()):
            return False
        return url == public_servers_url(int(match[1]), query.get('cursor', [None])[0],
                                        sort_order=query.get('sortOrder', [''])[0])
    except (ValueError, BootstrapError):
        return False


@dataclass(frozen=True, repr=False)
class PrivateInvite:
    link_id: str | None = None
    place_id: int | None = None
    link_code: str | None = None


def parse_vip_link(value: str) -> PrivateInvite:
    """Extract an invitation locally; never request an address supplied in a URL."""
    message = 'Invalid VIP link; use a Roblox Server share link or a game URL with privateServerLinkCode.'
    if not isinstance(value, str) or len(value) > 4096:
        raise BootstrapError(message)
    value = value.strip()
    if any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise BootstrapError(message)
    try:
        url = urlsplit(value)
        if (url.scheme != 'https' or url.netloc.lower() not in ('www.roblox.com', 'roblox.com')
                or url.fragment):
            raise ValueError
        query = parse_qs(url.query, keep_blank_values=True, max_num_fields=32)
        if any(len(values) != 1 for values in query.values()):
            raise ValueError
        if url.path in ('/share', '/share-links'):
            code = query.get('code', [''])[0]
            if query.get('type') != ['Server'] or not re.fullmatch(r'[a-fA-F0-9]{32}', code):
                raise ValueError
            return PrivateInvite(link_id=code)
        match = re.fullmatch(r'/games/([1-9][0-9]{0,18})(?:/[^?#]*)?', url.path)
        code = query.get('privateServerLinkCode', [''])[0]
        if not match or int(match[1]) >= 2**63 or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', code):
            raise ValueError
        return PrivateInvite(place_id=int(match[1]), link_code=code)
    except ValueError:
        raise BootstrapError(message) from None


@dataclass(repr=False)
class Credential:
    value: str = field(repr=False)

    def __post_init__(self):
        self.value = self.value.strip()
        prefix = ".ROBLOSECURITY="
        if self.value.startswith(prefix):
            self.value = self.value[len(prefix):]
        if not self.value or len(self.value) > 16384 or any(
            ord(c) < 33 or ord(c) > 126 or c in ';,"\\' for c in self.value
        ):
            raise BootstrapError("Invalid session cookie format; provide its value only.")

    def __repr__(self):
        return "Credential(<redacted>)"


def read_credential(env_name: str | None = None, file_path: str | None = None) -> Credential:
    if env_name is not None and file_path is not None:
        raise BootstrapError("Select one session source.")
    if file_path is not None:
        try:
            with Path(file_path).open("rb") as stream:
                value = stream.read(16388)
            if len(value) > 16387:
                raise BootstrapError("Session file exceeds the size limit.")
            return Credential(value.decode("utf-8-sig"))
        except (OSError, UnicodeError):
            raise BootstrapError("Cannot read the selected UTF-8 session file.") from None
    if env_name is not None:
        value = os.environ.get(env_name)
        if not value:
            raise BootstrapError("The explicitly selected session environment variable is empty.")
        return Credential(value)
    if not sys.stdin.isatty():
        raise BootstrapError("Hidden input requires an interactive terminal; run this command locally.")
    try:
        # Never fall back to visible input if terminal echo cannot be disabled.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return Credential(getpass.getpass("Your .ROBLOSECURITY session value (hidden): "))
    except (getpass.GetPassWarning, EOFError):
        raise BootstrapError("Hidden input is unavailable; use a local interactive terminal.") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Prevent forwarding a session cookie to a redirect destination.
        return None


@dataclass(repr=False)
class HttpReply:
    status: int
    headers: dict[str, str] = field(repr=False)
    body: bytes = field(repr=False)

    def __repr__(self):
        return f"HttpReply(status={self.status}, content=<redacted>)"


class RobloxHTTP:
    def __init__(self, timeout: float = 10):
        if not math.isfinite(timeout) or not 0 < timeout <= 10:
            raise BootstrapError("HTTP timeout must be finite and in (0, 10] seconds.")
        self.timeout = timeout
        self.opener = build_opener(NoRedirect())

    def request(self, url: str, *, credential: Credential | None = None, body: dict | None = None,
                csrf: str | None = None) -> HttpReply:
        details_id = url.removeprefix(PLACE_DETAILS_PREFIX) if url.startswith(PLACE_DETAILS_PREFIX) else ""
        details_request = (re.fullmatch(r"[1-9][0-9]{0,18}", details_id) is not None
                           and int(details_id) < 2**63 and body is None and csrf is None)
        public_request = _public_server_request(url) and body is None and csrf is None
        if url not in ALLOWED_URLS and not details_request and not public_request:
            raise BootstrapError("Destination is outside the fixed Roblox HTTPS endpoints.")
        if credential is None and not public_request:
            raise BootstrapError('This Roblox endpoint requires a session cookie.')
        headers = {"User-Agent": "Roblox/WinInet", "Accept": "application/json",
                   "Referer": "https://www.roblox.com/", "Origin": "https://www.roblox.com"}
        if credential is not None:
            headers['Cookie'] = f'.ROBLOSECURITY={credential.value}'
        if csrf:
            if any(ord(c) < 33 or ord(c) > 126 for c in csrf) or len(csrf) > 8192:
                raise BootstrapError("Invalid CSRF response header.")
            headers["X-CSRF-TOKEN"] = csrf
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                payload = response.read(MAX_RESPONSE + 1)
                if len(payload) > MAX_RESPONSE:
                    raise BootstrapError("Roblox response exceeded the size limit.")
                return HttpReply(response.code, {k.lower(): v for k, v in response.headers.items()}, payload)
        except (URLError, OSError, ValueError, HTTPException) as error:
            if isinstance(error, BootstrapError):
                raise
            failure = NetworkUnavailable if isinstance(error, (URLError, OSError, HTTPException)) else BootstrapError
            raise failure("HTTPS request failed; check network access and the configured proxy.") from None


def _json(reply: HttpReply):
    if "rblx-challenge-id" in reply.headers:
        raise BootstrapError("Roblox requires an additional challenge; complete account sign-in in its official client/site.")
    if reply.status == 429:
        raw_delay = reply.headers.get('retry-after', '10')
        try:
            try:
                delay = float(raw_delay)
            except ValueError:
                delay = parsedate_to_datetime(raw_delay).timestamp() - time.time()
            if not math.isfinite(delay) or delay < 0:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            delay = 10
        raise RateLimited(max(1, min(86400, delay)))
    if not 200 <= reply.status < 300:
        if reply.status == 401:
            raise BootstrapError("Roblox rejected the session (HTTP 401). Sign in again on the official site.")
        raise BootstrapError(f"Roblox rejected the request (HTTP {reply.status}).")
    try:
        result = json.loads(reply.body)
    except (ValueError, UnicodeError):
        raise BootstrapError("Roblox returned an unsupported JSON response.") from None
    return result


def _object(reply: HttpReply) -> dict:
    result = _json(reply)
    if not isinstance(result, dict):
        raise BootstrapError("Expected a JSON object from Roblox.")
    return result


@dataclass(frozen=True)
class Account:
    user_id: int

    def summary(self) -> dict:
        return {"state": "web_authenticated", "user_id": self.user_id,
                "web_authenticated": True, "game_session": False}


@dataclass(repr=False)
class ConnectionInfo:
    account: Account
    place_id: int
    endpoints: tuple[tuple[str, int], ...]
    _join_script: dict = field(repr=False)
    via_udmux: bool = True
    private_server: dict | None = None

    def summary(self) -> dict:
        result = {"state": "connection_info_ready", "user_id": self.account.user_id,
                "place_id": self.place_id, "endpoints": self.endpoints,
                "endpoint_transport": "udmux" if self.via_udmux else "direct",
                "web_authenticated": True, "connection_info_ready": True,
                "game_session": False,
                "note": "HTTPS bootstrap only; no authenticated game session established."}
        if self.private_server is not None:
            result.update(server_kind='private', private_server=self.private_server)
        return result

    def __repr__(self):
        return "ConnectionInfo(<session data redacted>; game_session=False)"

    def transport_fields(self) -> dict:
        """Only known field presence/types. Never serialize ticket/key values."""
        result = {}
        for name in ("ClientPublicKeyData", "EphemeralEarlyPubKey", "RandomSeed1",
                     "TokenValue", "TokenGenAlgorithm", "PepperId"):
            value = self._join_script.get(name)
            result[name] = {"present": value is not None,
                            "type": type(value).__name__ if value is not None else None}
        return result


class RobloxBootstrap:
    def __init__(self, credential: Credential, *, http: RobloxHTTP | None = None):
        self._credential = credential
        self._http = http if http is not None else RobloxHTTP()
        self._csrf = None
        self._account = None
        self._identity_until = 0

    def __repr__(self):
        return "RobloxBootstrap(<redacted>)"

    def authenticate(self, *, cached=False) -> Account:
        if cached and self._account is not None and time.monotonic() < self._identity_until:
            return self._account
        result = _object(self._http.request(IDENTITY_URL, credential=self._credential))
        user_id = result.get("id")
        if type(user_id) is not int or not 0 < user_id < 2**63:
            raise BootstrapError("Identity response did not contain a valid user ID.")
        self._account = Account(user_id)
        self._identity_until = time.monotonic() + 300
        return self._account

    def _post_join(self, body: dict, *, url: str = JOIN_URL) -> dict:
        response = self._http.request(url, credential=self._credential, body=body, csrf=self._csrf)
        if "rblx-challenge-id" not in response.headers and response.status == 403:
            token = response.headers.get("x-csrf-token")
            if token:
                self._csrf = token
                # One normal CSRF challenge retry, never an unbounded loop.
                response = self._http.request(url, credential=self._credential, body=body, csrf=token)
        return _object(response)

    def _access_refusal(self, account: Account, place_id: int) -> str:
        """Read one diagnostic; never echo arbitrary server messages or retry a gate."""
        reason = None
        try:
            data = _json(self._http.request(PLACE_DETAILS_PREFIX + str(place_id),
                                           credential=self._credential))
            if isinstance(data, list):
                for row in data:
                    if (isinstance(row, dict) and type(row.get("placeId")) is int
                            and row["placeId"] == place_id and row.get("isPlayable") is False):
                        reason = row.get("reasonProhibited")
                        break
        except BootstrapError:
            pass  # The original refusal remains valid if the diagnostic is unavailable.
        prefix = (f"GameJoin refused connection data (status 30); user_id={account.user_id}, "
                  f"place_id={place_id}. ")
        if reason == "ContextualPlayabilityAgeCheckRequired":
            return (prefix + "Roblox requires an age check for this account to access this game "
                    "(ContextualPlayabilityAgeCheckRequired). Check that the selected cookie belongs "
                    "to the same account used in Roblox Player, complete the age check on the official "
                    "Roblox site/app if prompted, then retry. No game session established.")
        if reason == "ContextualPlayabilityCoreGated":
            return (prefix + "Roblox currently restricts this account's access to this game "
                    "(ContextualPlayabilityCoreGated). Check access in the official Roblox site/app "
                    "using the same account. No game session established.")
        return (prefix + "Roblox requires an additional experience access check. Check access in the "
                "official Roblox site/app using the same account as the selected cookie. "
                "No game session established.")

    def prepare(self, place_id: int, *, attempts: int = 3) -> ConnectionInfo:
        if type(place_id) is not int or not 0 < place_id < 2**63:
            raise BootstrapError("Place ID must be a positive 64-bit integer.")
        if type(attempts) is not int or not 1 <= attempts <= 5:
            raise BootstrapError("Join polling attempts must be 1..5.")
        account = self.authenticate()
        body = {"placeId": place_id, "isTeleport": False, "gameJoinAttemptId": str(uuid.uuid4())}
        return self._prepare_join(account, place_id, body, attempts=attempts)

    def prepare_instance(self, place_id, server_id, *, attempts=3):
        if type(place_id) is not int or not 0 < place_id < 2**63:
            raise BootstrapError('Place ID must be a positive 64-bit integer.')
        server_id = job_id(server_id)
        if type(attempts) is not int or not 1 <= attempts <= 5:
            raise BootstrapError('Join polling attempts must be 1..5.')
        account = self.authenticate(cached=True)
        body = {'placeId': place_id, 'gameId': server_id, 'isTeleport': True,
                'gameJoinAttemptId': str(uuid.uuid4())}
        info = self._prepare_join(account, place_id, body, attempts=attempts, url=INSTANCE_JOIN_URL)
        if job_id(info._join_script.get('GameId')) != server_id:
            raise InstanceMismatch('GameJoin returned a different server; requested JobId was not joined.')
        return info

    def prepare_vip(self, link: str, *, attempts: int = 3) -> ConnectionInfo:
        invite = parse_vip_link(link)
        if type(attempts) is not int or not 1 <= attempts <= 5:
            raise BootstrapError('Join polling attempts must be 1..5.')
        account = self.authenticate()
        owner_id = private_id = None
        place_id, code = invite.place_id, invite.link_code
        if invite.link_id is not None:
            resolved = self._post_join({'linkId': invite.link_id, 'linkType': 'Server'}, url=RESOLVE_LINK_URL)
            data = resolved.get('privateServerInviteData')
            if not isinstance(data, dict) or data.get('status') != 'Valid':
                raise BootstrapError('VIP invitation is invalid, expired or unavailable to this account.')
            place_id, code = data.get('placeId'), data.get('linkCode')
            owner_id, private_id = data.get('ownerUserId'), data.get('privateServerId')
            if any(type(n) is not int or not 0 < n < 2**63 for n in (place_id, owner_id, private_id)):
                raise BootstrapError('VIP resolver returned invalid server identifiers.')
            if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', code):
                raise BootstrapError('VIP resolver returned no supported invitation code.')
        body = {'placeId': place_id, 'linkCode': code, 'isTeleport': False,
                'gameJoinAttemptId': str(uuid.uuid4())}
        info = self._prepare_join(account, place_id, body, attempts=attempts, url=PRIVATE_JOIN_URL)
        script = info._join_script
        # Share resolution uses a numeric ID; joinScript uses a different UUID.
        # Check private-server presence and the resolved owner, not equality of these IDs.
        try:
            server_uuid = uuid.UUID(script.get('PrivateServerID', ''))
        except (ValueError, TypeError, AttributeError):
            raise BootstrapError('Private GameJoin did not confirm a private server.') from None
        returned_owner = script.get('PrivateServerOwnerID')
        if (not server_uuid.int or type(returned_owner) is not int or not 0 < returned_owner < 2**63
                or owner_id is not None and returned_owner != owner_id):
            raise BootstrapError('Private GameJoin returned an unexpected server owner or server ID.')
        info.private_server = {'confirmed': True, 'owner_user_id': returned_owner}
        if private_id is not None:
            info.private_server['invite_server_id'] = private_id
        return info

    def _prepare_join(self, account: Account, place_id: int, body: dict, *, attempts: int,
                      url: str = JOIN_URL) -> ConnectionInfo:
        for attempt in range(attempts):
            result = self._post_join(body, url=url)
            status = result.get("status")
            if type(status) is not int:
                raise BootstrapError("GameJoin did not return an integer status.")
            if status == 2:
                return self._connection_info(account, place_id, result.get("joinScript"))
            if status == 30:
                raise BootstrapError(self._access_refusal(account, place_id))
            if status not in (0, 1):
                # Raw server messages can contain session fields; do not echo them.
                raise JoinRefused(status)
            if attempt + 1 < attempts:
                time.sleep(1)
        raise JoinPending("GameJoin is still waiting/loading; bounded polling ended without a session.")

    @staticmethod
    def _connection_info(account: Account, place_id: int, script) -> ConnectionInfo:
        if not isinstance(script, dict):
            raise BootstrapError("GameJoin status 2 did not include a supported joinScript object.")
        if type(script.get("PlaceId")) is not int or script["PlaceId"] != place_id:
            raise BootstrapError("Returned connection data does not match the requested Place ID.")
        if type(script.get("UserId")) is not int or script["UserId"] != account.user_id:
            raise BootstrapError("Returned connection data does not match the authenticated account.")
        if not isinstance(script.get("ClientTicket"), str) or not script["ClientTicket"]:
            raise BootstrapError("GameJoin returned no client ticket.")
        peers = script.get("UdmuxEndpoints")
        via_udmux = peers is not None and peers != []
        if not via_udmux:
            peers = script.get("ServerConnections")
        if not isinstance(peers, list) or not peers or len(peers) > 16:
            raise BootstrapError("GameJoin returned no supported UDMUX or direct server endpoint list.")
        endpoints = []
        try:
            for peer in peers:
                if not isinstance(peer, dict) or type(peer.get("Address")) is not str:
                    raise ValueError
                host = str(ip_address(peer["Address"]))
                if "%" in host or ip_address(host).version != 4:
                    raise ValueError
                port = peer.get("Port")
                if type(port) is not int or not 1 <= port <= 65535:
                    raise ValueError
                endpoints.append((host, port))
        except ValueError:
            raise BootstrapError("GameJoin returned an invalid endpoint.") from None
        return ConnectionInfo(account, place_id, tuple(endpoints), script, via_udmux=via_udmux)

