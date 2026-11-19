#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# See the GNU Affero General Public License for more details:
# <https://www.gnu.org/licenses/agpl-3.0.html>.
#

"""SynACK: admin API for per-user overrides of the remote media download size."""

from http import HTTPStatus
from typing import TYPE_CHECKING

from synapse.api.errors import Codes, NotFoundError, SynapseError
from synapse.http.servlet import RestServlet, parse_json_object_from_request
from synapse.http.site import SynapseRequest
from synapse.rest.admin._base import admin_patterns, assert_requester_is_admin
from synapse.types import JsonDict

if TYPE_CHECKING:
    from synapse.server import HomeServer


class DownloadSizeOverrideRestServlet(RestServlet):
    """Get, set or remove the largest remote media file fetched for a user.

    Example:
        POST /_synapse/admin/v1/users/@test:example.com/override_download_size
        {"max_download_size": 2147483648}

        200 OK
        {"max_download_size": 2147483648}
    """

    PATTERNS = admin_patterns("/users/(?P<user_id>[^/]*)/override_download_size$")

    def __init__(self, hs: "HomeServer"):
        self.store = hs.get_datastores().main
        self.auth = hs.get_auth()
        self.is_mine_id = hs.is_mine_id
        self.override_limit = hs.config.media.max_download_size_override_limit

    async def _check(self, request: SynapseRequest, user_id: str) -> None:
        await assert_requester_is_admin(self.auth, request)
        if not self.is_mine_id(user_id):
            raise SynapseError(
                HTTPStatus.BAD_REQUEST, "Only local users can have an override"
            )
        if not await self.store.get_user_by_id(user_id):
            raise NotFoundError("User not found")

    async def on_GET(
        self, request: SynapseRequest, user_id: str
    ) -> tuple[int, JsonDict]:
        await self._check(request, user_id)
        override = await self.store.get_download_size_override_for_user(user_id)
        return HTTPStatus.OK, (
            {} if override is None else {"max_download_size": override}
        )

    async def on_POST(
        self, request: SynapseRequest, user_id: str
    ) -> tuple[int, JsonDict]:
        await self._check(request, user_id)

        body = parse_json_object_from_request(request)
        size = body.get("max_download_size")
        if type(size) is not int or size < 0:  # noqa: E721
            raise SynapseError(
                HTTPStatus.BAD_REQUEST,
                "max_download_size must be a non-negative integer number of bytes",
                errcode=Codes.INVALID_PARAM,
            )
        if size > self.override_limit:
            raise SynapseError(
                HTTPStatus.BAD_REQUEST,
                f"max_download_size may not exceed {self.override_limit} bytes; "
                "raise max_download_size_override_limit in the homeserver config "
                "to allow more",
                errcode=Codes.INVALID_PARAM,
            )

        await self.store.set_download_size_override_for_user(user_id, size)
        return HTTPStatus.OK, {"max_download_size": size}

    async def on_DELETE(
        self, request: SynapseRequest, user_id: str
    ) -> tuple[int, JsonDict]:
        await self._check(request, user_id)
        await self.store.delete_download_size_override_for_user(user_id)
        return HTTPStatus.OK, {}
