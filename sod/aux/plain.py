# This file is part of sod.
#
# Copyright (C) 2020,2021 Martin Kampas <martin.kampas@ubedi.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import glob
import logging
from os.path import isabs
import shlex
import shutil
import subprocess
from urllib.parse import urlparse

from .. import Error
from ..repository import AuxStore, Snapshot, SOD_DIR, SNAPSHOT_REF_PREFIX

logger = logging.getLogger(__name__)

class PlainAuxStore(AuxStore):
    def __init__(self, repository, name, url):
        try:
            self._parse_url(url)
        except Error:
            raise

        super().__init__(repository, name, url)

    @staticmethod
    def type_name():
        return 'plain'

    def update(self):
        self._remove_remotes()

        for snapshot in self._list():
            remote_name = snapshot.reference
            self._repository.git.remotes.create(remote_name,
                    self._snapshot_url(snapshot) + '/' + SOD_DIR,
                    'HEAD:' + SNAPSHOT_REF_PREFIX + snapshot.reference)
            logger.info('Updating %s', snapshot.reference)
            result = subprocess.run(['git', '--git-dir', self._repository.git.path, 'fetch',
                remote_name], capture_output=True, text=True)
            if result.returncode != 0:
                raise Error('Failed to update ' + snapshot.reference + ': ' + result.stderr)

    def _snapshot_url(self, snapshot):
        url = self._url
        assert '*' not in url or snapshot.id_
        if snapshot.id_:
            url = url.replace('*', snapshot.id_, 1)
        return url

    def restore(self, path, destination_path, snapshot):
        assert not isabs(path)
        assert isabs(destination_path)

        url = self._snapshot_url(snapshot)
        url += '/' + path
        self._download(url, destination_path)

    def _download(self, url, destination_path):
        scheme, netloc, path = self._parse_url(url)
        if not scheme or scheme == 'file':
            assert not netloc
            try:
                shutil.copyfile(path, destination_path, follow_symlinks=False)
            except Exception as e:
                raise Error('Failed to copy file: ' + str(e))
        elif scheme == 'ssh':
            quoted_path = glob.escape(path)
            # TODO Avoid using '-T'?
            result = subprocess.run(['scp', '-T', netloc + ':' + quoted_path, destination_path])
            if result.returncode != 0:
                raise Error('Download failed')
        else:
            assert False

    @staticmethod
    def _parse_url(url):
        parsed = urlparse(url)
        if parsed.params:
            raise Error('Unsupported URL: Parameters must be empty')
        if parsed.query:
            raise Error('Unsupported URL: Query must be empty')
        if parsed.fragment:
            raise Error('Unsupported URL: Fragment must be empty')
        if not parsed.path:
            raise Error('Invalid URL: No path specified')

        if not parsed.scheme or parsed.scheme == 'file':
            if parsed.netloc:
                raise Error('Invalid URL: Network location must be empty with the scheme used')
        elif parsed.scheme == 'ssh':
            if not parsed.netloc:
                raise Error('Invalid URL: Netwoek location must not be empty with the scheme used')
        else:
            raise Error('Unsupported URL: Unrecognized scheme')

        if '*' in parsed.netloc:
            raise Error('Unsupported URL: Network location must not contain \'*\'')
        if parsed.path.count('*') > 1:
            raise Error('Unsupported URL: Multiple \'*\' in path')

        return (parsed.scheme or 'file', parsed.netloc, parsed.path)

    def _remove_remotes(self):
        to_remove = []
        for remote in self._repository.git.remotes:
            if remote.name == self._name or remote.name.startswith(self._name + '/'):
                to_remove.append(remote.name)
        for name in to_remove:
            self._repository.git.remotes.delete(name)

    def _list(self):
        scheme, netloc, path = self._parse_url(self._url)
        if '*' not in path:
            yield Snapshot(self, None, None)
            return

        # Only match directories which look like sod repositories
        path += '/' + SOD_DIR

        prefix, suffix = path.split('*', maxsplit=1)

        matching_paths = []
        if scheme == 'file':
            matching_paths = glob.glob(path)
        elif scheme == 'ssh':
            remote_command = 'ls -d --quoting-style=shell {}*{}'.format(
                    shlex.quote(prefix), shlex.quote(suffix))
            result = subprocess.run(['ssh', netloc, remote_command], capture_output=True)
            if result.returncode != 0:
                raise Error('Failed to list snapshots: ' + result.stderr.decode())
            matching_paths = shlex.split(result.stdout.decode())
        else:
            assert False

        for matching_path in matching_paths:
            id_ = matching_path[len(prefix):-len(suffix)]
            yield Snapshot(self, id_, None)
