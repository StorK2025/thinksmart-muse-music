"""Exact file rollback. Backup data is root-only and never belongs in the repo."""
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


class Transaction:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.entries = []

    def backup(self, paths):
        for target in dict.fromkeys(map(Path, paths)):
            entry = {'path': str(target), 'exists': target.exists() or target.is_symlink()}
            if target.is_symlink():
                entry['link'] = os.readlink(target)
            elif entry['exists']:
                meta = target.stat()
                if not stat.S_ISREG(meta.st_mode):
                    raise ValueError('不是普通文件: ' + str(target))
                name = f'{len(self.entries):04}.backup'
                shutil.copy2(target, self.directory / name)
                entry.update(file=name, uid=meta.st_uid, gid=meta.st_gid, mode=stat.S_IMODE(meta.st_mode))
            self.entries.append(entry)
        self._save()

    def _save(self):
        path = self.directory / 'manifest.json'
        path.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding='utf-8')
        path.chmod(0o600)

    @staticmethod
    def restore(directory):
        directory = Path(directory).resolve()
        manifest = directory / 'manifest.json'
        if os.name != 'nt':
            for p in (directory, manifest):
                s = p.stat()
                if s.st_uid != os.getuid() or s.st_mode & 0o022:
                    raise ValueError('备份必须归 root 所有，且不能被其他账号改写。')
        entries = json.loads(manifest.read_text(encoding='utf-8'))
        # Validate the whole manifest before writing any file.
        for entry in entries:
            target = Path(entry['path'])
            if not target.is_absolute():
                raise ValueError('无效恢复目标')
            if entry['exists'] and 'link' not in entry:
                name = entry['file']
                if Path(name).name != name or not name.endswith('.backup'):
                    raise ValueError('无效备份文件')
                if not (directory / name).is_file():
                    raise ValueError('备份不完整')
        for entry in reversed(entries):
            target = Path(entry['path'])
            if 'link' in entry:
                target.unlink(missing_ok=True)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(entry['link'])
            elif entry['exists']:
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=target.parent)
                os.close(fd)
                try:
                    shutil.copyfile(directory / entry['file'], tmp)
                    os.chmod(tmp, entry['mode'])
                    if hasattr(os, 'chown'):
                        os.chown(tmp, entry['uid'], entry['gid'])
                    os.replace(tmp, target)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
            else:
                target.unlink(missing_ok=True)
