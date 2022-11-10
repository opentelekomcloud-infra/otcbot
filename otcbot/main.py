# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import asyncio
import logging
import sys
from time import sleep

from aiohttp import ClientConnectionError, ServerDisconnectedError
from nio import (
    AsyncClient,
    AsyncClientConfig,
    InviteMemberEvent,
    LocalProtocolError,
    LoginError,
    MegolmEvent,
    RoomMessageText,
    UnknownEvent,
)

from otcbot.init_project import InitProject
from otcbot.propose_dep_update import ProposeDepUpdate

from otcbot.callbacks import Callbacks
from otcbot.config import Config
from otcbot.storage import Storage

logger = logging.getLogger(__name__)


async def main() -> None:
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.yaml"

    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="OTC Bot..")
    subparsers = parser.add_subparsers(
        dest="subparser_name", help="sub-command help"
    )
    InitProject.argparse_arguments(subparsers)
    ProposeDepUpdate.argparse_arguments(subparsers)

    args = parser.parse_args()

    # Read the parsed config file and create a Config object

    if args.subparser_name == "init_project":
        InitProject().execute(args)
    elif args.subparser_name == "dep_update":
        ProposeDepUpdate().execute(args)
    else:
        # Run the bot

        config = Config(config_path)

        # Configure the database
        store = Storage(config.database)

        # Configuration options for the AsyncClient
        client_config = AsyncClientConfig(
            max_limit_exceeded=0,
            max_timeouts=0,
            store_sync_tokens=True,
            encryption_enabled=True,
        )

        # Initialize the matrix client
        client = AsyncClient(
            config.homeserver_url,
            config.user_id,
            device_id=config.device_id,
            store_path=config.store_path,
            config=client_config,
        )

        if config.user_token:
            client.access_token = config.user_token
            client.user_id = config.user_id

        # Set up event callbacks
        callbacks = Callbacks(client, store, config)
        client.add_event_callback(callbacks.message, (RoomMessageText,))
        client.add_event_callback(
            callbacks.invite_event_filtered_callback, (InviteMemberEvent,)
        )
        client.add_event_callback(callbacks.decryption_failure, (MegolmEvent,))
        client.add_event_callback(callbacks.unknown, (UnknownEvent,))

        # Keep trying to reconnect on failure (with some time in-between)
        while True:
            try:
                if config.user_token:
                    # Use token to log in
                    client.load_store()

                    # Sync encryption keys with the server
                    if client.should_upload_keys:
                        await client.keys_upload()
                else:
                    # Try to login with the configured username/password
                    try:
                        login_response = await client.login(
                            password=config.user_password,
                            device_name=config.device_name,
                        )

                        # Check if login failed
                        if type(login_response) == LoginError:
                            logger.error(
                                "Failed to login: %s", login_response.message
                            )
                            return False
                    except LocalProtocolError as e:
                        # There's an edge case here where the user hasn't installed the correct C
                        # dependencies. In that case, a LocalProtocolError is raised on login.
                        logger.fatal(
                            "Failed to login. Have you installed the correct dependencies? "
                            "https://github.com/poljar/matrix-nio#installation "
                            "Error: %s",
                            e,
                        )
                        return False

                    # Login succeeded!

                logger.info(f"Logged in as {config.user_id}")
                await client.sync_forever(timeout=30000, full_state=True)

            except (ClientConnectionError, ServerDisconnectedError):
                logger.warning(
                    "Unable to connect to homeserver, retrying in 15s..."
                )

                # Sleep so we don't bombard the server with login requests
                sleep(15)
            finally:
                # Make sure to close the client connection on disconnect
                await client.close()


def cmd():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
