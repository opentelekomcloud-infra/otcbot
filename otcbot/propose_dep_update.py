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
import re

from pathlib import Path
import shutil

from git import Actor
from git import Repo


class ProposeDepUpdate:
    log = logging.getLogger("otcbot.propose_dep_update")

    def __init__(self):
        self.work_dir = None
        self.repo = None
        self.main_branch = None
        self.target_branch = None

    @classmethod
    def argparse_arguments(cls, parser) -> None:
        subparser = parser.add_parser("dep_update", help="Project name")
        subparser.add_argument("--name", required=True, help="Project name")
        subparser.add_argument(
            "--repo-url", required=True, help="Project git repository path"
        )
        subparser.add_argument(
            "--dependency-name", required=True, help="Dependency package"
        )
        subparser.add_argument(
            "--dependency-version",
            required=True,
            help="New dependency version (requirements.txt syntax)",
        )
        subparser.add_argument(
            "--checkout_dir", required=False, help="Checkout location"
        )
        subparser.add_argument(
            "--main-branch",
            required=False,
            default="main",
            help="Main/master branch name",
        )
        subparser.add_argument(
            "--branch", required=False, help="Target (PR) branch name"
        )

    def _set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.project_dir = Path(self.work_dir)

    def get_git_repo(self) -> Repo:
        """Get a repository object"""
        if not self.project_dir:
            raise RuntimeError("Project work dir is not set")
        self.log.debug("Getting git repository: %s", self.repo_url)
        if self.repo:
            return self.repo
        git_path = Path(self.project_dir, ".git")
        if git_path.exists():
            self.repo = Repo(self.project_dir)
        else:
            self.log.debug("Checking out repository")
            self.repo = Repo.clone_from(
                self.repo_url, self.project_dir, branch=self.main_branch
            )
        self.refresh_git_repo()
        return self.repo

    def refresh_git_repo(self, recurse_submodules=True):
        """Refresh git repository"""
        try:
            if not self.repo:
                self.repo = self.get_git_repo()
            self.repo.remotes.origin.update()
            self.repo.remotes.origin.fetch()
            # self.repo.git.checkout(self.main_branch)
            # self.remote_ref = self.repo.remotes.origin.refs[self.main_branch]
            head = self.repo.branches[self.main_branch]
            head.checkout(force=True)
            # self.remote_ref.checkout()
            # self.repo.head.reference = self.remote_ref
            # self.repo.head.reset(index=True, working_tree=True)
            if self.target_branch in self.repo.branches:
                self.repo.delete_head(self.target_branch)
            self.branch = self.repo.create_head(self.target_branch)
            # self.repo.heads[self.target_branch].set_tracking_branch(self.target_branch)
            self.repo.heads[self.target_branch].checkout()
        except Exception:
            self.log.exception("Cannot update repository")

    def execute(self, args):
        if args.checkout_dir:
            self._set_work_dir(args.checkout_dir)
        else:
            self._set_work_dir(args.name)
        if not self.work_dir:
            raise RuntimeError("Work dir is not set")
        self.repo_url = args.repo_url
        self.main_branch = args.main_branch
        self.target_branch = args.branch
        self.lib_name = args.dependency_name
        self.lib_ver = args.dependency_version
        self.repo = self.get_git_repo()
        dep_files = [
            "requirements.txt",
            "doc/requirements.txt",
            "api-ref/requirements.txt",
            "umn/requirements.txt",
        ]
        replacements_done = False
        for req_file in dep_files:
            rfile = Path(self.work_dir, req_file)
            if rfile.exists():
                bck_file = rfile.with_suffix(".bck")
                shutil.copy(rfile, bck_file)
                updated = False
                with (bck_file.open() as fr, rfile.open("w") as fw):
                    for line in fr:
                        new_line = re.sub(
                            f"{self.lib_name}[^#]*",
                            f"{self.lib_name}{self.lib_ver} ",
                            line,
                        )
                        if new_line != line:
                            updated = True
                        fw.write(new_line)
                if updated:
                    replacements_done = True
                    self.repo.index.add([rfile.resolve().as_posix()])
                bck_file.unlink()
        if replacements_done:
            author = Actor(
                "otcbot", "52695153+otcbot@users.noreply.github.com"
            )
            self.repo.index.commit(
                f"Update {self.lib_name} to {self.lib_ver}",
                author=author,
                committer=author,
            )
            origin = self.repo.remote(name="origin")
            origin.push(self.target_branch)
            # self.repo.remotes.origin.push('origin', self.target_branch)
