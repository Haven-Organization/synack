# SynACK

SynACK is a fork of [Synapse](https://github.com/element-hq/synapse), the
Matrix homeserver, with a small set of meaningful, opinionated changes.

It tracks upstream Synapse releases and is currently based on
**Synapse v1.160.0**. Everything not listed below behaves exactly like stock
Synapse, so the [upstream documentation](https://element-hq.github.io/synapse/latest/)
applies as is. The original Synapse README is kept in
[README.rst](README.rst).

## Changes from stock Synapse

### 1. HTTP Range requests for media

Stock Synapse always sends the whole file, so seeking in audio and video does
not work in Chromium-based clients such as Element Desktop. SynACK answers
`Range` requests on media downloads with `206 Partial Content`
(`416 Range Not Satisfiable` for an out-of-bounds range) and advertises
`Accept-Ranges: bytes`.

- Applies to media read from local disk: the primary media store or a
  `FileStorageProviderBackend` copy. Other storage providers (S3 and similar)
  still serve the full file.
- A single byte range is supported, which is what browsers send when seeking.
  Anything else is ignored and gets the full file.

### 2. Remote media on the legacy endpoints is fetched over federation

When a client asks for remote media through the old unauthenticated endpoints
(`/_matrix/media/v3/download` and `/_matrix/media/v3/thumbnail`, also `r0`),
stock Synapse fetches it from the origin server with the deprecated
unauthenticated media protocol. Many servers, including matrix.org, no longer
serve that protocol, so those requests fail with a 404.

SynACK fetches over the authenticated federation media endpoint first and
falls back to the old protocol only if the origin does not support the new
one. What the client receives is unchanged. This matters mostly for servers
that set `enable_authenticated_media: false` to keep older clients working.

### 3. Optional fallback for remote media through another homeserver

Some origin servers refuse media requests from particular homeservers, for
example behind a WAF that blocks their address range. SynACK can retry a
failed remote media fetch through the client-server API of another homeserver
where you have an account. It is off unless configured:

```yaml
remote_media_fetch_fallback:
  enabled: true
  homeserver_url: "https://matrix.example.org"
  access_token: "<access token of your account on that homeserver>"
```

The fallback is only tried after the normal fetch has failed. The access token
is a credential for that account, so keep your `homeserver.yaml` private.

## Installing

Build and install SynACK the same way as Synapse from source; see the
[upstream installation guide](https://element-hq.github.io/synapse/latest/setup/installation.html).
The Python package name (`matrix-synapse`), module name (`synapse`) and
configuration format are unchanged, so SynACK is a drop-in replacement for the
Synapse release it is based on.

## Maintaining the fork

How the changes are tracked and how upstream releases are merged is described
in [SYNACK.md](SYNACK.md).

## License

SynACK is licensed only under the
[GNU Affero General Public License v3.0 or later](LICENSE-AGPL-3.0).

Upstream Synapse is also offered by Element under a separate commercial
license. That option does not exist for SynACK: the commercial license file and
the license metadata that referred to it have been removed, and the dual
licensing described in [README.rst](README.rst) applies to Element's Synapse,
not to this fork.

Synapse is developed by Element and the Matrix.org Foundation. SynACK is not
affiliated with or endorsed by either.
