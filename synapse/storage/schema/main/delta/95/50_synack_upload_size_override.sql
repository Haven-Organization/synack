--
-- This file is licensed under the Affero General Public License (AGPL) version 3.
--
-- See the GNU Affero General Public License for more details:
-- <https://www.gnu.org/licenses/agpl-3.0.html>.

-- SynACK: per-user overrides of `max_upload_size`, set through the admin API.
CREATE TABLE IF NOT EXISTS upload_size_override (
    user_id TEXT NOT NULL PRIMARY KEY,
    max_upload_size BIGINT NOT NULL
);
