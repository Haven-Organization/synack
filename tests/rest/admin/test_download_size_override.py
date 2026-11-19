#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# See the GNU Affero General Public License for more details:
# <https://www.gnu.org/licenses/agpl-3.0.html>.
#

"""SynACK: per-user overrides of the remote media download size."""

from unittest.mock import AsyncMock

from twisted.internet.testing import MemoryReactor
from twisted.web.resource import Resource

import synapse.rest.admin
from synapse.api.errors import SynapseError
from synapse.rest.client import login, media
from synapse.server import HomeServer
from synapse.types import JsonDict
from synapse.util.clock import Clock

from tests import unittest
from tests.server import FakeChannel


class DownloadSizeOverrideTestCase(unittest.HomeserverTestCase):
    servlets = [
        synapse.rest.admin.register_servlets,
        login.register_servlets,
        media.register_servlets,
    ]

    def default_config(self) -> JsonDict:
        config = super().default_config()
        config["max_upload_size"] = "100"
        config["max_download_size_override_limit"] = "1K"
        # The legacy endpoints only fetch remote media when this is off
        config["enable_authenticated_media"] = False
        return config

    def create_resource_dict(self) -> dict[str, Resource]:
        resources = super().create_resource_dict()
        resources["/_matrix/media"] = self.hs.get_media_repository_resource()
        return resources

    def prepare(self, reactor: MemoryReactor, clock: Clock, hs: HomeServer) -> None:
        self.admin = self.register_user("admin", "pass", admin=True)
        self.admin_tok = self.login("admin", "pass")
        self.user = self.register_user("user", "pass")
        self.user_tok = self.login("user", "pass")
        self.url = f"/_synapse/admin/v1/users/{self.user}/override_download_size"

        # Every remote fetch fails, recording the size limit it was given.
        client = hs.get_federation_client()
        self.fetch = AsyncMock(side_effect=SynapseError(502, "nope"))
        client.federation_download_media = self.fetch  # type: ignore[method-assign]
        client.download_media = self.fetch  # type: ignore[method-assign]

    def _set(self, size: object, tok: str | None = None) -> FakeChannel:
        return self.make_request(
            "POST",
            self.url,
            {"max_download_size": size},
            access_token=tok or self.admin_tok,
        )

    def _fetched_max_size(self, path: str, tok: str | None) -> int:
        self.fetch.reset_mock()
        channel = self.make_request("GET", path, access_token=tok, shorthand=False)
        self.assertEqual(channel.code, 502, (path, channel.json_body))
        self.fetch.assert_called_once()
        return self.fetch.call_args.kwargs["max_size"]

    def test_get_set_delete(self) -> None:
        channel = self.make_request("GET", self.url, access_token=self.admin_tok)
        self.assertEqual(channel.code, 200, channel.json_body)
        self.assertEqual(channel.json_body, {})

        channel = self._set(500)
        self.assertEqual(channel.code, 200, channel.json_body)
        self.assertEqual(channel.json_body, {"max_download_size": 500})

        channel = self.make_request("GET", self.url, access_token=self.admin_tok)
        self.assertEqual(channel.json_body, {"max_download_size": 500})

        channel = self.make_request("DELETE", self.url, access_token=self.admin_tok)
        self.assertEqual(channel.code, 200, channel.json_body)
        channel = self.make_request("GET", self.url, access_token=self.admin_tok)
        self.assertEqual(channel.json_body, {})

    def test_remote_fetches_follow_override(self) -> None:
        paths = (
            "/_matrix/client/v1/media/download/remote.org/abc",
            "/_matrix/client/v1/media/thumbnail/remote.org/abc?width=32&height=32",
            "/_matrix/media/v3/download/remote.org/abc",
            "/_matrix/media/v3/thumbnail/remote.org/abc?width=32&height=32",
        )
        for path in paths:
            self.assertEqual(self._fetched_max_size(path, self.user_tok), 100, path)

        self.assertEqual(self._set(1024).code, 200)
        for path in paths:
            self.assertEqual(self._fetched_max_size(path, self.user_tok), 1024, path)

        # The admin has no override, so gets the default
        for path in paths:
            self.assertEqual(self._fetched_max_size(path, self.admin_tok), 100, path)

        self.make_request("DELETE", self.url, access_token=self.admin_tok)
        for path in paths:
            self.assertEqual(self._fetched_max_size(path, self.user_tok), 100, path)

    def test_legacy_endpoints_without_valid_token_use_default(self) -> None:
        self._set(1024)
        for path in (
            "/_matrix/media/v3/download/remote.org/abc",
            "/_matrix/media/v3/thumbnail/remote.org/abc?width=32&height=32",
        ):
            self.assertEqual(self._fetched_max_size(path, None), 100, path)
            self.assertEqual(self._fetched_max_size(path, "bogus"), 100, path)

    def test_rejects_values_above_limit_or_invalid(self) -> None:
        for bad in (1025, -1, "1M", 1.5, None):
            channel = self._set(bad)
            self.assertEqual(channel.code, 400, (bad, channel.json_body))
            self.assertEqual(channel.json_body["errcode"], "M_INVALID_PARAM")

    def test_requires_admin(self) -> None:
        self.assertEqual(self._set(500, tok=self.user_tok).code, 403)
        channel = self.make_request("GET", self.url, access_token=self.user_tok)
        self.assertEqual(channel.code, 403)

    def test_rejects_remote_and_unknown_users(self) -> None:
        for user_id, code in (("@x:remote.org", 400), ("@nobody:test", 404)):
            channel = self.make_request(
                "POST",
                f"/_synapse/admin/v1/users/{user_id}/override_download_size",
                {"max_download_size": 500},
                access_token=self.admin_tok,
            )
            self.assertEqual(channel.code, code, channel.json_body)
