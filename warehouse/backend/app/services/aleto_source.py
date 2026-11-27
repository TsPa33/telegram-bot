"""Bounded HTTP client for the Aleto catalogue only."""
from http.client import HTTPException, HTTPSConnection
from ipaddress import ip_address
import socket
import ssl
from time import monotonic, sleep
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from app.services.aleto_adapter import source_url

USER_AGENT = 'CarPotCatalogueWorker/1.0'
MAX_ROBOTS_BYTES = 128 * 1024
TIMEOUT = 15
MIN_INTERVAL = 3


class SourceUnavailable(ValueError):
    """A source request failed without providing usable catalogue data."""


class PublicHTTPSConnection(HTTPSConnection):
    def connect(self):
        # Connect to the same address that was checked. TLS still validates
        # the certificate against the original Aleto hostname.
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ip_address(item[4][0]).is_global for item in addresses):
            raise SourceUnavailable('SOURCE_ADDRESS_REJECTED')
        family, kind, protocol, _, address = addresses[0]
        raw = socket.socket(family, kind, protocol)
        try:
            raw.settimeout(self.timeout)
            raw.connect(address)
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class AletoSource:
    def __init__(self):
        self.next_request = 0.0
        self.policies: dict[str, RobotFileParser] = {}

    def read(self, url: str, *, max_bytes: int, allowed_types: tuple[str, ...]) -> bytes:
        parsed = urlsplit(source_url(url))
        host = parsed.hostname
        if host not in self.policies:
            policy = RobotFileParser()
            body = self._request(host, '/robots.txt', MAX_ROBOTS_BYTES, ('text/plain',))
            try:
                text = body.decode('utf-8-sig')
            except UnicodeError:
                raise SourceUnavailable('ROBOTS_INVALID') from None
            if not any(line.lower().startswith('user-agent:') for line in text.splitlines()):
                raise SourceUnavailable('ROBOTS_INVALID')
            policy.parse(text.splitlines())
            self.policies[host] = policy
            self.next_request = max(self.next_request, monotonic() + self._interval(host))
        if not self.policies[host].can_fetch(USER_AGENT, url):
            raise SourceUnavailable('ROBOTS_DISALLOWED')
        target = parsed.path or '/'
        if parsed.query:
            target += '?' + parsed.query
        return self._request(host, target, max_bytes, allowed_types)

    def _interval(self, host: str) -> float:
        policy = self.policies.get(host)
        if not policy:
            return MIN_INTERVAL
        delay = policy.crawl_delay(USER_AGENT) or 0
        rate = policy.request_rate(USER_AGENT)
        return max(MIN_INTERVAL, delay, rate.seconds / rate.requests if rate and rate.requests else 0)

    def _request(self, host, target, max_bytes, allowed_types):
        sleep(max(0, self.next_request - monotonic()))
        connection = PublicHTTPSConnection(host, timeout=TIMEOUT, context=ssl.create_default_context())
        try:
            connection.request('GET', target, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status != 200:
                raise SourceUnavailable(f'SOURCE_HTTP_{response.status}')
            if response.headers.get_content_type() not in allowed_types:
                raise SourceUnavailable('SOURCE_CONTENT_TYPE')
            if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise SourceUnavailable('SOURCE_CONTENT_ENCODING')
            deadline = monotonic() + TIMEOUT
            body = bytearray()
            while len(body) <= max_bytes:
                if monotonic() >= deadline:
                    raise SourceUnavailable('SOURCE_TIMEOUT')
                chunk = response.read1(min(65536, max_bytes + 1 - len(body)))
                if not chunk:
                    return bytes(body)
                body.extend(chunk)
            raise SourceUnavailable('SOURCE_BODY_LIMIT')
        except (OSError, HTTPException) as exc:
            raise SourceUnavailable('SOURCE_UNREACHABLE') from exc
        finally:
            connection.close()
            self.next_request = monotonic() + self._interval(host)
