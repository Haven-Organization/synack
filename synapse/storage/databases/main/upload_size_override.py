#
# This file is licensed under the Affero General Public License (AGPL) version 3.
#
# See the GNU Affero General Public License for more details:
# <https://www.gnu.org/licenses/agpl-3.0.html>.
#

"""SynACK: per-user overrides of `max_upload_size`."""

from typing import TYPE_CHECKING

from synapse.storage.database import (
    DatabasePool,
    LoggingDatabaseConnection,
    LoggingTransaction,
)
from synapse.storage.databases.main import CacheInvalidationWorkerStore
from synapse.util.caches.descriptors import cached

if TYPE_CHECKING:
    from synapse.server import HomeServer


class UploadSizeOverrideStore(CacheInvalidationWorkerStore):
    def __init__(
        self,
        database: DatabasePool,
        db_conn: LoggingDatabaseConnection,
        hs: "HomeServer",
    ) -> None:
        super().__init__(database, db_conn, hs)
        self._default_max_upload_size = hs.config.media.max_upload_size

    @cached(max_entries=10000)
    async def get_upload_size_override_for_user(self, user_id: str) -> int | None:
        """The user's overridden maximum upload size in bytes, or None if unset."""
        return await self.db_pool.simple_select_one_onecol(
            table="upload_size_override",
            keyvalues={"user_id": user_id},
            retcol="max_upload_size",
            allow_none=True,
            desc="get_upload_size_override_for_user",
        )

    async def get_max_upload_size_for_user(self, user_id: str) -> int:
        """The largest upload this user may make, in bytes."""
        override = await self.get_upload_size_override_for_user(user_id)
        return self._default_max_upload_size if override is None else override

    async def set_upload_size_override_for_user(
        self, user_id: str, max_upload_size: int
    ) -> None:
        def _txn(txn: LoggingTransaction) -> None:
            self.db_pool.simple_upsert_txn(
                txn,
                table="upload_size_override",
                keyvalues={"user_id": user_id},
                values={"max_upload_size": max_upload_size},
            )
            self._invalidate_cache_and_stream(
                txn, self.get_upload_size_override_for_user, (user_id,)
            )

        await self.db_pool.runInteraction("set_upload_size_override_for_user", _txn)

    async def delete_upload_size_override_for_user(self, user_id: str) -> None:
        def _txn(txn: LoggingTransaction) -> None:
            self.db_pool.simple_delete_txn(
                txn,
                table="upload_size_override",
                keyvalues={"user_id": user_id},
            )
            self._invalidate_cache_and_stream(
                txn, self.get_upload_size_override_for_user, (user_id,)
            )

        await self.db_pool.runInteraction("delete_upload_size_override_for_user", _txn)
