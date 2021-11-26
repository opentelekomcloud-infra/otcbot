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

import logging
from pathlib import Path

from jinja2 import Template

import pkg_resources


class InitProject:
    @classmethod
    def argparse_arguments(cls, parser) -> None:
        subparser = parser.add_parser(
            'init_project', help='Initialize new project')
        subparser.add_argument(
            '--name', required=True, help='project name')
        subparser.add_argument(
            '--path', required=True,
            help='Path to the root folder where to initialize project')
        subparser.add_argument(
            '--description', help='Project description')
        subparser.add_argument(
            '--enable-api-ref', action='store_true',
            help='Produce API-ref structure'
        )
        subparser.add_argument(
            '--enable-rn', action='store_true',
            help='Produce ReleaseNotes structure'
        )

    def _populate_template(self, src: str, dest, args) -> None:
        tm = Template(src)
        with open(dest, 'w') as f:
            f.write(tm.render(vars(args)))
            f.write('\n')

    def _process_template_section(self, files: list, args) -> None:
        for f in files:
            logging.debug(f"Processing {f}")
            dest_path = Path(args.path, f)
            Path(dest_path.parents[0]).mkdir(parents=True, exist_ok=True)
            self._populate_template(
                pkg_resources.resource_stream(
                    __name__, f"data/project_templates/{f}"
                ).read().decode(),
                dest_path,
                args
            )

    def execute(self, args):
        main_files = [
            'setup.py',
            'setup.cfg',
            'tox.ini',
            '.gitignore',
            'README.rst',
            'zuul.yaml',
            'requirements.txt',
            'test-requirements.txt'
        ]
        doc_files = [
            'doc/requirements.txt',
            'doc/source/conf.py',
            'doc/source/index.rst'
        ]
        api_ref_files = [
            'api-ref/source/conf.py',
            'api-ref/source/index.rst'
        ]
        rn_files = [
            'releasenotes/source/conf.py',
            'releasenotes/source/index.rst'
        ]

        self._process_template_section(main_files, args)
        self._process_template_section(doc_files, args)
        if args.enable_api_ref:
            self._process_template_section(api_ref_files, args)
        if args.enable_rn:
            self._process_template_section(rn_files, args)
