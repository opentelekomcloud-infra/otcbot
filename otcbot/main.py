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

from otcbot.init_project import InitProject


async def main() -> None:
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(
        description='OTC Bot..')
    subparsers = parser.add_subparsers(
        dest='subparser_name',
        help='sub-command help')
    InitProject.argparse_arguments(subparsers)

    args = parser.parse_args()

    if args.subparser_name == 'init_project':
        InitProject().execute(args)


if __name__ == "__main__":
    try:
        asyncio.run(
            main()
        )
    except KeyboardInterrupt:
        pass
