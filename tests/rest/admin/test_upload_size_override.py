#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# See the GNU Affero General Public License for more details:
# <https://www.gnu.org/licenses/agpl-3.0.html>.
#

"""SynACK: per-user overrides of `max_upload_size`."""

from twisted.internet.testing import MemoryReactor
from twisted.web.resource import Resource

import synapse.rest.admin
from synapse.app._base import max_request_body_size
from synapse.rest.client import login, media
from synapse.server import HomeServer
from synapse.types import JsonDict
from synapse.util.clock import Clock

from tests import unittest
from tests.server import FakeChannel


class UploadSizeOverrideTestCase(unittest.HomeserverTestCase):
    servlets = [
        synapse.rest.admin.register_servlets,
        login.register_servlets,
        media.register_servlets,
    ]

    def default_config(self) -> JsonDict:
        config = super().default_config()
        config["max_upload_size"] = "100"
        config["max_upload_size_override_limit"] = "1K"
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
        self.url = f"/_synapse/admin/v1/users/{self.user}/override_upload_size"

    def _set(self, size: object, tok: str | None = None) -> FakeChannel:
        return self.make_request(
            "POST",
            self.url,
            {"max_upload_size": size},
            access_token=tok or self.admin_tok,
        )

    def _upload(self, size: int) -> FakeChannel:
        return self.make_request(
            "POST",
            "/_matrix/media/v3/upload",
            content=b"0" * size,
            access_token=self.user_tok,
            shorthand=False,
            content_type=b"text/plain",
        )

    def _media_config(self, path: str) -> int:
        channel = self.make_request(
            "GET", path, access_token=self.user_tok, shorthand=False
        )
        self.assertEqual(channel.code, 200, channel.json_body)
        return channel.json_body["m.upload.size"]

    def test_get_set_delete(self) -> None:
        channel = self.make_request("GET", self.url, access_token=self.admin_tok)
        self.assertEqual(channel.code, 200, channel.json_body)
        self.assertEqual(channel.json_body, {})

        channel = self._set(500)
        self.assertEqual(channel.code, 200, channel.json_body)
        self.assertEqual(channel.json_body, {"max_upload_size": 500})

        channel = self.make_request("GET", self.url, access_token=self.admin_tok)
        self.assertEqual(channel.json_body, {"max_upload_size": 500})

        channel = self.make_request("DELETE", self.url, access_token=self.admin_tok)
        self.assertEqual(channel.code, 200, channel.json_body)
        channel = self.make_request("GET", self.url, access_token=self.admin_tok)
        self.assertEqual(channel.json_body, {})

    def test_uploads_follow_override(self) -> None:
        self.assertEqual(self._upload(101).code, 413)

        self.assertEqual(self._set(1024).code, 200)
        self.assertEqual(self._upload(1024).code, 200)
        self.assertEqual(self._upload(1025).code, 413)

        # Smaller than the default works too
        self.assertEqual(self._set(10).code, 200)
        self.assertEqual(self._upload(10).code, 200)
        channel = self._upload(11)
        self.assertEqual(channel.code, 413)
        self.assertEqual(channel.json_body["errcode"], "M_TOO_LARGE")

        self.make_request("DELETE", self.url, access_token=self.admin_tok)
        self.assertEqual(self._upload(100).code, 200)
        self.assertEqual(self._upload(101).code, 413)

    def test_async_upload_follows_override(self) -> None:
        self._set(1024)
        channel = self.make_request(
            "POST", "/_matrix/media/v1/create", access_token=self.user_tok
        )
        self.assertEqual(channel.code, 200, channel.json_body)
        media_id = channel.json_body["content_uri"].rsplit("/", 1)[1]
        channel = self.make_request(
            "PUT",
            f"/_matrix/media/v3/upload/test/{media_id}",
            content=b"0" * 1024,
            access_token=self.user_tok,
            shorthand=False,
            content_type=b"text/plain",
        )
        self.assertEqual(channel.code, 200, channel.json_body)

    def test_media_config_reports_user_limit(self) -> None:
        paths = ("/_matrix/client/v1/media/config", "/_matrix/media/v3/config")
        for path in paths:
            self.assertEqual(self._media_config(path), 100)
        self._set(1024)
        for path in paths:
            self.assertEqual(self._media_config(path), 1024)

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
                f"/_synapse/admin/v1/users/{user_id}/override_upload_size",
                {"max_upload_size": 500},
                access_token=self.admin_tok,
            )
            self.assertEqual(channel.code, code, channel.json_body)

    def test_request_body_limit_covers_override_limit(self) -> None:
        self.assertGreaterEqual(max_request_body_size(self.hs.config), 1024)
