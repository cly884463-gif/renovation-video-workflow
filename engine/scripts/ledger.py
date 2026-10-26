"""Serialize history mutations, reject ID collisions and stale revisions."""
import contextlib,hashlib,json,os,time,uuid
from pathlib import Path
from production import read,require


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


@contextlib.contextmanager
def locked(path,timeout=15):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_name(path.name+'.lock').open('a+b') as f:
        f.seek(0,2)
        if f.tell()==0:f.write(b'0');f.flush()
        deadline=time.monotonic()+timeout
        while True:
            try:
                f.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=deadline:raise ValueError('团队记录正在写入或文件锁不可用，请稍后重试；不要绕过锁')
                time.sleep(.1)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)


def atomic_save(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.pending-'+uuid.uuid4().hex)
    with tmp.open('x',encoding='utf8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)


def check_job(job,history):
    require(job.get('id') and job['id']!='NEW01','须用new-job生成唯一任务ID')
    ids=[x['id'] for x in history];require(len(ids)==len(set(ids)),'历史存在重复ID，先核对合并')
    old=next((x for x in history if x['id']==job['id']),None)
    mode=job.get('mode','new');require(mode in ('new','revision'),'任务mode须为new或revision')
    if mode=='revision':
        require(old is not None,'返修目标不存在，不能作为新片写入')
        require(job.get('revision_base_sha256')==digest(old),'返修依据已过期；先读取最新记录，重新核对修改')
    else:require(old is None,'任务ID已存在；新片须用new-job生成新ID，返修须显式使用--revision')
    return old


def commit(path,job,entry,backup_dir):
    path=Path(path)
    with locked(path):
        history=read(path);old=check_job(job,history)
        others=[x for x in history if x['id']!=job['id']]
        retained=old and old['music_identity']==entry['music_identity'] and old['music_sha256']==entry['music_sha256']
        if others and not retained:
            require(others[-1]['music_identity']!=entry['music_identity'] and others[-1]['music_sha256']!=entry['music_sha256'],'团队历史已更新，相邻曲目重复，请换曲后重新审核')
        from production import save
        save(Path(backup_dir)/'history_before.json',history)
        if old is None:history.append(entry)
        else:history[history.index(old)]=entry
        atomic_save(path,history)


def seed(path,value):
    path=Path(path)
    with locked(path):
        if path.exists():read(path);return 'preserved'
        atomic_save(path,value);return 'created'
