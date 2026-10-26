"""Machine-specific mounts mapped to stable library identities, never host IPs."""
import re
from pathlib import Path
from production import require, resolve


def verify_aliases(name,relative,cfg):
    from production import sha
    candidates=[p/relative for p in roots(cfg)[name]]
    files=[p for p in candidates if p.is_file()]
    if len(files)>1:
        expected=sha(files[0])
        require(all(sha(p)==expected for p in files[1:]),'同库入口的同名文件内容冲突：'+str(relative)+'；请核对镜像或分配不同库ID')


def roots(cfg):
    result = {}
    base = Path(cfg.get('_base', '.'))
    configured = cfg.get('source_roots', {})
    require(isinstance(configured, dict), 'source_roots须为素材库ID到路径数组的对象')
    for name, paths in configured.items():
        require(re.fullmatch(r'[a-z][a-z0-9_-]*', name) and name not in ('workspace', 'package', 'cloud'), '素材库ID无效：'+name)
        require(isinstance(paths, list) and paths and all(isinstance(p, str) and p.strip() for p in paths), '每个素材库须配置非空路径数组')
        result[name] = [resolve(p, base) for p in paths]
    if cfg.get('shared_root'):
        legacy = resolve(cfg['shared_root'], base)
        result.setdefault('shared', [])
        if legacy not in result['shared']: result['shared'].insert(0, legacy)
    seen = {}
    for name, paths in result.items():
        for p in paths:
            require(p not in seen or seen[p] == name, '同一路径不能分配给两个素材库：'+str(p))
            seen[p] = name
    return result


def prefix(name):
    return '@shared/' if name == 'shared' else '@library/'+name+'/'


def key(source, cfg):
    p = Path(source).resolve()
    matches = [(len(root.parts), name, p.relative_to(root)) for name, paths in roots(cfg).items() for root in paths if p.is_relative_to(root)]
    require(matches, '素材不在配置的source_roots/shared_root或准确云端映射中')
    # An explicitly configured nested library takes precedence over its parent.
    _, name, relative = max(matches, key=lambda x: x[0])
    verify_aliases(name,relative,cfg)
    return prefix(name)+relative.as_posix()


def expand(value, cfg):
    if value.startswith('@shared/'):
        name, tail = 'shared', value[len('@shared/'):]
    elif value.startswith('@library/'):
        parts = value.split('/', 2)
        require(len(parts) == 3, '素材库路径缺相对路径')
        _, name, tail = parts
    else:
        return value
    require(tail and '..' not in tail.replace('\\', '/').split('/'), '素材库路径越界或为空')
    choices = roots(cfg).get(name, [])
    require(choices, '未配置素材库：'+name)
    candidates = []
    for root in choices:
        p = (root/tail).resolve()
        require(p.is_relative_to(root), '素材库路径越界')
        candidates.append(p)
    for p in candidates:
        if p.exists():
            if p.is_file():verify_aliases(name,Path(tail),cfg)
            return str(p)
    raise ValueError('所有已配置入口均找不到素材：'+value+'；检查共享权限、连接和相对目录')
